"""Sitzungen: Ablauf, Abmeldung, Sperre, Cookie-Eigenschaften.

Eine Sitzung ist der einzige Ausweis, den diese Seite kennt. Sie muss von selbst
verfallen, beim Abmelden und beim Sperren sofort erloeschen, und ihr Cookie darf
nicht per Skript auslesbar oder ueber eine unverschluesselte Verbindung
abgreifbar sein.
"""
from __future__ import annotations

from datetime import timedelta

from app import db
from app.config import settings
from app.db import iso, now_utc
from tests.conftest import PASSWORT, anmelden, konto


def _altern_lassen(token: str, tage: int) -> None:
    """Die Sitzung kuenstlich altern lassen, statt im Test zu warten."""
    db._exec("UPDATE sessions SET expires_at=? WHERE token=?",
             (iso(now_utc() - timedelta(days=tage)), token))


# ── Ablauf ────────────────────────────────────────────────────────────
def test_abgelaufene_sitzung_wird_abgewiesen(mitglied):
    assert mitglied.get("/api/me").status_code == 200
    _altern_lassen(mitglied.token, 1)
    assert mitglied.get("/api/me").status_code == 401


def test_abgelaufene_sitzung_wird_beim_zugriff_entfernt(mitglied):
    """Nicht nur abweisen: die Zeile verschwindet. Sonst sammelt die Tabelle
    Ausweise, die niemand mehr braucht, aber jeder Datenbank-Dump enthaelt."""
    _altern_lassen(mitglied.token, 1)
    mitglied.get("/api/me")
    assert db.get_session(mitglied.token) is None
    assert db._one("SELECT * FROM sessions WHERE token=?", (mitglied.token,)) is None


def test_aufraeumer_entfernt_nur_abgelaufene(mitglied):
    frisch = anmelden(konto("frische-person"), "frische-person")
    _altern_lassen(mitglied.token, 1)
    db.purge_expired_sessions()
    assert db._one("SELECT * FROM sessions WHERE token=?", (mitglied.token,)) is None
    assert db.get_session(frisch.token) is not None


def test_gueltigkeit_folgt_der_einstellung(mitglied):
    sitzung = db.get_session(mitglied.token)
    from datetime import datetime
    rest = datetime.fromisoformat(sitzung["expires_at"]) - now_utc()
    assert timedelta(days=settings.session_ttl_days - 1) < rest <= timedelta(days=settings.session_ttl_days)


# ── Abmelden und Sperren ──────────────────────────────────────────────
def test_abmelden_loescht_die_sitzung(mitglied):
    antwort = mitglied.post("/logout")
    assert antwort.status_code == 303
    assert db.get_session(mitglied.token) is None
    # Das Cookie wird zusaetzlich im Browser geraeumt.
    assert "gd_session=" in antwort.headers.get("set-cookie", "")


def test_sperren_beendet_laufende_sitzungen(admin):
    opfer = anmelden(konto("stoerenfried"), "stoerenfried")
    assert opfer.get("/api/me").status_code == 200
    antwort = admin.post(f"/admin/users/{opfer.uid}/disable", data={"value": "1"})
    assert antwort.status_code == 303
    assert db._one("SELECT * FROM sessions WHERE user_id=?", (opfer.uid,)) is None
    assert opfer.get("/api/me").status_code == 401


def test_geloeschtes_konto_nimmt_seine_sitzungen_mit(owner):
    opfer = anmelden(konto("scheidende"), "scheidende")
    owner.post(f"/admin/users/{opfer.uid}/delete", data={})
    assert db.get_user(opfer.uid) is None
    assert db._one("SELECT * FROM sessions WHERE user_id=?", (opfer.uid,)) is None


