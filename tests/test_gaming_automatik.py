"""Gaming-Rollen-Automatik: der einzige Endpunkt ohne Sitzung.

Hier legt ein Bot Konten an und sperrt sie wieder. Der Zugang haengt allein an
einem Bearer-Token, nicht an einer Rolle - entsprechend genau wird geprueft, dass
ohne Token nichts geht und dass die eingebauten Sicherungen halten: von Hand
angelegte Konten bleiben unberuehrt, eine unvollstaendige Liste sperrt niemanden,
und oberhalb des Deckels bricht der Abgleich lieber ab.
"""
from __future__ import annotations

import pytest

from app import db
from app.config import settings
from tests.conftest import _hash, konto

TOKEN = "gaming-pruef-token"
ENDPUNKTE = ["/api/gaming/abgleich", "/api/gaming/dm-vermerk",
             "/api/gaming/dm-erledigt", "/api/gaming/ruecknahme"]


@pytest.fixture
def automatik(monkeypatch, anonym):
    monkeypatch.setattr(settings, "provision_token", TOKEN)
    return anonym


def _abgleich(client, mitglieder, vollstaendig=True, token=TOKEN):
    kopf = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/gaming/abgleich", headers=kopf,
                       json={"mitglieder": mitglieder, "vollstaendig": vollstaendig})


def _automatik_konto(name: str, discord_id: str, disabled: bool = False) -> int:
    uid = db.create_user(name, name, _hash("egal"), role="member",
                         discord_id=discord_id, discord_name=name, auto_gaming=True)
    if disabled:
        db.set_disabled(uid, True)
    return uid


# ── Ohne Token laeuft gar nichts ──────────────────────────────────────
@pytest.mark.parametrize("pfad", ENDPUNKTE)
def test_ohne_eingerichtete_automatik_503(anonym, pfad):
    """Leerer `provision_token` heisst: Automatik aus. Dann darf der Endpunkt
    nicht etwa offen sein, sondern muss ehrlich absagen."""
    antwort = anonym.post(pfad, headers={"Authorization": "Bearer irgendwas"}, json={})
    assert antwort.status_code == 503


@pytest.mark.parametrize("pfad", ENDPUNKTE)
def test_ohne_kopfzeile_401(automatik, pfad):
    assert automatik.post(pfad, json={}).status_code == 401


@pytest.mark.parametrize("pfad", ENDPUNKTE)
def test_falscher_token_401(automatik, pfad):
    antwort = automatik.post(pfad, headers={"Authorization": "Bearer falsch"}, json={})
    assert antwort.status_code == 401


def test_falsches_schema_401(automatik):
    for kopf in (TOKEN, f"Basic {TOKEN}", f"Token {TOKEN}", "Bearer", "Bearer "):
        antwort = automatik.post("/api/gaming/abgleich",
                                 headers={"Authorization": kopf}, json={})
        assert antwort.status_code == 401, f"„{kopf}" + "“ kam durch"


def test_grossschreibung_des_schemas_ist_egal(automatik):
    antwort = automatik.post("/api/gaming/abgleich",
                             headers={"Authorization": f"bearer {TOKEN}"},
                             json={"mitglieder": [], "vollstaendig": True})
    assert antwort.status_code == 200


# ── Anlegen ───────────────────────────────────────────────────────────
def test_neues_mitglied_bekommt_ein_konto(automatik):
    antwort = _abgleich(automatik, [{"discord_id": "111", "name": "spieler.eins",
                                     "anzeige": "Spieler Eins"}])
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["ok"] is True
    assert len(daten["neu"]) == 1
    neu = daten["neu"][0]
    # Der Punkt aus dem Discord-Namen ist kein zulaessiges Zeichen und wird ersetzt.
    assert neu["nutzer"] == "spieler_eins"
    assert neu["passwort"]

    konto_zeile = db.get_user_by_discord("111")
    assert konto_zeile["auto_gaming"] == 1
    assert konto_zeile["role"] == "member"
    assert konto_zeile["verified"] == 0
    assert konto_zeile["password_hash"].startswith("$argon2id$"), "Passwort nicht gehasht"


def test_zweiter_durchgang_legt_nichts_doppelt_an(automatik):
    mitglieder = [{"discord_id": "111", "name": "spielerin"}]
    _abgleich(automatik, mitglieder)
    zweite = _abgleich(automatik, mitglieder).json()
    assert zweite["neu"] == []
    assert zweite["unveraendert"] == 1
    assert db.count_users() == 1


def test_eintrag_ohne_discord_id_wird_uebersprungen(automatik):
    antwort = _abgleich(automatik, [{"name": "ohne-id"}, {"discord_id": "", "name": "leer"}])
    assert antwort.json()["neu"] == []
    assert db.count_users() == 0


def test_mitglieder_muss_eine_liste_sein(automatik):
    antwort = automatik.post("/api/gaming/abgleich",
                             headers={"Authorization": f"Bearer {TOKEN}"},
                             json={"mitglieder": {"discord_id": "1"}, "vollstaendig": True})
    assert antwort.status_code == 400


# ── Sperren ───────────────────────────────────────────────────────────
def test_verlorene_rolle_sperrt_das_konto(automatik):
    uid = _automatik_konto("weggefallen", "222")
    token, _ = db.create_session(uid, "quelle-test", "pytest")
    ergebnis = _abgleich(automatik, []).json()
    assert [g["nutzer"] for g in ergebnis["gesperrt"]] == ["weggefallen"]
    assert db.get_user(uid)["disabled"] == 1
    assert db.get_session(token) is None, "die laufende Sitzung blieb offen"


