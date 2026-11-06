"""Der Aktivitaets-Streifen auf der Kachel: was er zaehlt und was nicht.

Geprueft wird die Lesefunktion `db.aktivitaet_je_spiel` und die Zusicherung,
dass die Werte NICHT auf der oeffentlichen Seite landen.

Die Zeit wird hier festgehalten (`now_utc` gepatcht), nicht umschifft. Die
eine Entscheidung, die diese Funktion ueberhaupt treffen muss, ist die zwischen
UTC und Ortszeit; ein Test, der mit „jetzt" rechnet, wuerde genau dort je nach
Uhrzeit des Laufs mal gruen und mal rot sein.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import db
from tests.conftest import anmelden, konto

# Mitten im Sommer: Berlin liegt dann zwei Stunden vor UTC. Im Winter ist es
# eine, die Richtung bleibt dieselbe -- deshalb genuegt ein Zeitpunkt.
JETZT = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def feste_zeit(monkeypatch):
    monkeypatch.setattr(db, "now_utc", lambda: JETZT)


def _sitzung(game: str, start_utc: str, minuten: float = 60.0, peak: int = 2) -> None:
    """Eine abgeschlossene Spielsitzung direkt in die Tabelle schreiben.

    Direkt per SQL und nicht ueber `open_play_session`: dessen Zeitstempel
    kaeme aus `now_iso()`, und gerade der Zeitpunkt ist hier der Pruefgegenstand.
    """
    db._exec("INSERT INTO play_sessions(game,world,started_at,ended_at,peak_players,"
             "player_minutes) VALUES(?,?,?,?,?,?)",
             (game, "greenleaf", start_utc, start_utc, peak, minuten))


def test_nach_mitternacht_zaehlt_zum_neuen_tag(feste_zeit):
    """Der Fall, fuer den die Zonenrechnung da ist.

    23:30 UTC ist in Berlin bereits 01:30 des Folgetags. Eine Runde, die nach
    Mitternacht laeuft, gehoert auf den Tag, an dem die Spieler sie erlebt
    haben. Ohne Umrechnung landete sie einen Balken zu weit links, und das
    sieht im Bild vollkommen richtig aus.
    """
    _sitzung("valheim", "2026-07-15T23:30:00+00:00")
    tage = db.aktivitaet_je_spiel(14)["valheim"]["tage"]

    assert tage[-1] > 0, "01:30 Ortszeit gehoert auf HEUTE, nicht auf gestern"
    assert tage[-2] == 0, "der Vortag darf diese Sitzung nicht auch noch tragen"


def test_abend_bleibt_auf_seinem_tag(feste_zeit):
    """Gegenprobe: ein Abend VOR Mitternacht darf nicht verschoben werden.

    Ohne diese zweite Richtung wuerde ein Test auch dann gruen, wenn jemand
    pauschal einen Tag addiert, statt die Zone zu rechnen.
    """
    _sitzung("valheim", "2026-07-15T19:00:00+00:00")       # Berlin 21:00, Vortag
    tage = db.aktivitaet_je_spiel(14)["valheim"]["tage"]

    assert tage[-2] > 0 and tage[-1] == 0


def test_ohne_spieler_kein_balken(feste_zeit):
    """Ein geweckter, nie betretener Server ist keine Aktivitaet.

    Sonst behauptete der Streifen genau das Gegenteil dessen, wofuer er da ist:
    dass hier jemand war.
    """
    _sitzung("valheim", "2026-07-16T09:00:00+00:00", peak=0, minuten=0)
    assert "valheim" not in db.aktivitaet_je_spiel(14)


def test_zuletzt_nennt_die_juengste_sitzung(feste_zeit):
    _sitzung("valheim", "2026-07-10T12:00:00+00:00")
    _sitzung("valheim", "2026-07-15T12:00:00+00:00")
    zuletzt_s = db.aktivitaet_je_spiel(14)["valheim"]["zuletzt_s"]

    assert 86000 < zuletzt_s < 87000, "erwartet rund 24 h, nicht sechs Tage"


def test_aelter_als_der_zeitraum_faellt_raus(feste_zeit):
    _sitzung("valheim", "2026-06-01T12:00:00+00:00")
    assert "valheim" not in db.aktivitaet_je_spiel(14)


def test_mitglied_bekommt_den_streifen_fuer_jede_kachel():
    """Auch Kacheln OHNE jede Sitzung tragen das Feld.

    Der Leerzustand ist die Aussage „in zwei Wochen niemand" und damit genau
    die Auskunft, fuer die der Streifen gebaut wurde. Faellt das Feld dort weg,
    fehlt er ausgerechnet auf den Kacheln, bei denen man ihn braucht.
    """
    s = anmelden(konto("streifenleser"), "streifenleser")
    kacheln = s.get("/api/status").json()["games"]

    assert kacheln, "ohne Kacheln prueft dieser Test nichts"
    for k in kacheln:
        assert "aktivitaet" in k, f"{k['key']} ohne Aktivitaets-Feld"
        assert len(k["aktivitaet"]["tage"]) == 14


def test_oeffentlich_ohne_spielzeiten(anonym):
    """Die Zusicherung, die den Streifen vom Rest unterscheidet.

    Wer wann gespielt hat, ist bei einer Runde von acht Leuten auf
    Tagesaufloesung ein Anwesenheitsprotokoll. Die oeffentliche Seite bekommt
    deshalb nur das grob gestaffelte „zuletzt gespielt", das weder Spiel noch
    Uhrzeit nennt.
    """
    daten = anonym.get("/api/public/status").json()

    assert "aktivitaet" not in str(daten), "Spielzeiten gehoeren nicht nach draussen"
    for kachel in daten.get("games", []):
        assert "aktivitaet" not in kachel
