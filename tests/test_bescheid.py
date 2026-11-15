"""Bescheid bei Bereitschaft (app/static/bescheid.js), unter node geprueft.

Die Entscheidung, wann "ist bereit" gemeldet wird, ist die Stelle, an der sich die
Funktion verraten kann: zu frueh (alter Lauf beim Neustart) schickt jemanden in
einen Server, der gleich neu startet; nie (Start schneller als eine Abfrage) laesst
ihn umsonst warten.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "bescheid.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node fehlt")


def lauf(schritte, gesehen=True, max_ms=480000):
    """schritte: Liste (jetzt_ms, state). Liefert die Meldungen je Schritt."""
    prog = f"""
const {{ bescheidAuswerten }} = require({json.dumps(str(JS))});
const w = new Map([["terraria", {{ seit: 0, gesehen: {json.dumps(gesehen)} }}]]);
const aus = [];
for (const [t, s] of {json.dumps(schritte)}) {{
  aus.push(bescheidAuswerten(w, s ? [{{ key: "terraria", label: "Terraria", state: s }}] : [], t, {max_ms}));
}}
console.log(JSON.stringify({{ aus, rest: w.size }}));
"""
    out = subprocess.run(["node", "-e", prog], check=True, stdout=subprocess.PIPE, text=True)
    return json.loads(out.stdout)


def test_start_meldet_bereit_sobald_active():
    r = lauf([(5000, "sleeping"), (60000, "starting"), (120000, "active")])
    assert r["aus"] == [[], [], [{"key": "terraria", "name": "Terraria", "bereit": True}]]
    assert r["rest"] == 0


def test_schneller_start_wird_trotzdem_gemeldet():
    # Erste Abfrage nach dem Klick zeigt schon "active": beim Start aus dem Schlaf gilt das.
    r = lauf([(5000, "active")])
    assert r["aus"][0][0]["bereit"] is True


def test_neustart_meldet_alten_lauf_nicht():
    r = lauf([(5000, "active"), (40000, "starting"), (90000, "active")], gesehen=False)
    assert r["aus"][0] == []
    assert r["aus"][2][0]["bereit"] is True


def test_stumm_meldet_fehlschlag():
    r = lauf([(5000, "starting"), (400000, "stumm")])
    assert r["aus"][1] == [{"key": "terraria", "name": "Terraria", "bereit": False}]
    assert r["rest"] == 0


def test_nach_ablauf_zaehlt_der_jetzige_zustand():
    # Neustart, Wechsel nie gesehen, nach Ablauf laeuft er: das ist bereit, kein Fehlschlag.
    r = lauf([(5000, "active"), (500000, "active")], gesehen=False)
    assert r["aus"][1][0]["bereit"] is True
    r = lauf([(5000, "starting"), (500000, "starting")])
    assert r["aus"][1][0]["bereit"] is False


def test_spiel_fehlt_im_status_wartet_weiter():
    r = lauf([(5000, None), (10000, "active")])
    assert r["aus"][0] == []
    assert r["aus"][1][0]["bereit"] is True
