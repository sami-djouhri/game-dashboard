"""Die Minecraft-Zusatzangaben der Kachel: drei Zustaende, nicht zwei.

Geprueft wird vor allem der UNBEKANNTE Fall. Ein fehlender Mount, eine
unlesbare Datei oder ein fehlendes Feld darf NICHT als Wert erscheinen: "Farmwelt
erneuert vor 0 Tagen" oder "0 Job-Staende gesichert" sieht wie eine Messung aus
und ist keine. Die Kachel soll dann nichts zeigen.

Die mtime-Zwischenablage ist mitgeprueft: sie ist der Grund, warum die Anzeige
nicht bei jedem Aufruf drei Dateien liest -- und sie ist auch die Stelle, an der
eine Aenderung haengenbleiben koennte.
"""
from __future__ import annotations

import json
import os
import time

import pytest


@pytest.fixture
def helfer(tmp_path, monkeypatch):
    """Ein Ordner wie der gemountete, mit frischem Modulzustand je Test."""
    import importlib

    monkeypatch.setenv("MC_HELFER_DIR", str(tmp_path))
    from app import mcfakten

    importlib.reload(mcfakten)
    return tmp_path, mcfakten


def schreibe(ordner, name, inhalt):
    (ordner / name).write_text(json.dumps(inhalt))


def test_ohne_mount_sagt_nichts(helfer):
    """Kein Ordner, keine Datei -- und vor allem keine erfundene Null."""
    _, mcfakten = helfer
    mcfakten.ORDNER = mcfakten.Path("/gibt/es/nicht")
    assert mcfakten.farmwelt() is None
    assert mcfakten.jobparkplatz() is None
    assert mcfakten.bonus() is None
    assert mcfakten.alles() == {}


def test_unlesbare_datei_sagt_nichts(helfer):
    ordner, mcfakten = helfer
    (ordner / "farmwelt-reset.json").write_text("{kein json")
    assert mcfakten.farmwelt() is None


def test_fehlendes_feld_sagt_nichts(helfer):
    """Die Datei gibt es, der Wert fehlt. Das ist nicht 'vor 0 Tagen'."""
    ordner, mcfakten = helfer
    schreibe(ordner, "farmwelt-reset.json", {"letztes_ergebnis": "unnoetig"})
    assert mcfakten.farmwelt() is None
    schreibe(ordner, "jobs-parkplatz.json", {"zeit": "egal"})
    assert mcfakten.jobparkplatz() is None


def test_null_als_zeitpunkt_sagt_nichts(helfer):
    """Eine 0 ist in Unixzeit der 1.1.1970 und nicht 'noch nie'."""
    ordner, mcfakten = helfer
    schreibe(ordner, "farmwelt-reset.json", {"letzter_reset": 0})
    assert mcfakten.farmwelt() is None


def test_farmwelt_rechnet_das_alter(helfer):
    ordner, mcfakten = helfer
    vor_zwei_tagen = int(time.time()) - 2 * 86400
    schreibe(ordner, "farmwelt-reset.json", {"letzter_reset": vor_zwei_tagen})
    f = mcfakten.farmwelt()
    assert f["reset_zeit"] == vor_zwei_tagen
    # Zwei Tage, mit einer Sekunde Spiel fuer die Laufzeit des Tests.
    assert 2 * 86400 - 5 <= f["reset_vor_s"] <= 2 * 86400 + 5


def test_zukunft_wird_nicht_negativ(helfer):
    """Eine Uhr, die springt, darf keine negative Dauer ergeben: 'vor -3 h'
    waere eine Zahl, die niemand erklaeren kann."""
    ordner, mcfakten = helfer
    schreibe(ordner, "farmwelt-reset.json", {"letzter_reset": int(time.time()) + 9999})
    assert mcfakten.farmwelt()["reset_vor_s"] == 0


def test_jobparkplatz_zaehlt_beide_mengen(helfer):
    ordner, mcfakten = helfer
    schreibe(ordner, "jobs-parkplatz.json",
             {"geparkt": {"a|miner": {}, "b|farmer": {}}, "vorgemerkt": {"c|chef": {}}})
    assert mcfakten.jobparkplatz() == {"geparkt": 2, "vorgemerkt": 1}


def test_bonus_faktor_eins_ist_ein_wert(helfer):
    """Faktor 1 heisst 'kein Bonus' und ist trotzdem eine Auskunft -- die Kachel
    entscheidet, ob sie ihn zeigt, nicht dieses Modul."""
    ordner, mcfakten = helfer
    schreibe(ordner, "jobs-bonus.json", {"faktor": 1, "gezahlt": 0})
    assert mcfakten.bonus() == {"faktor": 1, "gezahlt": 0}
    schreibe(ordner, "jobs-bonus.json", {"faktor": 4, "gezahlt": 1234})
    assert mcfakten.bonus() == {"faktor": 4, "gezahlt": 1234}


