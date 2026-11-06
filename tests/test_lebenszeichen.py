"""Die Zeile „zuletzt gespielt" auf der oeffentlichen Startseite.

Sie beantwortet die Frage, die die drei Zahlen darueber offenlassen: ist hier gerade
nur zufaellig nichts los, oder ist die Runde tot? Bis zum 2026-10-17 stand in beiden
Faellen dasselbe da („gerade ruhig, jederzeit weckbar").

Gespeist wird sie aus `play_sessions`, und die Tabelle haelt Benutzernamen. Die
Zeile ist damit die erste Stelle, an der etwas aus diesen Daten OEFFENTLICH steht,
und genau darum liegt der Schwerpunkt dieser Datei nicht auf der Formatierung,
sondern auf dem, was NICHT mitkommt: kein Name, kein Spiel, keine Uhrzeit.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import db
from app.routers.pages import _zuletzt_gespielt


def _session(vor_minuten: int, spieler: int = 2, wer: str = "maxmuster",
             spiel: str = "valheim") -> int:
    """Eine abgeschlossene Spielsitzung, die vor n Minuten begann."""
    sid = db.open_play_session(spiel, "greenleaf", wer)
    db._exec("UPDATE play_sessions SET started_at=?, peak_players=? WHERE id=?",
             (db.iso(db.now_utc() - timedelta(minutes=vor_minuten)), spieler, sid))
    return sid


# ── Was die Zeile verschweigen muss ───────────────────────────────────
def test_keine_namen_kein_spiel_keine_uhrzeit():
    _session(vor_minuten=200, wer="maxmuster", spiel="valheim")
    text = _zuletzt_gespielt()
    assert text, "es gab eine Sitzung, die Zeile blieb trotzdem leer"
    assert "maxmuster" not in text
    assert "valheim" not in text.lower() and "greenleaf" not in text.lower()
    assert ":" not in text, f"Uhrzeit in der oeffentlichen Zeile: {text!r}"


def test_landing_zeigt_die_zeile_ohne_anmeldung(anonym):
    _session(vor_minuten=200)
    text = anonym.get("/").text
    assert "zuletzt gespielt" in text
    assert "maxmuster" not in text


def test_landing_nennt_auch_hier_keinen_namen(anonym):
    """Gegenprobe mit einem Namen, der zufaellig nicht wie ein Name aussieht:
    waere das Feld `ausgeloest_von` versehentlich durchgereicht, faende man es nur
    mit einer Zeichenfolge, die sonst nirgends im Dokument steht."""
    _session(vor_minuten=90, wer="zzqqxx")
    assert "zzqqxx" not in anonym.get("/").text


# ── Leerzustand: nichts behaupten ─────────────────────────────────────
def test_ohne_daten_bleibt_die_zeile_weg(anonym):
    """Kein „vor 0 min", kein Strich: die Zaehlung beginnt am Tag ihrer Einfuehrung,
    nicht am Tag des ersten Spiels. Eine Null waere hier eine falsche Auskunft."""
    assert _zuletzt_gespielt() == ""
    assert "zuletzt gespielt" not in anonym.get("/").text


def test_geweckt_aber_nie_betreten_zaehlt_nicht():
    """Der Grund fuer `peak_players > 0`. Ein Server, den jemand geweckt und nie
    betreten hat, hat ebenfalls eine Sitzung. Zaehlte sie mit, stuende „gerade eben
    gespielt" ausgerechnet dann da, wenn niemand gespielt hat."""
    _session(vor_minuten=5, spieler=0)
    assert _zuletzt_gespielt() == ""


def test_eine_leere_sitzung_verdeckt_keine_echte():
    """Die leere Sitzung ist die juengste, die echte liegt davor: gefragt ist die
    echte. Eine Abfrage nach schlicht `MAX(started_at)` faende die falsche."""
    _session(vor_minuten=300, spieler=4)
    _session(vor_minuten=2, spieler=0)
    assert _zuletzt_gespielt() == "vor 5 Stunden"


# ── Stufen der Ungenauigkeit ──────────────────────────────────────────
@pytest.mark.parametrize("minuten,erwartet", [
    (0, "gerade eben"),
    (19, "gerade eben"),
    (20, "vor 20 min"),
    (89, "vor 89 min"),
    # Einzahl: 90 bis 119 Minuten sind eine Stunde. Beim Hinschreiben dieser
    # Erwartung fiel auf, dass dort „vor 1 Stunden" stand -- im Code, nicht im Test.
    (90, "vor 1 Stunde"),
    (119, "vor 1 Stunde"),
    (120, "vor 2 Stunden"),
    (60 * 19, "vor 19 Stunden"),
    (60 * 20, "gestern"),
    (60 * 47, "gestern"),
    (60 * 48, "vor 2 Tagen"),
    (1440 * 13, "vor 13 Tagen"),
    (1440 * 14, "vor 2 Wochen"),
    (1440 * 59, "vor 8 Wochen"),
    (1440 * 60, "vor 2 Monaten"),
    (1440 * 400, "vor 13 Monaten"),
])
def test_stufen(minuten, erwartet):
    """Je laenger her, desto groeber -- und ab zwei Wochen bewusst so grob, dass die
    Zeile nichts mehr ueber einzelne Abende sagt."""
    _session(vor_minuten=minuten)
    assert _zuletzt_gespielt() == erwartet


def test_zukunft_wird_verschwiegen():
    """Wird die Uhr des Wirts zurueckgestellt, liegt ein Zeitstempel in der Zukunft.
    „vor -40 min" ist schlechter als gar keine Zeile."""
    _session(vor_minuten=-40)
    assert _zuletzt_gespielt() == ""


def test_unlesbarer_zeitstempel_bricht_die_seite_nicht(anonym):
    sid = _session(vor_minuten=10)
    db._exec("UPDATE play_sessions SET started_at=? WHERE id=?", ("kein-datum", sid))
    assert _zuletzt_gespielt() == ""
    assert anonym.get("/").status_code == 200
