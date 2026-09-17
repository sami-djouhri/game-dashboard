"""Rollen-Durchsetzung je Endpunkt.

Der Wert dieser Datei liegt in der Vollstaendigkeit der Tabellen: eine neue Route
faellt nur dann auf, wenn jede bestehende hier steht. Wer einen Endpunkt ergaenzt,
traegt ihn in die passende Liste ein - `test_keine_route_vergessen` besteht darauf.

Jeder Eintrag nennt das Routenmuster (so, wie FastAPI es kennt) UND den konkreten
Pfad, mit dem geprueft wird. Das Muster ist fuer die Vollstaendigkeitsprobe da,
der Pfad fuer den Aufruf; eine Ableitung des einen aus dem anderen war zu
fehleranfaellig, um sich darauf zu verlassen.
"""
from __future__ import annotations

import pytest

from app import db
from app.config import settings
from app.main import app
from tests.conftest import anmelden, konto

# (Methode, Routenmuster, Pfad, noetig)  noetig: offen|angemeldet|verifiziert|admin|owner
API_ROUTEN = [
    ("GET", "/api/public/status", "/api/public/status", "offen"),
    ("GET", "/api/me", "/api/me", "angemeldet"),
    ("GET", "/api/status", "/api/status", "angemeldet"),
    ("POST", "/api/games/{game}/start", "/api/games/valheim/start", "angemeldet"),
    ("GET", "/api/worlds/{key}/download", "/api/worlds/valheim/download", "verifiziert"),
    ("POST", "/api/games/{game}/stop", "/api/games/valheim/stop", "admin"),
    ("POST", "/api/games/{game}/restart", "/api/games/valheim/restart", "admin"),
    ("POST", "/api/games/{game}/reserve", "/api/games/valheim/reserve", "admin"),
    ("POST", "/api/games/{game}/release", "/api/games/valheim/release", "admin"),
    ("POST", "/api/games/{game}/switch", "/api/games/terraria/switch?world=testwelt", "admin"),
    ("POST", "/api/games/{game}/worlds", "/api/games/terraria/worlds", "admin"),
    ("POST", "/api/games/{game}/worlds/delete", "/api/games/terraria/worlds/delete", "admin"),
    ("GET", "/api/games/{game}/snapshots", "/api/games/valheim/snapshots", "admin"),
    ("POST", "/api/games/{game}/snapshot", "/api/games/valheim/snapshot", "admin"),
    ("POST", "/api/games/{game}/restore", "/api/games/valheim/restore", "admin"),
    ("POST", "/api/games/{game}/snapshots/delete", "/api/games/valheim/snapshots/delete", "admin"),
]

# Formular-POSTs. Platzhalter-IDs reichen fuer die Rollenprobe: die Pruefung ist
# eine Dependency und laeuft, bevor die Funktion ueberhaupt in die DB schaut.
FORMULARE = [
    ("/logout", "/logout", "angemeldet"),
    ("/account/password", "/account/password", "angemeldet"),
    ("/account/delete", "/account/delete", "angemeldet"),
    ("/admin/applications/{app_id}/approve", "/admin/applications/1/approve", "admin"),
    ("/admin/applications/{app_id}/reject", "/admin/applications/1/reject", "admin"),
    ("/admin/invites", "/admin/invites", "admin"),
    ("/admin/invites/{invite_id}/revoke", "/admin/invites/1/revoke", "admin"),
    ("/admin/users/{uid}/verify", "/admin/users/1/verify", "admin"),
    ("/admin/users/{uid}/disable", "/admin/users/1/disable", "admin"),
    ("/admin/users/{uid}/role", "/admin/users/1/role", "owner"),
    ("/admin/users/{uid}/delete", "/admin/users/1/delete", "owner"),
]

SEITEN = [
    ("/", "offen"),
    ("/login", "offen"),
    ("/apply", "offen"),
    ("/guides", "offen"),
    ("/impressum", "offen"),
    ("/datenschutz", "offen"),
    ("/app", "angemeldet"),
    ("/account", "angemeldet"),
    ("/admin", "admin"),
    ("/admin/verlauf", "admin"),
]

