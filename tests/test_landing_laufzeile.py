"""Laufzeile der Landing (app/static/landing.js), unter node geprueft.

Bis 2026-11-26 nannte sie nur das erste laufende Spiel: bei 3 Spielern auf
Valheim und 2 auf GreenForest stand dort "5 Personen spielen gerade · Valheim".
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "landing.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node fehlt")


def zeile(status):
    prog = f"""
const {{ laufzeile }} = require({json.dumps(str(JS))});
console.log(JSON.stringify(laufzeile({json.dumps(status)})));
"""
    out = subprocess.run(["node", "-e", prog], check=True, stdout=subprocess.PIPE, text=True)
    return json.loads(out.stdout)


def _g(label, state="active", players=0):
    return {"label": label, "state": state, "players": players}


def test_zwei_besetzte_server_werden_beide_genannt():
    z = zeile({"online_total": 5, "games": [_g("Valheim", players=3),
                                            _g("GreenForest", players=2),
                                            _g("Calamity", "sleeping")]})
    assert z == "<b>5</b> Personen spielen gerade · Valheim, GreenForest"


def test_reihenfolge_nach_spielerzahl():
    z = zeile({"online_total": 4, "games": [_g("A", players=1), _g("B", players=3)]})
    assert z.endswith("· B, A")


def test_einzahl_und_leerlauf():
    assert zeile({"online_total": 1, "games": [_g("DayZ", players=1)]}) == \
        "<b>1</b> Person spielt gerade · DayZ"
    assert zeile({"online_total": 0, "games": [_g("DayZ")]}) == "DayZ läuft"
    assert zeile({"online_total": 0, "games": [_g("A"), _g("B")]}) == "A, B laufen"


def test_nichts_wach_ist_leer():
    assert zeile({"online_total": 0, "games": [_g("A", "sleeping"), _g("B", "starting")]}) == ""
    assert zeile({}) == ""


def test_namen_werden_maskiert():
    z = zeile({"online_total": 0, "games": [_g("<img src=x>")]})
    assert "<img" not in z
