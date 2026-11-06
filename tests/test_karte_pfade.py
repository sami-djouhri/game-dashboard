"""Die Minecraft-Karte: Pfade duerfen die Kartenwurzel nie verlassen.

Dieselbe Klasse wie `test_vault_pfade.py`, nur schaerfer: `/karte/{pfad:path}`
nimmt Schraegstriche mit, der ganze Rest der URL kommt also roh in die Funktion.
Liefe die Pruefung ins Leere, stuende der Container offen, samt
`data/game-dashboard.sqlite` mit allen Passwort-Hashes.

Zusaetzlich geprueft wird die Unterscheidung „nicht gerendert" gegen „da":
`vorhanden()` fragt nach der `index.html` und nicht nach dem Verzeichnis. BlueMap
legt sein Datenverzeichnis naemlich beim ersten Start an, auch wenn es danach
nichts zeichnet -- genau dieser Zustand bestand von der Installation bis zum
2026-10-17. Eine Pruefung auf `is_dir()` haette „Karte vorhanden" gemeldet und die
Oberflaeche auf eine leere Seite verlinkt.
"""
from __future__ import annotations

import importlib

import pytest

BOESE_PFADE = [
    "../../etc/passwd",
    "../data/game-dashboard.sqlite",
    "..",
    "....//....//etc/passwd",
    "/etc/passwd",
    "maps/../../../root/.ssh/id_rsa",
    "index\x00.html",
    "..\\..\\windows\\system32",
    "%2e%2e%2fetc%2fpasswd",
]


@pytest.fixture
def karte(tmp_path, monkeypatch):
    """Eine Kartenwurzel, wie BlueMap sie nach dem Rendern hinterlaesst."""
    wurzel = tmp_path / "karte"
    (wurzel / "maps" / "world_freebuild" / "tiles").mkdir(parents=True)
    (wurzel / "index.html").write_text("<html>karte</html>")
    (wurzel / "settings.json").write_text('{"maps":["world_freebuild"]}')
    (wurzel / "maps" / "world_freebuild" / "tiles" / "0_0.json.gz").write_bytes(b"\x1f\x8b" + b"x" * 20)
    # Etwas, das NICHT ausgeliefert werden darf, aber innerhalb der Wurzel liegt.
    (wurzel / "geheim.conf").write_text("accept-download: true")
    # Und etwas ausserhalb, das ein Traversal treffen wuerde.
    (tmp_path / "beute.txt").write_text("hier liegt das Ziel")

    monkeypatch.setenv("MC_KARTE_DIR", str(wurzel))
    from app import karte as modul
    importlib.reload(modul)
    return wurzel, modul


# ── Containment ───────────────────────────────────────────────────────
@pytest.mark.parametrize("pfad", BOESE_PFADE)
def test_kein_ausbruch_aus_der_wurzel(karte, pfad):
    _, modul = karte
    assert modul.datei(pfad) is None, f"„{pfad}“ hat die Kartenwurzel verlassen"


def test_symlink_nach_draussen_wird_abgewiesen(karte, tmp_path):
    """`resolve()` auf beiden Seiten: ein Symlink IN der Wurzel, der nach
    draussen zeigt, besteht eine reine Zeichenketten-Pruefung mühelos."""
    wurzel, modul = karte
    (wurzel / "raus.html").symlink_to(tmp_path / "beute.txt")
    assert modul.datei("raus.html") is None


def test_erlaubte_datei_kommt_durch(karte):
    """Die Gegenprobe: waere alles verboten, liefe der Test oben ins Leere und
    niemand saehe je eine Karte."""
    wurzel, modul = karte
    treffer = modul.datei("index.html")
    assert treffer is not None
    ziel, typ = treffer
    assert ziel == (wurzel / "index.html")
    assert "html" in typ


def test_leerer_pfad_ist_die_startseite(karte):
    _, modul = karte
    treffer = modul.datei("")
    assert treffer and treffer[0].name == "index.html"


def test_unterverzeichnis_kommt_durch(karte):
    """Kacheln liegen tief verschachtelt, das muss gehen."""
    _, modul = karte
    treffer = modul.datei("maps/world_freebuild/tiles/0_0.json.gz")
    assert treffer is not None
    ziel, typ = treffer
    assert typ == "application/json", "gzip-Kachel braucht den JSON-Typ"
    assert modul.ist_gzip(ziel), "ohne Content-Encoding haelt der Browser sie fuer kaputt"


# ── Endungs-Allowlist ─────────────────────────────────────────────────
def test_fremde_endung_wird_abgewiesen(karte):
    """Allowlist statt Sperrliste. Die Datei liegt INNERHALB der Wurzel und waere
    ohne diese Pruefung abrufbar: BlueMaps eigene Konfiguration landet dort zwar
    nicht, aber wer das Verzeichnis einmal anders mountet, gibt sonst aus, was dort
    gerade liegt."""
    _, modul = karte
    assert modul.datei("geheim.conf") is None


def test_verzeichnis_ist_keine_datei(karte):
    _, modul = karte
    assert modul.datei("maps") is None


# ── Vorhanden heisst gerendert ────────────────────────────────────────
def test_vorhanden_erkennt_die_gerenderte_karte(karte):
    _, modul = karte
    assert modul.vorhanden() is True


def test_leeres_verzeichnis_gilt_nicht_als_karte(tmp_path, monkeypatch):
    """Der eigentliche Punkt. BlueMap legt sein Verzeichnis beim ersten Start an
    und zeichnet trotzdem nichts, wenn `accept-download` auf false steht: genau so lag
    es hier von der Installation bis zum 2026-10-17 (16 KB, kein Block). Ein Test auf
    `is_dir()` haette die Oberflaeche auf eine leere Seite verlinken lassen."""
    leer = tmp_path / "karte"
    (leer / "web").mkdir(parents=True)
    monkeypatch.setenv("MC_KARTE_DIR", str(leer))
    from app import karte as modul
    importlib.reload(modul)
    assert modul.vorhanden() is False
    assert modul.datei("index.html") is None


def test_fehlender_mount_sagt_nichts(tmp_path, monkeypatch):
    monkeypatch.setenv("MC_KARTE_DIR", str(tmp_path / "gibt-es-nicht"))
    from app import karte as modul
    importlib.reload(modul)
    assert modul.vorhanden() is False
    assert modul.datei("index.html") is None
