"""CSRF-Schutz auf allen schreibenden Endpunkten.

Die Seite steht oeffentlich und arbeitet mit einem Sitzungs-Cookie. Ohne
CSRF-Token genuegte eine fremde Seite mit einem versteckten Formular, um im Namen
eines angemeldeten Admins Welten zu loeschen. Geprueft wird deshalb nicht ein
Beispiel, sondern JEDER schreibende Endpunkt: eine neue Route ohne `check_csrf`
faellt hier auf, nicht erst im Betrieb.

Ausgenommen sind die drei Endpunkte vor der Anmeldung (`/login`, `/apply`,
`/join/<code>`): dort gibt es noch keine Sitzung, an die ein Token gebunden
waere. Sie haengen an SameSite=Lax und den Bremsen in `test_bremsen.py`.
"""
from __future__ import annotations

import pytest

from app import db
from tests.conftest import anmelden, konto

# (Pfad, Pflichtfelder) - ohne die Pflichtfelder antwortet FastAPI mit 422,
# bevor `check_csrf` ueberhaupt laeuft, und der Test pruefte nichts.
FORMULARE = [
    ("/logout", {}),
    ("/account/password", {"current": "a", "new": "bbbbbbbb", "new2": "bbbbbbbb"}),
    ("/account/delete", {"password": "a"}),
    ("/admin/applications/1/approve", {}),
    ("/admin/applications/1/reject", {}),
    ("/admin/invites", {}),
    ("/admin/invites/1/revoke", {}),
    ("/admin/users/1/verify", {}),
    ("/admin/users/1/disable", {}),
    ("/admin/users/1/role", {}),
    ("/admin/users/1/delete", {}),
]

API_POSTS = [
    "/api/games/valheim/start",
    "/api/games/valheim/stop",
    "/api/games/valheim/restart",
    "/api/games/valheim/reserve",
    "/api/games/valheim/release",
    "/api/games/terraria/switch?world=testwelt",
    "/api/games/terraria/worlds",
    "/api/games/terraria/worlds/delete",
    "/api/games/valheim/snapshot",
    "/api/games/valheim/restore",
    "/api/games/valheim/snapshots/delete",
]


@pytest.mark.parametrize("pfad,pflicht", FORMULARE)
def test_formular_ohne_token_abgelehnt(owner, pfad, pflicht):
    antwort = owner.roh_post(pfad, data=dict(pflicht))
    assert antwort.status_code == 403, f"{pfad} nahm ein Formular ohne CSRF-Token an"


@pytest.mark.parametrize("pfad,pflicht", FORMULARE)
def test_formular_mit_falschem_token_abgelehnt(owner, pfad, pflicht):
    daten = dict(pflicht, csrf="ein-erfundenes-token")
    assert owner.roh_post(pfad, data=daten).status_code == 403


@pytest.mark.parametrize("pfad", API_POSTS)
def test_api_ohne_token_abgelehnt(owner, pfad):
    antwort = owner.roh_post(pfad, json={})
    assert antwort.status_code == 403, f"{pfad} nahm einen Aufruf ohne CSRF-Token an"


@pytest.mark.parametrize("pfad", API_POSTS)
def test_api_mit_falschem_token_abgelehnt(owner, pfad):
    antwort = owner.roh_post(pfad, json={}, headers={"X-CSRF-Token": "erfunden"})
    assert antwort.status_code == 403


def test_token_einer_fremden_sitzung_gilt_nicht(owner):
    """Das Token haengt an der Sitzung, nicht am Konto: wer eines aus einer anderen
    Anmeldung mitbringt, kommt nicht durch."""
    zweite = anmelden(konto("zweiter-admin", rolle="admin"), "zweiter-admin")
    assert zweite.csrf != owner.csrf
    antwort = owner.roh_post("/api/games/valheim/stop", json={},
                             headers={"X-CSRF-Token": zweite.csrf})
    assert antwort.status_code == 403


def test_richtiges_token_kommt_durch(owner, bruecke):
    assert owner.post("/api/games/valheim/stop").status_code == 200
    assert bruecke.zuletzt() == ("post_action", "stop", "valheim", None)


def test_token_nach_abmeldung_wertlos(mitglied):
    """Abmelden loescht die Sitzung serverseitig. Ein mitgeschriebenes Token darf
    danach nichts mehr bewirken, auch nicht mit dem alten Cookie."""
    assert mitglied.post("/logout").status_code == 303
    mitglied.client.cookies.set("gd_session", mitglied.token)
    assert mitglied.post("/api/games/valheim/start").status_code == 401
    assert db.get_session(mitglied.token) is None


def test_fremder_origin_wird_nur_vermerkt(owner, bruecke):
    """Bewusst dokumentiertes Verhalten: der Origin-Abgleich ist Beiwerk, kein
    Riegel. Hinter cloudflared und dev-portal weicht der Host regelmaessig vom
    oeffentlichen Namen ab, ein harter Vergleich wuerde echte Aufrufe abweisen.
    Wer das aendern will, aendert hier bewusst mit.
    """
    antwort = owner.post("/api/games/valheim/start",
                         headers={"Origin": "https://boeswillige-seite.example"})
    assert antwort.status_code == 200
    assert bruecke.kam_an("post_action")


def test_token_ist_zufaellig_und_lang():
    a = anmelden(konto("a-person"), "a-person")
    b = anmelden(konto("b-person"), "b-person")
    assert a.csrf != b.csrf
    assert len(a.csrf) >= 30
