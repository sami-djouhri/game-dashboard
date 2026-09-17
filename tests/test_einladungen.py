"""Einladungs- und Bewerbungsflow.

Die Einladung ist der einzige Weg in die Mitgliederliste. Sie traegt Rolle und
Verifizierung: wer sie einloest, bekommt genau das, was der Admin eingestellt hat,
und nichts, was er selbst ins Formular schreibt.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import unquote

from app import db
from app.db import iso, now_utc
from app.security import invite_code


def _einladung(rolle: str = "member", verified: bool = False, tage: int = 14,
               max_uses: int = 1) -> str:
    code = invite_code()
    exp = iso(now_utc() + timedelta(days=tage)) if tage else None
    db.create_invite(code, rolle, verified, "Testeinladung", None, exp, max_uses)
    return code


def _einloesen(client, code: str, name: str = "neuling", **extra):
    daten = {"username": name, "display_name": name.title(),
             "password": "einladungswort", "password2": "einladungswort"}
    daten.update(extra)
    return client.post(f"/join/{code}", data=daten)


# ── Der normale Weg ───────────────────────────────────────────────────
def test_einladung_legt_konto_an(anonym):
    code = _einladung()
    antwort = _einloesen(anonym, code)
    assert antwort.status_code == 303
    assert antwort.headers["location"].startswith("/app")
    neu = db.get_user_by_name("neuling")
    assert neu is not None
    assert neu["role"] == "member"
    assert neu["verified"] == 0
    # Direkt angemeldet, ohne zweiten Schritt.
    assert anonym.cookies.get("gd_session")


def test_einladung_traegt_die_verifizierung(anonym):
    _einloesen(anonym, _einladung(verified=True), "vertraute")
    assert db.get_user_by_name("vertraute")["verified"] == 1


def test_einloesen_zaehlt_hoch(anonym):
    code = _einladung(max_uses=2)
    _einloesen(anonym, code, "erste")
    assert db.get_invite_by_code(code)["uses"] == 1
    _einloesen(anonym, code, "zweite")
    assert db.get_invite_by_code(code)["uses"] == 2
    # Jetzt ist sie aufgebraucht.
    _einloesen(anonym, code, "dritte")
    assert db.get_user_by_name("dritte") is None


# ── Wann eine Einladung nicht gilt ────────────────────────────────────
def test_abgelaufene_einladung(anonym):
    code = invite_code()
    db.create_invite(code, "member", False, "alt", None,
                     iso(now_utc() - timedelta(days=1)), 1)
    _einloesen(anonym, code, "zu-spaet")
    assert db.get_user_by_name("zu-spaet") is None


def test_zurueckgezogene_einladung(anonym):
    code = _einladung()
    db.revoke_invite(db.get_invite_by_code(code)["id"])
    _einloesen(anonym, code, "zurueckgezogen")
    assert db.get_user_by_name("zurueckgezogen") is None


def test_unbekannter_code(anonym):
    antwort = _einloesen(anonym, "GIBTESNICHT", "fremde")
    assert antwort.status_code == 200          # Seite mit Hinweis, kein Redirect
    assert db.get_user_by_name("fremde") is None


def test_einladung_ohne_ablauf_bleibt_gueltig(anonym):
    code = invite_code()
    db.create_invite(code, "member", False, "dauerhaft", None, None, 1)
    _einloesen(anonym, code, "spaeter")
    assert db.get_user_by_name("spaeter") is not None


# ── Was im Formular steht, entscheidet nichts ueber Rechte ────────────
def test_rolle_kommt_aus_der_einladung_nicht_aus_dem_formular(anonym):
    """Der Klassiker: ein verstecktes Feld `role=owner` im abgeschickten
    Formular. Es darf schlicht ignoriert werden."""
    _einloesen(anonym, _einladung(), "schlaue", role="owner", verified="1",
               is_admin="true", disabled="0")
    neu = db.get_user_by_name("schlaue")
    assert neu["role"] == "member"
    assert neu["verified"] == 0


def test_admin_einladung_macht_einen_admin(anonym):
    """Umgekehrt muss eine vom Owner ausgestellte Admin-Einladung auch wirken."""
    _einloesen(anonym, _einladung(rolle="admin"), "stellvertretung")
    assert db.get_user_by_name("stellvertretung")["role"] == "admin"


# ── Eingabepruefung beim Einloesen ────────────────────────────────────
def test_benutzername_muss_dem_muster_folgen(anonym):
    code = _einladung(max_uses=50)
    for name in ("ab", "x" * 30, "mit leerzeichen", "boese<script>", "punkt.name", ""):
        _einloesen(anonym, code, name)
        assert db.get_user_by_name(name) is None, f"„{name}" + "“ wurde angenommen"
    assert db.get_invite_by_code(code)["uses"] == 0


def test_passwort_muss_lang_genug_sein(anonym):
    code = _einladung()
    _einloesen(anonym, code, "kurzpasswort", password="kurz", password2="kurz")
    assert db.get_user_by_name("kurzpasswort") is None


def test_passwoerter_muessen_uebereinstimmen(anonym):
    code = _einladung()
    _einloesen(anonym, code, "vertippt", password="langgenug1", password2="langgenug2")
    assert db.get_user_by_name("vertippt") is None


def test_vergebener_name_wird_abgelehnt(anonym, mitglied):
    code = _einladung()
    _einloesen(anonym, code, "mitglied")
    assert db.count_users() == 1        # nur das Konto aus der Fixture
    assert db.get_invite_by_code(code)["uses"] == 0


# ── Bewerbung -> Einladung ────────────────────────────────────────────
def test_bewerbung_annehmen_erzeugt_einladung(admin, anonym):
    anonym.post("/apply", data={"name": "Bewerberin", "games": "valheim",
                                "message": "Ich moechte mitspielen."})
    bewerbung = db.list_applications()[0]
    antwort = admin.post(f"/admin/applications/{bewerbung['id']}/approve",
                         data={"verified": "1"})
    assert antwort.status_code == 303
    einladung = db.list_invites()[0]
    # Der Einladungslink steht als Meldung im Redirect und nennt den Host des
    # Aufrufs - im LAN-Vorschaubetrieb also einen Link, der dort auch funktioniert.
    meldung = unquote(antwort.headers["location"])
    assert f"/join/{einladung['code']}" in meldung
    assert "http://testserver/join/" in meldung

    assert einladung["role"] == "member"
    assert einladung["verified"] == 1
    assert einladung["max_uses"] == 1
    assert db.get_application(bewerbung["id"])["status"] == "approved"


def test_bewerbung_nur_einmal_entscheiden(admin, anonym):
    anonym.post("/apply", data={"name": "Doppelt"})
    bid = db.list_applications()[0]["id"]
    admin.post(f"/admin/applications/{bid}/approve", data={})
    zweite = admin.post(f"/admin/applications/{bid}/reject", data={})
    assert "err=" in zweite.headers["location"]
    assert db.get_application(bid)["status"] == "approved"
    assert len(db.list_invites()) == 1


def test_entschiedene_bewerbungen_werden_geloescht(admin, anonym):
    """DSGVO-Aufbewahrung: was entschieden und alt genug ist, verschwindet.
    Offene Bewerbungen bleiben, sonst waere die Warteliste selbst vergaenglich."""
    anonym.post("/apply", data={"name": "Alt-Entschieden"})
    anonym.post("/apply", data={"name": "Noch-Offen"})
    alt, offen = db.list_applications()[1], db.list_applications()[0]
    admin.post(f"/admin/applications/{alt['id']}/reject", data={})
    db._exec("UPDATE applications SET reviewed_at=? WHERE id=?",
             (iso(now_utc() - timedelta(days=60)), alt["id"]))

    assert db.purge_reviewed_applications(30) == 1
    verbleibend = [a["name"] for a in db.list_applications()]
    assert verbleibend == [offen["name"]]
