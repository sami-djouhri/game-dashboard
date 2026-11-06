"""Sicherungen auf der Clan-Seite (Vorgabe 2026-10-04).

Admins legen an und spielen ein, loeschen kann nur der Owner, und jeder Stand ist fuer
Admins herunterladbar. Der Download liefert ausschliesslich, was der Arbiter fuer das
Spiel selbst auflistet, nie einen Pfad aus der Anfrage.
"""
from __future__ import annotations

from app import bridge
from app.config import settings


def _liste(monkeypatch, dateien):
    async def list_snapshots(game):
        return {"snapshots": [{"file": f} for f in dateien]}
    monkeypatch.setattr(bridge, "list_snapshots", list_snapshots)


def test_admin_darf_sicherung_nicht_loeschen(admin, bruecke):
    r = admin.post("/api/games/valheim/snapshots/delete", json={"file": "taeglich/valheim/valheim-20261001-041500.tar.gz"})
    assert r.status_code == 403
    assert not bruecke.kam_an("delete_snapshot")


def test_admin_darf_welt_nicht_loeschen(admin, bruecke):
    r = admin.post("/api/games/terraria/worlds/delete", json={"id": "testwelt"})
    assert r.status_code == 403
    assert not bruecke.kam_an("delete_world")


def test_owner_darf_loeschen(owner, bruecke):
    r = owner.post("/api/games/valheim/snapshots/delete", json={"file": "taeglich/valheim/valheim-20261001-041500.tar.gz"})
    assert r.status_code == 200
    assert bruecke.zuletzt()[0] == "delete_snapshot"


def test_admin_sicherung_traegt_den_nutzer(admin, bruecke):
    admin.post("/api/games/valheim/snapshot")
    assert bruecke.zuletzt()[3:] == (admin.username, False)


def test_admin_laedt_alten_stand(admin, monkeypatch, tmp_path):
    rel = "taeglich/valheim/valheim-20260910-041500.tar.gz"
    (tmp_path / "taeglich" / "valheim").mkdir(parents=True)
    (tmp_path / rel).write_bytes(b"\x1f\x8bINHALT")
    monkeypatch.setattr(settings, "saves_dir", str(tmp_path))
    _liste(monkeypatch, [rel])
    r = admin.get("/api/games/valheim/snapshots/download", params={"file": rel})
    assert r.status_code == 200
    assert r.content == b"\x1f\x8bINHALT"


def test_download_nur_was_der_arbiter_listet(admin, monkeypatch, tmp_path):
    """Eine Datei, die zwar im Verzeichnis liegt, aber nicht zu diesem Spiel gelistet
    ist, wird nicht geliefert: die Liste ist die Erlaubnis, nicht das Dateisystem."""
    rel = "taeglich/dayz/dayz-20260910-041500.tar.gz"
    (tmp_path / "taeglich" / "dayz").mkdir(parents=True)
    (tmp_path / rel).write_bytes(b"x")
    monkeypatch.setattr(settings, "saves_dir", str(tmp_path))
    _liste(monkeypatch, [])
    assert admin.get("/api/games/valheim/snapshots/download", params={"file": rel}).status_code == 404


def test_download_ohne_admin_verboten(verifiziert, monkeypatch):
    _liste(monkeypatch, ["valheim.tar.gz"])
    r = verifiziert.get("/api/games/valheim/snapshots/download", params={"file": "valheim.tar.gz"})
    assert r.status_code == 403


def test_einspielen_geht_mit_laufend_an_die_bridge(monkeypatch):
    """Das Dashboard spielt auch bei laufendem Server ein (Vorgabe 2026-10-04); dafuer
    muss ?laufend=1 an der Bridge ankommen, sonst lehnt der Arbiter mit rc 4 ab."""
    import asyncio
    import importlib
    import app.bridge as echt
    echt = importlib.reload(echt)
    pfade = []

    async def post(path, json_body=None, timeout=None, owner=False, wer=None):
        pfade.append((path, owner, wer))
        return "ok", "fertig"
    monkeypatch.setattr(echt, "_post_snapshot_api", post)
    asyncio.run(echt.restore_snapshot("valheim", "manuell/valheim/valheim-20261001-000000.tar.gz", wer="anna"))
    assert pfade == [("/restore/valheim?laufend=1", False, "anna")]
