"""Bremsen gegen Durchprobieren: Anmeldung, Bewerbung, Welt-Anlegen.

Dazu die Frage, gegen WEN gebremst wird. `X-Forwarded-For` darf nur zaehlen, wenn
der TCP-Peer ein bekannter Reverse-Proxy ist. Waere das nicht so, koennte jeder
Aufrufer mit einem frei erfundenen Header je Versuch eine neue Identitaet
behaupten und die Bremse komplett umgehen.
"""
from __future__ import annotations

import time

from starlette.requests import Request

from app import db, security
from app.auth import client_ip
from app.config import settings
from app.security import RateLimiter
from tests.conftest import PASSWORT, konto


def _anfrage(peer: str, **kopfzeilen) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(k.replace("_", "-").lower().encode(), v.encode())
                    for k, v in kopfzeilen.items()],
        "client": (peer, 51234),
    })


# ── Anmelde-Bremse ────────────────────────────────────────────────────
def test_anmeldung_wird_nach_n_versuchen_gebremst(anonym, monkeypatch):
    """Nach der Obergrenze ist Schluss - auch fuer den, der das Passwort dann
    richtig eintippt. Die Bremse sitzt bewusst VOR der Passwortpruefung."""
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    konto("gebremste")

    for versuch in range(3):
        antwort = anonym.post("/login", data={"username": "gebremste", "password": "falsch"})
        assert "err=" in antwort.headers["location"]
        assert "Zu+viele" not in antwort.headers["location"], \
            f"schon Versuch {versuch + 1} wurde gebremst, die Grenze ist zu scharf"

    gebremst = anonym.post("/login", data={"username": "gebremste", "password": PASSWORT})
    assert "Zu+viele+Versuche" in gebremst.headers["location"]
    assert anonym.cookies.get(settings.session_cookie) is None


def test_erfolgreiche_anmeldung_loest_die_bremse(anonym, monkeypatch):
    """Wer sich einmal vertippt und dann richtig anmeldet, soll nicht mit einer
    halb vollen Bremse weiterleben."""
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    konto("tippfehler")
    anonym.post("/login", data={"username": "tippfehler", "password": "falsch"})
    gut = anonym.post("/login", data={"username": "tippfehler", "password": PASSWORT})
    assert gut.headers["location"] == "/app"
    assert security.rate._hits.get("login:testclient:tippfehler", []) == []


def test_breite_ip_schranke_gegen_namensraten(anonym, monkeypatch):
    """Die zweite Schranke zaehlt pro Adresse ueber ALLE Namen. Ohne sie koennte
    jemand mit je acht Versuchen beliebig viele Namen durchprobieren."""
    monkeypatch.setattr(settings, "login_max_attempts", 3)   # IP-Gesamtgrenze: 3 * 3
    for i in range(9):
        antwort = anonym.post("/login", data={"username": f"namen-{i}", "password": "x"})
        assert "Zu+viele" not in antwort.headers["location"]
    letzter = anonym.post("/login", data={"username": "namen-99", "password": "x"})
    assert "Zu+viele+Versuche" in letzter.headers["location"]


def test_erfundener_forwarded_header_umgeht_die_bremse_nicht(anonym, monkeypatch):
    """Der Testclient ist kein vertrauenswuerdiger Proxy. Ein selbst gesetzter
    `X-Forwarded-For` darf deshalb keine neue Identitaet erzeugen."""
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    for i in range(9):
        anonym.post("/login", data={"username": "opfer", "password": "x"},
                    headers={"X-Forwarded-For": f"203.0.113.{i}"})
    letzter = anonym.post("/login", data={"username": "opfer", "password": "x"},
                          headers={"X-Forwarded-For": "203.0.113.200"})
    assert "Zu+viele+Versuche" in letzter.headers["location"]


# ── Welche Adresse zaehlt ─────────────────────────────────────────────
def test_forwarded_header_nur_hinter_bekanntem_proxy():
    vertraut = _anfrage("127.0.0.1", x_forwarded_for="203.0.113.7")
    assert client_ip(vertraut) == "203.0.113.7"

    fremd = _anfrage("198.51.100.4", x_forwarded_for="203.0.113.7")
    assert client_ip(fremd) == "198.51.100.4", "ein fremder Peer darf keine Adresse behaupten"


def test_forwarded_kette_nimmt_den_ersten_eintrag():
    anfrage = _anfrage("127.0.0.1", x_forwarded_for="203.0.113.7, 10.0.0.1, 172.17.0.5")
    assert client_ip(anfrage) == "203.0.113.7"


def test_unsinniger_peer_faellt_nicht_um():
    """Der Testclient meldet sich als „testclient", also gar keine Adresse. Das
    darf keine Ausnahme werfen, sondern muss schlicht als eigene Quelle gelten."""
    assert client_ip(_anfrage("testclient", x_forwarded_for="203.0.113.7")) == "testclient"


