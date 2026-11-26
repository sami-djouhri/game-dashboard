"""Server-Updates auf der Admin-Seite (2026-11-22).

Sehen duerfen Admins, ausloesen nur der Owner: ein Update veraendert den Spielstand mit,
und die Bridge nimmt es ohnehin nur mit dem Owner-Token an. Ein Knopf erscheint nur bei
Spielen mit automatischem Weg, sonst bietet die Seite etwas an, das das Werkzeug ablehnt.
"""
from __future__ import annotations

from app import bridge, db

STAND = {"gemessen": "2026-11-22T04:48:33Z", "spiele": [
    {"name": "valheim", "weg": "steam", "automatisch": True, "installiert": "1",
     "aktuell": "2", "hinterher": False, "mods_hinterher": [], "hinweis": "", "update": None},
    {"name": "factorio", "weg": "factorio", "automatisch": True, "installiert": "2.0.77",
     "aktuell": "2.1.24", "hinterher": True, "mods_hinterher": [], "hinweis": "",
     "update": {"laeuft": False, "start": 1795000000, "ende": 1795000300, "rc": 1,
                "wer": "chef", "abgebrochen": False, "log": ["FEHLER beim Update: Token"]}},
    {"name": "dayz", "weg": "steam", "automatisch": False, "installiert": "24570360",
     "aktuell": "26220720", "hinterher": True, "mods_hinterher": [],
     "hinweis": "laedt nicht anonym", "update": None},
]}


def test_mitglied_kommt_nicht_hinein(mitglied, bruecke):
    r = mitglied.get("/admin/updates", follow_redirects=False)
    assert r.status_code == 303
    assert not bruecke.kam_an("get_updates")


def test_admin_sieht_den_stand_aber_keinen_knopf(admin, bruecke):
    bruecke.updates = STAND
    r = admin.get("/admin/updates")
    assert r.status_code == 200
    assert "2.1.24" in r.text and "veraltet" in r.text
    assert "Update einspielen" not in r.text
    assert "laedt nicht anonym" in r.text


def test_owner_bekommt_knoepfe_nur_bei_automatischem_weg(owner, bruecke):
    bruecke.updates = STAND
    r = owner.get("/admin/updates")
    assert r.text.count("Update einspielen") == 2
    assert 'action="/admin/updates/dayz"' not in r.text
    assert 'action="/admin/updates/factorio"' in r.text


def test_veraltete_stehen_oben(owner, bruecke):
    bruecke.updates = STAND
    r = owner.get("/admin/updates")
    assert r.text.index("Factorio") < r.text.index("Valheim")


def test_laufendes_update_hat_keinen_knopf_und_laedt_neu(owner, bruecke):
    stand = {"gemessen": None, "spiele": [dict(STAND["spiele"][0], update={
        "laeuft": True, "start": 1795000000, "rc": None, "ende": None, "wer": "chef",
        "abgebrochen": False, "log": ["Welt-Schnappschuss anlegen"]})]}
    bruecke.updates = stand
    r = owner.get("/admin/updates")
    assert "Update einspielen" not in r.text
    assert "läuft seit" in r.text
    assert 'http-equiv="refresh"' in r.text


def test_admin_darf_kein_update_starten(admin, bruecke):
    r = admin.post("/admin/updates/valheim", follow_redirects=False)
    assert r.status_code == 403
    assert not bruecke.kam_an("start_update")


def test_owner_startet_und_es_steht_im_verlauf(owner, bruecke):
    r = owner.post("/admin/updates/valheim", follow_redirects=False)
    assert r.status_code == 303
    assert bruecke.zuletzt() == ("start_update", "valheim", owner.username)
    assert any(e["action"] == "game.update" for e in db.recent_events(5))


def test_ohne_csrf_kein_start(owner, bruecke):
    r = owner.roh_post("/admin/updates/valheim", data={"csrf": "falsch"}, follow_redirects=False)
    assert r.status_code in (400, 403)
    assert not bruecke.kam_an("start_update")


def test_unsauberer_spielname_geht_nicht_an_die_bridge(owner, bruecke):
    r = owner.post("/admin/updates/VALHEIM..x", follow_redirects=False)
    assert r.status_code == 303
    assert not bruecke.kam_an("start_update")


def test_bridge_weg_zeigt_hinweis_statt_fehlerseite(owner, monkeypatch):
    async def kaputt():
        raise RuntimeError("weg")
    monkeypatch.setattr(bridge, "get_updates", kaputt)
    r = owner.get("/admin/updates")
    assert r.status_code == 200
    assert "Stand nicht abrufbar" in r.text