def test_handkonten_bleiben_unberuehrt(automatik):
    """Owner und Admins tragen die Discord-Rolle gar nicht. Ohne die
    auto_gaming-Grenze haette der erste Abgleich genau sie ausgesperrt."""
    eigner = konto("eigner", rolle="owner")
    chefin = konto("chefin", rolle="admin")
    von_hand = konto("handgemacht")
    db.set_discord(von_hand, "333", "handgemacht")

    ergebnis = _abgleich(automatik, []).json()
    assert ergebnis["gesperrt"] == []
    for uid in (eigner, chefin, von_hand):
        assert db.get_user(uid)["disabled"] == 0


def test_admin_mit_automatik_kennzeichen_wird_nicht_gesperrt(automatik):
    """Zweite Schranke: selbst ein Konto mit `auto_gaming` wird nur gesperrt,
    solange es die Rolle `member` hat. Wer befoerdert wurde, bleibt drin."""
    uid = _automatik_konto("befoerdert", "444")
    db.set_role(uid, "admin")
    assert _abgleich(automatik, []).json()["gesperrt"] == []
    assert db.get_user(uid)["disabled"] == 0


def test_unvollstaendige_liste_sperrt_niemanden(automatik):
    """Der Bot konnte die Mitgliederliste nicht sicher erheben. Dann wird nur
    angelegt und entsperrt - und die ausgesetzten Sperrungen werden gemeldet,
    damit „keine Meldung" nicht wie „nichts zu tun" aussieht."""
    uid = _automatik_konto("unklar", "555")
    ergebnis = _abgleich(automatik, [], vollstaendig=False).json()
    assert ergebnis["gesperrt"] == []
    assert ergebnis["sperren_ausgesetzt"] == 1
    assert db.get_user(uid)["disabled"] == 0
    arten = [e["action"] for e in db.recent_events(10)]
    assert "abgleich.sperren_ausgesetzt" in arten


def test_deckel_bricht_den_abgleich_ab(automatik, monkeypatch):
    """Mehr Sperrungen als der Deckel erlaubt heisst fast immer: die Liste ist
    kaputt, nicht der Clan aufgeloest. Dann lieber nichts tun und melden."""
    monkeypatch.setattr(settings, "provision_max_sperren", 2)
    for i in range(3):
        _automatik_konto(f"weg-{i}", f"60{i}")
    ergebnis = _abgleich(automatik, []).json()
    assert ergebnis["ok"] is False
    assert ergebnis["zu_sperren"] == 3
    assert all(db.get_user_by_discord(f"60{i}")["disabled"] == 0 for i in range(3))
    arten = [e["action"] for e in db.recent_events(10)]
    assert "abgleich.abgebrochen" in arten


def test_rolle_zurueck_entsperrt_ohne_neues_passwort(automatik):
    uid = _automatik_konto("rueckkehrerin", "777", disabled=True)
    alter_hash = db.get_user(uid)["password_hash"]
    ergebnis = _abgleich(automatik, [{"discord_id": "777", "name": "rueckkehrerin"}]).json()
    assert [e["nutzer"] for e in ergebnis["entsperrt"]] == ["rueckkehrerin"]
    assert db.get_user(uid)["disabled"] == 0
    assert db.get_user(uid)["password_hash"] == alter_hash
    assert ergebnis["neu"] == []


# ── Ruecknahme nicht zustellbarer Konten ──────────────────────────────
def test_ruecknahme_entfernt_nur_ungenutzte_konten(automatik):
    frisch = _automatik_konto("nie-benutzt", "888")
    benutzt = _automatik_konto("schon-drin", "999")
    db.touch_login(benutzt)

    antwort = automatik.post("/api/gaming/ruecknahme",
                             headers={"Authorization": f"Bearer {TOKEN}"},
                             json={"discord_ids": ["888", "999"], "grund": "DM nicht zustellbar"})
    assert antwort.status_code == 200
    assert antwort.json()["entfernt"] == ["nie-benutzt"]
    assert db.get_user(frisch) is None
    assert db.get_user(benutzt) is not None


def test_zurueckgenommene_id_wird_nicht_neu_angelegt(automatik):
    """Ohne Merkzettel legt der naechste Durchgang dasselbe Konto wieder an und
    nimmt es wieder zurueck - eine Schleife samt Meldung im Admin-Kanal."""
    _automatik_konto("einmal", "888")
    automatik.post("/api/gaming/ruecknahme", headers={"Authorization": f"Bearer {TOKEN}"},
                   json={"discord_ids": ["888"]})
    ergebnis = _abgleich(automatik, [{"discord_id": "888", "name": "einmal"}]).json()
    assert ergebnis["neu"] == []
    assert ergebnis["uebergangen"] == 1
    assert db.get_user_by_discord("888") is None


# ── Merkzettel fuer den Admin-Bereich ─────────────────────────────────
def test_stand_wird_vermerkt(automatik):
    """Ohne diesen Eintrag ist „keine Meldung" nicht von „laeuft nicht mehr" zu
    unterscheiden."""
    _abgleich(automatik, [{"discord_id": "111", "name": "wer-auch-immer"}])
    stand = db.hole_stand("gaming_abgleich")
    assert stand is not None
    import json
    werte = json.loads(stand["wert"])
    assert werte["traeger"] == 1
    assert werte["neu"] == 1
    assert werte["vollstaendig"] is True