def test_proxy_netz_wird_als_bereich_erkannt():
    # 172.16.0.0/12 steht als Netz in den vertrauten Proxys (docker-Bridges).
    assert client_ip(_anfrage("172.20.0.9", x_forwarded_for="203.0.113.7")) == "203.0.113.7"
    # 172.32.x liegt ausserhalb von /12 und darf nicht mehr vertrauen.
    assert client_ip(_anfrage("172.32.0.9", x_forwarded_for="203.0.113.7")) == "172.32.0.9"


# ── Herkunft wird nie als Adresse gespeichert ─────────────────────────
def test_verlauf_speichert_keine_adressen(anonym):
    """In der Datenbank steht eine Kennung, keine IP. Sonst waere das Audit-Log
    ein Bewegungsprofil."""
    anonym.post("/login", data={"username": "unbekannt", "password": "x"})
    zeilen = db.recent_events(5)
    assert zeilen, "der Fehlversuch wurde gar nicht protokolliert"
    assert zeilen[0]["action"] == "login.fail"
    assert zeilen[0]["detail"].startswith("quelle-")


def test_kennung_ist_stabil_und_nicht_die_adresse():
    a = security.ip_kennung("203.0.113.7")
    b = security.ip_kennung("203.0.113.7")
    c = security.ip_kennung("203.0.113.8")
    assert a == b and a != c
    assert "203.0.113" not in a


# ── Bewerbungen ───────────────────────────────────────────────────────
def test_bewerbungen_sind_gedeckelt(anonym, monkeypatch):
    monkeypatch.setattr(settings, "apply_max_per_hour", 2)
    for i in range(2):
        antwort = anonym.post("/apply", data={"name": f"Bewerber {i}", "games": "valheim"})
        assert antwort.status_code == 200
    zuviel = anonym.post("/apply", data={"name": "Bewerber 3"})
    assert zuviel.status_code == 303
    assert "Zu+viele+Bewerbungen" in zuviel.headers["location"]
    assert len(db.list_applications()) == 2


def test_bewerbung_braucht_einen_namen(anonym):
    antwort = anonym.post("/apply", data={"name": "x"})
    assert antwort.status_code == 303
    assert "err=" in antwort.headers["location"]
    assert db.list_applications() == []


# ── Welt-Anlegen ──────────────────────────────────────────────────────
def test_welt_anlegen_ist_pro_admin_gedeckelt(admin, bruecke):
    """Zwei neue Welten am Tag. Jede Welt kostet Plattenplatz auf dem Spiele-VPS,
    und angelegt ist sie in einer Sekunde."""
    for i in range(2):
        antwort = admin.post("/api/games/terraria/worlds", json={"id": f"neue-welt-{i}"})
        assert antwort.status_code == 200, antwort.text
    dritte = admin.post("/api/games/terraria/worlds", json={"id": "neue-welt-3"})
    assert dritte.status_code == 429
    assert sum(1 for a in bruecke.aufrufe if a[0] == "create_world") == 2


def test_welt_id_muss_dem_muster_folgen(admin, bruecke):
    """Die ID landet auf dem Wirt in Verzeichnisnamen und Arbiter-Aufrufen. Alles,
    was dort Unfug anrichten koennte, faellt schon hier durch."""
    for unfug in ("../etc", "welt mit leerzeichen", "ab", "x" * 40, "welt;rm -rf /",
                  "welt$(id)", "welt/unter", "", "welt\nzweite"):
        antwort = admin.post("/api/games/terraria/worlds", json={"id": unfug})
        assert antwort.status_code == 400, f"„{unfug}" + "“ wurde als Welt-ID angenommen"
    assert not bruecke.kam_an("create_world")


def test_welt_id_wird_klein_geschrieben(admin, bruecke):
    """Grossschreibung ist kein Fehler, sondern wird vereinheitlicht - sonst
    entstuenden „Greenleaf" und „greenleaf" als zwei Welten nebeneinander."""
    assert admin.post("/api/games/terraria/worlds", json={"id": "GROSS"}).status_code == 200
    assert bruecke.zuletzt() == ("create_world", "terraria", "gross", "")


# ── Der Zaehler selbst ────────────────────────────────────────────────
def test_fenster_gleitet():
    limiter = RateLimiter()
    assert limiter.allow("k", 2, 1) is True
    assert limiter.allow("k", 2, 1) is True
    assert limiter.allow("k", 2, 1) is False
    time.sleep(1.05)
    assert limiter.allow("k", 2, 1) is True, "das Zeitfenster gibt nichts wieder frei"


def test_schluessel_sind_getrennt():
    limiter = RateLimiter()
    assert limiter.allow("a", 1, 60) is True
    assert limiter.allow("a", 1, 60) is False
    assert limiter.allow("b", 1, 60) is True


def test_vorgabewerte_sind_nicht_versehentlich_offen():
    """Eine Bremse, die erst nach hundert Versuchen greift, ist keine. Der Test
    haelt die Groessenordnung fest, nicht die exakte Zahl."""
    assert 3 <= settings.login_max_attempts <= 15
    assert 300 <= settings.login_window_s <= 3600
    assert 1 <= settings.apply_max_per_hour <= 20