def test_selbstloeschung_braucht_das_passwort(mitglied):
    falsch = mitglied.post("/account/delete", data={"password": "nicht-das-passwort"})
    assert falsch.status_code == 303
    assert "err=" in falsch.headers["location"]
    assert db.get_user(mitglied.uid) is not None

    richtig = mitglied.post("/account/delete", data={"password": PASSWORT})
    assert richtig.status_code == 303
    assert db.get_user(mitglied.uid) is None


def test_selbstloeschung_anonymisiert_den_verlauf(mitglied):
    db.log_event("mitglied", "game.start", "valheim")
    mitglied.post("/account/delete", data={"password": PASSWORT})
    akteure = {e["actor"] for e in db.recent_events(50)}
    assert "mitglied" not in akteure, "der Name blieb im Audit-Log stehen"


def test_owner_kann_sich_nicht_selbst_loeschen(owner):
    antwort = owner.post("/account/delete", data={"password": PASSWORT})
    assert antwort.status_code == 303
    assert "err=" in antwort.headers["location"]
    assert db.get_user(owner.uid) is not None


# ── Anmeldung und Cookie ──────────────────────────────────────────────
def test_anmeldung_setzt_ein_cookie(anonym):
    konto("anmelderin")
    antwort = anonym.post("/login", data={"username": "anmelderin", "password": PASSWORT})
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/app"
    token = anonym.cookies.get(settings.session_cookie)
    assert token and db.get_session(token) is not None


def test_gesperrtes_konto_kann_sich_nicht_anmelden(anonym):
    konto("gesperrte", disabled=True)
    antwort = anonym.post("/login", data={"username": "gesperrte", "password": PASSWORT})
    assert "err=" in antwort.headers["location"]
    assert anonym.cookies.get(settings.session_cookie) is None


def test_cookie_traegt_die_schutz_attribute(anonym, monkeypatch):
    """Im Betrieb laeuft die Seite hinter TLS. Dann muss das Cookie `Secure`
    tragen, `HttpOnly` sein und bei SameSite=lax bleiben - letzteres ist neben
    dem CSRF-Token die zweite Haelfte des Schutzes."""
    monkeypatch.setattr(settings, "cookie_secure", True)
    konto("sichere")
    antwort = anonym.post("/login", data={"username": "sichere", "password": PASSWORT})
    kopf = antwort.headers["set-cookie"].lower()
    assert "httponly" in kopf
    assert "secure" in kopf
    assert "samesite=lax" in kopf
    assert "path=/" in kopf


def test_cookie_ist_undurchsichtig(mitglied):
    """Im Cookie steht ein Zufallstoken, kein Name und keine Rolle. Was drin
    steht, koennte sonst jemand umschreiben."""
    assert mitglied.username not in mitglied.token
    assert "member" not in mitglied.token
    assert len(mitglied.token) >= 40


def test_erfundenes_cookie_oeffnet_nichts(anonym):
    anonym.cookies.set(settings.session_cookie, "frei-erfunden-aber-lang-genug-xxxxxxxxxxxx")
    assert anonym.get("/api/me").status_code == 401


def test_passwortwechsel_braucht_das_alte_passwort(mitglied):
    falsch = mitglied.post("/account/password",
                           data={"current": "falsch", "new": "neues-passwort", "new2": "neues-passwort"})
    assert "err=" in falsch.headers["location"]

    zu_kurz = mitglied.post("/account/password",
                            data={"current": PASSWORT, "new": "kurz", "new2": "kurz"})
    assert "err=" in zu_kurz.headers["location"]

    ungleich = mitglied.post("/account/password",
                             data={"current": PASSWORT, "new": "neues-passwort", "new2": "anderes-wort"})
    assert "err=" in ungleich.headers["location"]

    alter_hash = db.get_user(mitglied.uid)["password_hash"]
    gut = mitglied.post("/account/password",
                        data={"current": PASSWORT, "new": "neues-passwort", "new2": "neues-passwort"})
    assert "msg=" in gut.headers["location"]
    assert db.get_user(mitglied.uid)["password_hash"] != alter_hash