VERWALTUNG = [r for r in API_ROUTEN if r[3] in ("admin", "owner")]
NUR_OWNER = [f for f in FORMULARE if f[2] == "owner"]


def _ruf(sitzung, methode: str, pfad: str):
    return sitzung.get(pfad) if methode == "GET" else sitzung.post(pfad, json={})


# ── anonym ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("methode,muster,pfad,noetig", API_ROUTEN)
def test_api_ohne_anmeldung(anonym, methode, muster, pfad, noetig):
    antwort = (anonym.get(pfad) if methode == "GET"
               else anonym.post(pfad, json={}, headers={"X-CSRF-Token": "egal"}))
    if noetig == "offen":
        assert antwort.status_code == 200
    else:
        assert antwort.status_code == 401, f"{methode} {pfad} war ohne Anmeldung erreichbar"


@pytest.mark.parametrize("muster,pfad,noetig", FORMULARE)
def test_formulare_ohne_anmeldung(anonym, muster, pfad, noetig):
    assert anonym.post(pfad, data={"csrf": "egal"}).status_code == 401


def test_seiten_ohne_anmeldung(anonym):
    for pfad, noetig in SEITEN:
        antwort = anonym.get(pfad)
        if noetig == "offen":
            assert antwort.status_code == 200, f"{pfad} war anonym nicht erreichbar"
        else:
            # Mitglieder-Seiten leiten zur Anmeldung um, der Admin-Bereich antwortet
            # hart mit 401 (er haengt direkt an der current_user-Dependency).
            assert antwort.status_code in (303, 401), f"{pfad} war anonym offen"
            if antwort.status_code == 303:
                assert antwort.headers["location"].startswith("/login")


# ── Mitglied gegen Admin-Rechte ───────────────────────────────────────
@pytest.mark.parametrize("methode,muster,pfad,noetig", VERWALTUNG)
def test_mitglied_darf_nicht_verwalten(mitglied, methode, muster, pfad, noetig):
    assert _ruf(mitglied, methode, pfad).status_code == 403, \
        f"{methode} {pfad} war fuer Mitglieder offen"


@pytest.mark.parametrize("muster,pfad,noetig", [f for f in FORMULARE if f[2] != "angemeldet"])
def test_mitglied_darf_keine_admin_formulare(mitglied, muster, pfad, noetig):
    assert mitglied.post(pfad, data={}).status_code == 403


def test_mitglied_sieht_kein_admin_panel(mitglied):
    for pfad in ("/admin", "/admin/verlauf"):
        antwort = mitglied.get(pfad)
        assert antwort.status_code == 303
        assert antwort.headers["location"].startswith("/app")


# ── Admin gegen Owner-Rechte ──────────────────────────────────────────
@pytest.mark.parametrize("muster,pfad,noetig", NUR_OWNER)
def test_admin_darf_keine_owner_sachen(admin, muster, pfad, noetig):
    assert admin.post(pfad, data={}).status_code == 403


def test_admin_kann_keine_admin_einladung_erstellen(admin):
    """Nur der Owner ernennt Admins. Ohne diese Schranke koennte sich jeder Admin
    ueber eine Einladung an sich selbst beliebig viele weitere Admins bauen."""
    antwort = admin.post("/admin/invites", data={"role": "admin", "note": "versuch"})
    assert antwort.status_code == 303
    assert "err=" in antwort.headers["location"]
    assert db.list_invites() == []


def test_owner_kann_admin_einladung_erstellen(owner):
    antwort = owner.post("/admin/invites", data={"role": "admin", "note": "fuer die Vertretung"})
    assert antwort.status_code == 303
    einladungen = db.list_invites()
    assert len(einladungen) == 1
    assert einladungen[0]["role"] == "admin"


def test_admin_kann_owner_nicht_sperren_oder_entmachten(admin, owner):
    """Der Owner ist der letzte Halt. Ein Admin darf ihn weder sperren noch loeschen."""
    antwort = admin.post(f"/admin/users/{owner.uid}/disable", data={"value": "1"})
    assert antwort.status_code == 303
    assert "err=" in antwort.headers["location"]
    assert db.get_user(owner.uid)["disabled"] == 0
    # Rolle aendern ist ohnehin owner-only (Dependency), hier nur zur Sicherheit:
    assert admin.post(f"/admin/users/{owner.uid}/role", data={"role": "member"}).status_code == 403