def test_faktor_unter_eins_ist_kein_faktor(helfer):
    ordner, mcfakten = helfer
    schreibe(ordner, "jobs-bonus.json", {"faktor": 0})
    assert mcfakten.bonus() is None


def test_alles_laesst_leere_schluessel_weg(helfer):
    ordner, mcfakten = helfer
    schreibe(ordner, "jobs-bonus.json", {"faktor": 2, "gezahlt": 5})
    erg = mcfakten.alles()
    assert set(erg) == {"bonus"}
    assert "farmwelt" not in erg   # kein null, der Schluessel fehlt ganz


def test_aenderung_kommt_durch_die_zwischenablage(helfer):
    """Die mtime-Zwischenablage darf eine Aenderung nicht verschlucken.
    Genau das war die Falle beim Single-File-Bindmount; hier ist es dieselbe
    Frage eine Schicht hoeher."""
    ordner, mcfakten = helfer
    schreibe(ordner, "jobs-bonus.json", {"faktor": 1})
    assert mcfakten.bonus()["faktor"] == 1
    schreibe(ordner, "jobs-bonus.json", {"faktor": 4})
    # mtime kann bei schnellen Schreibvorgaengen gleich bleiben -- deshalb wird
    # sie hier ausdruecklich vorgerueckt, wie es im Betrieb ohnehin passiert.
    os.utime(ordner / "jobs-bonus.json", (time.time() + 1, time.time() + 1))
    assert mcfakten.bonus()["faktor"] == 4


def test_kachel_traegt_die_fakten_nur_bei_minecraft(helfer):
    """Gegen die Verdrahtung in games.py: andere Spiele bekommen ein leeres Feld."""
    ordner, mcfakten = helfer
    schreibe(ordner, "jobs-bonus.json", {"faktor": 2})
    from app import games
    status = {
        "games": {"registry": ["minecraft", "valheim"], "reserved_all": [],
                  "detail": {}},
        "mc": {}, "lab": {}, "ram": {"avail_mb": 9000},
    }
    view = games.build_view(status, {}, True)
    nach_key = {g["key"]: g for g in view["games"]}
    assert nach_key["valheim"]["fakten"] == {}
    # Minecraft liest aus demselben Ordner -- die Verdrahtung ist der Punkt,
    # nicht der Inhalt.
    assert "fakten" in nach_key["minecraft"]


# ── Der naechste Reset (seit 2026-10-17) ──────────────────────────────
def test_naechster_reset_wird_als_restzeit_geliefert(helfer):
    """Die Kachel fragt nach vorn, nicht zurueck: wer in der Farmwelt abbaut, will
    wissen, wie viel Zeit ihm bleibt."""
    ordner, mcfakten = helfer
    jetzt = int(time.time())
    schreibe(ordner, "farmwelt-reset.json",
             {"letzter_reset": jetzt - 5 * 86400, "naechster_reset": jetzt + 2 * 86400})
    f = mcfakten.farmwelt()
    assert 2 * 86400 - 5 <= f["naechster_in_s"] <= 2 * 86400 + 5


def test_abgelaufener_termin_wird_weggelassen(helfer):
    """Der Wert wird nur woechentlich geschrieben. Steht er in der Vergangenheit,
    ist der Lauf ausgefallen oder der Timer aus -- dann ist das Alter die ehrlichere
    Angabe. Ein abgelaufener Countdown („neu in 0 h", seit Tagen) ist die
    unbrauchbarste Form dieser Auskunft und sieht trotzdem nach Messung aus."""
    ordner, mcfakten = helfer
    jetzt = int(time.time())
    schreibe(ordner, "farmwelt-reset.json",
             {"letzter_reset": jetzt - 9 * 86400, "naechster_reset": jetzt - 2 * 86400})
    f = mcfakten.farmwelt()
    assert "naechster_in_s" not in f
    assert f["reset_vor_s"] > 0, "das Alter muss als Rueckfall erhalten bleiben"


def test_termin_ohne_letzten_reset_sagt_nichts(helfer):
    """Ohne `letzter_reset` gibt es gar keine Auskunft, auch nicht die halbe: die
    Kachel braucht den Bezugspunkt, sonst stuende dort ein Termin ohne Gegenwart."""
    ordner, mcfakten = helfer
    schreibe(ordner, "farmwelt-reset.json", {"naechster_reset": int(time.time()) + 86400})
    assert mcfakten.farmwelt() is None


def test_kaputter_termin_bricht_das_alter_nicht(helfer):
    """Ein Wert vom falschen Typ darf die brauchbare Haelfte nicht mitreissen."""
    ordner, mcfakten = helfer
    jetzt = int(time.time())
    schreibe(ordner, "farmwelt-reset.json",
             {"letzter_reset": jetzt - 3600, "naechster_reset": "Montag"})
    f = mcfakten.farmwelt()
    assert f is not None and "naechster_in_s" not in f
