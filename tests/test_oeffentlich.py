"""Was die oeffentliche Seite preisgibt - und was nicht.

Die Landing steht ohne Anmeldung im Netz. Sie darf werben, Live-Zahlen zeigen und
Bewerbungen annehmen; sie darf keine Beitritts-Adressen, keinen Bridge-Token und
keine Betriebs-Interna des Wirts herausgeben.
"""
from __future__ import annotations

import httpx
import pytest

from app import bridge, games
from app.config import settings

ADRESSEN = games.adress_bausteine()


def _ohne_adressen(text: str) -> bool:
    return not any(a in text for a in ADRESSEN)


# ── Adressen erst nach der Anmeldung ──────────────────────────────────
@pytest.mark.parametrize("pfad", ["/", "/guides", "/apply", "/impressum", "/datenschutz"])
def test_oeffentliche_seiten_nennen_keine_serveradresse(anonym, pfad):
    antwort = anonym.get(pfad)
    assert antwort.status_code == 200
    assert _ohne_adressen(antwort.text), f"{pfad} zeigt anonym eine Beitritts-Adresse"


def test_mitglieder_sehen_die_adressen(mitglied):
    """Die Gegenprobe zur Maskierung: waeren die Adressen auch angemeldet weg,
    liefe der Test oben ins Leere und niemand kaeme auf die Server."""
    text = mitglied.get("/guides").text
    assert any(a in text for a in ADRESSEN), "auch angemeldet stand keine Adresse da"


def test_mods_bleiben_auch_anonym_sichtbar(anonym):
    """Bewusste Entscheidung: was gespielt wird, ist kein Geheimnis - genau das
    will jemand vor dem Bewerben wissen."""
    antwort = anonym.get("/guides")
    assert antwort.status_code == 200
    assert "Mod" in antwort.text


# ── Der oeffentliche Status ist reduziert ─────────────────────────────
def test_public_status_zeigt_keine_interna(anonym):
    daten = anonym.get("/api/public/status").json()
    assert set(daten) <= {"online_total", "active_game", "active_label", "games", "ok", "arbiter_ok"}
    for feld in ("ram", "lab", "registry", "bedarf", "reserved_all", "detail"):
        assert feld not in daten, f"„{feld}" + "“ steht im oeffentlichen Status"
    for kachel in daten["games"]:
        assert "address" not in kachel and "join" not in kachel


def test_public_status_kennt_keine_adressen(anonym):
    assert _ohne_adressen(anonym.get("/api/public/status").text)


def test_mitglieder_status_zeigt_die_rolle(mitglied, admin):
    assert mitglied.get("/api/status").json()["is_admin"] is False
    assert admin.get("/api/status").json()["is_admin"] is True


# ── Der Bridge-Token bleibt serverseitig ──────────────────────────────
@pytest.mark.parametrize("pfad", ["/", "/guides", "/api/public/status"])
def test_kein_bridge_token_nach_aussen(anonym, pfad):
    assert settings.game_bridge_token, "ohne gesetzten Token prueft dieser Test nichts"
    assert settings.game_bridge_token not in anonym.get(pfad).text


def test_kein_bridge_token_fuer_angemeldete(admin):
    for pfad in ("/app", "/admin", "/api/status", "/api/me"):
        text = admin.get(pfad).text
        assert settings.game_bridge_token not in text, f"{pfad} enthielt den Bridge-Token"
        assert settings.game_bridge_url not in text


# ── Ausfall der Steuerung ─────────────────────────────────────────────
def test_seite_bleibt_stehen_wenn_die_bridge_schweigt(anonym, mitglied, monkeypatch):
    """Faellt die wake-bridge aus, darf die Seite nicht leer wirken: „nichts
    laeuft" waere die falsche Auskunft. Sie meldet stattdessen `arbiter_ok=false`.
    """
    async def kaputt():
        raise httpx.ConnectError("keine Verbindung")

    monkeypatch.setattr(bridge, "get_status", kaputt)

    oeffentlich = anonym.get("/api/public/status")
    assert oeffentlich.status_code == 200
    assert oeffentlich.json()["arbiter_ok"] is False

    intern = mitglied.get("/api/status")
    assert intern.status_code == 200
    assert intern.json()["arbiter_ok"] is False
    assert anonym.get("/").status_code == 200


def test_steuerbefehl_bei_toter_bridge_meldet_503(mitglied, monkeypatch):
    async def kaputt():
        raise httpx.ConnectError("keine Verbindung")

    monkeypatch.setattr(bridge, "get_status", kaputt)
    antwort = mitglied.post("/api/games/valheim/start")
    assert antwort.status_code == 503


def test_unbekanntes_spiel_wird_abgewiesen(admin, bruecke):
    """Der Game-Schluessel landet im Aufruf an die Bridge. Erlaubt ist nur, was
    in der Arbiter-Registry steht."""
    for unfug in ("gibtsnicht", "../etc", "valheim;id", "VALHEIM"):
        antwort = admin.post(f"/api/games/{unfug}/stop")
        assert antwort.status_code in (404, 405), f"„{unfug}" + "“ kam durch"
    assert not bruecke.kam_an("post_action")


def test_welt_muss_in_der_registry_stehen(admin, bruecke):
    ok = admin.post("/api/games/terraria/switch", params={"world": "testwelt"})
    assert ok.status_code == 200

    unbekannt = admin.post("/api/games/terraria/switch", params={"world": "fremdwelt"})
    assert unbekannt.status_code == 404

    ohne_welten = admin.post("/api/games/valheim/switch", params={"world": "greenleaf"})
    assert ohne_welten.status_code == 400
    assert sum(1 for a in bruecke.aufrufe if a[0] == "post_action") == 1


# ── Keine API-Dokumentation nach aussen ───────────────────────────────
@pytest.mark.parametrize("pfad", ["/docs", "/redoc", "/openapi.json"])
def test_keine_api_doku(anonym, pfad):
    """Die Seite steht oeffentlich; eine vollstaendige Endpunktliste waere eine
    Einladung, sie durchzuprobieren."""
    assert anonym.get(pfad).status_code == 404


def test_health_verraet_nichts(anonym):
    daten = anonym.get("/health").json()
    assert daten["status"] == "ok"
    assert set(daten) == {"status", "service", "version", "time"}