def test_owner_bleibt_owner(owner):
    """Auch der Owner selbst kann seine Rolle nicht per Formular abgeben, ohne sie
    vorher zu uebertragen - sonst stuende das Portal ohne Owner da."""
    antwort = owner.post(f"/admin/users/{owner.uid}/role", data={"role": "member"})
    assert antwort.status_code == 303
    assert "err=" in antwort.headers["location"]
    assert db.get_user(owner.uid)["role"] == "owner"


# ── verified-Durchsetzung beim Welten-Download ────────────────────────
def _welt_ablegen(tmp_path, name: str = "valheim.tar.gz") -> None:
    welten = tmp_path / "worlds"
    welten.mkdir(exist_ok=True)
    (welten / name).write_bytes(b"kein echtes tar, reicht fuer den Zugriffstest")
    settings.worlds_dir = str(welten)


def test_download_braucht_verifizierung(mitglied, verifiziert, tmp_path):
    _welt_ablegen(tmp_path)
    assert mitglied.get("/api/worlds/valheim/download").status_code == 403
    erlaubt = verifiziert.get("/api/worlds/valheim/download")
    assert erlaubt.status_code == 200
    assert erlaubt.headers["content-type"] == "application/gzip"


def test_admin_darf_auch_unverifiziert_herunterladen(tmp_path):
    """`can_download` ist bewusst `verified OR is_admin` - ein Admin, den niemand
    gesondert verifiziert hat, kommt trotzdem an die Spielstaende."""
    _welt_ablegen(tmp_path)
    sitzung = anmelden(konto("unverifizierte-chefin", rolle="admin"), "unverifizierte-chefin")
    assert sitzung.get("/api/worlds/valheim/download").status_code == 200


def test_download_wird_protokolliert(verifiziert, tmp_path):
    """Wer einen fremden Spielstand herunterlaedt, hinterlaesst eine Zeile. Ohne
    sie waere der Abfluss ganzer Welten der einzige Vorgang ohne Spur."""
    _welt_ablegen(tmp_path)
    assert verifiziert.get("/api/worlds/valheim/download").status_code == 200
    arten = [e["action"] for e in db.recent_events(10)]
    assert "world.download" in arten


# ── Mitglied darf, was es darf ────────────────────────────────────────
def test_mitglied_darf_starten(mitglied, bruecke):
    antwort = mitglied.post("/api/games/valheim/start")
    assert antwort.status_code == 200
    assert antwort.json()["outcome"] == "ok"
    assert bruecke.zuletzt() == ("post_action", "start", "valheim", None)


def test_gesperrtes_konto_kommt_nicht_mehr_rein(mitglied):
    assert mitglied.get("/api/me").status_code == 200
    db.set_disabled(mitglied.uid, True)
    # Dieselbe Session, dasselbe Cookie: die Sperre muss sofort greifen.
    assert mitglied.get("/api/me").status_code == 401


def test_keine_route_vergessen():
    """Jede Route der App steht in einer der Tabellen oben.

    Ohne diese Probe waechst die App an den Rollentests vorbei: ein neuer
    Endpunkt ist einfach nicht getestet, und nichts faellt auf.
    """
    bekannt = ({m for _, m, _, _ in API_ROUTEN} | {m for m, _, _ in FORMULARE}
               | {p for p, _ in SEITEN})
    # Bewusst ausgenommen: Technik ohne Rollenbezug, der oeffentliche Einloesepfad
    # (eigene Datei) und die Token-Endpunkte der Gaming-Automatik - die haengen an
    # einem Bearer statt an einer Rolle und werden in test_gaming_automatik geprueft.
    ausgenommen = {"/health", "/static", "/join/{code}",
                   "/api/gaming/abgleich", "/api/gaming/dm-vermerk",
                   "/api/gaming/dm-erledigt", "/api/gaming/ruecknahme"}
    fehlt = sorted({getattr(r, "path", "") for r in app.routes}
                   - bekannt - ausgenommen - {""})
    assert not fehlt, f"Diese Routen stehen in keiner Rollentabelle: {fehlt}"
