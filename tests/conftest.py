"""Testumgebung: eigene Datenbank je Test, gestubbte wake-bridge, leere Bremsen.

★ Die Umgebungsvariablen stehen hier GANZ oben, vor jedem `app.`-Import:
`app/config.py` wertet `Settings()` beim Modulimport aus, ein spaeteres
`os.environ[...]` aendert daran nichts mehr. Genau daran ist andernorts schon ein
Waechter gescheitert, der nichts prueffte und trotzdem gruen war.

Zwei bewusste Abweichungen vom Produktivbetrieb, beide hier und nicht im Test:
  * `COOKIE_SECURE=false` - der Testclient spricht http, ein Secure-Cookie aus
    `Set-Cookie` wuerde von httpx gar nicht erst zurueckgeschickt. Dass die Flags
    im Produktivfall richtig gesetzt werden, prueft `test_sessions.py` am Header.
  * `DATA_DIR` zeigt ins Temp-Verzeichnis, damit ein Testlauf niemals die echte
    `data/`-Datenbank oder die `ip-kennung.secret` anfasst.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="game-dashboard-tests-")
os.environ["COOKIE_SECURE"] = "false"
os.environ["GAME_BRIDGE_TOKEN"] = "pruef-bridge-token"
os.environ["PROVISION_TOKEN"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bridge, db, security  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORT = "pruefwort-12345"


@lru_cache(maxsize=8)
def _hash(passwort: str) -> str:
    """argon2id kostet auf dem Pi ueber eine Sekunde je Aufruf. Die Kosten sind
    gewollt (sie sind der Schutz), also wird nicht der Algorithmus verbilligt,
    sondern derselbe Hash ueber den ganzen Lauf wiederverwendet."""
    return hash_password(passwort)


# ── Arbiter-Status, wie ihn die wake-bridge liefert ───────────────────
# Genug Struktur, dass build_view echte Kacheln baut: ein laufendes Spiel, ein
# Multi-Welt-Spiel mit zwei Welten, eine Reservierung.
def arbiter_status() -> dict:
    return {
        "games": {
            "registry": ["dayz", "valheim", "terraria", "zomboid", "factorio", "avorion"],
            "worlds": {"terraria": {"active": "greenleaf", "list": ["greenleaf", "testwelt"]}},
            "detail": {"valheim": {"players": 2, "running": True}},
            "reserved_all": ["valheim"],
            "bedarf": {"dayz": {"ram_mb": 5700, "min_free_mb": 6000},
                       "valheim": {"ram_mb": 2000, "min_free_mb": 2500}},
            "running": ["valheim"],
        },
        "ram": {"avail_mb": 9000, "reserviert_startend_mb": 0},
        "mc": {"running": False},
        "lab": {"reserved": False},
    }


@dataclass
class Bruecke:
    """Aufzeichnung dessen, was das Dashboard an die Bridge weitergegeben haette."""
    aufrufe: list = field(default_factory=list)
    antwort: tuple[str, str] = ("ok", "fertig")

    def zuletzt(self) -> tuple:
        return self.aufrufe[-1] if self.aufrufe else ()

    def kam_an(self, name: str) -> bool:
        return any(a[0] == name for a in self.aufrufe)


@pytest.fixture(autouse=True)
def bruecke(monkeypatch) -> Bruecke:
    """Stubbt JEDEN Weg nach draussen. autouse, damit kein Test versehentlich
    einen echten Socket oeffnet - in CI gibt es weder Arbiter noch Spielserver."""
    b = Bruecke()

    async def status() -> dict:
        return arbiter_status()

    async def always_on() -> dict:
        return {}

    async def post_action(action: str, game: str, world: str | None = None):
        b.aufrufe.append(("post_action", action, game, world))
        return b.antwort

    async def set_reservierung(game: str, an: bool):
        b.aufrufe.append(("set_reservierung", game, an))
        return b.antwort

    async def create_world(game: str, world_id: str, label: str = ""):
        b.aufrufe.append(("create_world", game, world_id, label))
        return b.antwort

    async def snapshot_now(game: str, world: str | None = None):
        b.aufrufe.append(("snapshot_now", game, world))
        return b.antwort

    async def restore_snapshot(game: str, file: str):
        b.aufrufe.append(("restore_snapshot", game, file))
        return b.antwort

    async def delete_snapshot(game: str, file: str):
        b.aufrufe.append(("delete_snapshot", game, file))
        return b.antwort

    async def delete_world(game: str, world_id: str):
        b.aufrufe.append(("delete_world", game, world_id))
        return b.antwort

    async def list_snapshots(game: str) -> dict:
        b.aufrufe.append(("list_snapshots", game))
        return {"nightly": [], "manual": []}

    for name, fn in (("get_status", status), ("get_always_on", always_on),
                     ("post_action", post_action), ("set_reservierung", set_reservierung),
                     ("create_world", create_world), ("snapshot_now", snapshot_now),
                     ("restore_snapshot", restore_snapshot), ("delete_snapshot", delete_snapshot),
                     ("delete_world", delete_world), ("list_snapshots", list_snapshots)):
        monkeypatch.setattr(bridge, name, fn)
    return b


@pytest.fixture(autouse=True)
def frische_ablage(tmp_path, monkeypatch):
    """Je Test eine leere SQLite-Datei und leere Bremsen.

    Ohne das Leeren des Rate-Limiters tragen sich Tests gegenseitig ihre
    Fehlversuche ein: der Limiter ist prozesslokal und kennt keine Testgrenze.
    """
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "worlds_dir", str(tmp_path / "worlds"))
    if db._conn is not None:
        db._conn.close()
    db._conn = None
    db.init_db()
    security.rate._hits.clear()
    yield
    if db._conn is not None:
        db._conn.close()
    db._conn = None


# ── Konten und angemeldete Clients ────────────────────────────────────
@dataclass
class Sitzung:
    """Ein angemeldeter Browser: Client, Konto-ID und das CSRF-Token der Session."""
    client: TestClient
    uid: int
    username: str
    csrf: str
    token: str

    def get(self, url: str, **kw):
        return self.client.get(url, **kw)

    def post(self, url: str, **kw):
        """POST mit gueltigem CSRF: als Header (JSON-API) und als Formularfeld.

        Die API liest `X-CSRF-Token`, die Formulare ein Feld `csrf` - beide hier
        zu setzen haelt die Tests lesbar. Wer CSRF pruefen will, nimmt
        `roh_post` und legt selbst fest, was mitgeht.
        """
        kw.setdefault("headers", {}).setdefault("X-CSRF-Token", self.csrf)
        if not ({"json", "content", "files"} & set(kw)):
            daten = kw.get("data") or {}
            daten.setdefault("csrf", self.csrf)
            kw["data"] = daten
        return self.client.post(url, **kw)

    def roh_post(self, url: str, **kw):
        return self.client.post(url, **kw)


def konto(username: str, rolle: str = "member", verified: bool = False,
          disabled: bool = False, **extra) -> int:
    uid = db.create_user(username, username, _hash(PASSWORT), role=rolle,
                         verified=verified, **extra)
    if disabled:
        db.set_disabled(uid, True)
    return uid


def anmelden(uid: int, username: str) -> Sitzung:
    token, csrf = db.create_session(uid, "quelle-test", "pytest")
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(settings.session_cookie, token)
    return Sitzung(client=client, uid=uid, username=username, csrf=csrf, token=token)


@pytest.fixture
def anonym() -> TestClient:
    # Die Peer-Adresse des Testclients ist fest „testclient" und damit kein
    # vertrauenswuerdiger Proxy. Das ist hier die richtige Vorgabe: so wird
    # `X-Forwarded-For` verworfen, wie bei einem Direktzugriff von aussen.
    # Den vertrauten Fall prueft `test_bremsen.py` direkt an `auth.client_ip`.
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def mitglied() -> Sitzung:
    return anmelden(konto("mitglied"), "mitglied")


@pytest.fixture
def verifiziert() -> Sitzung:
    return anmelden(konto("verifiziert", verified=True), "verifiziert")


@pytest.fixture
def admin() -> Sitzung:
    return anmelden(konto("chefin", rolle="admin"), "chefin")


@pytest.fixture
def owner() -> Sitzung:
    return anmelden(konto("eigner", rolle="owner", verified=True), "eigner")
