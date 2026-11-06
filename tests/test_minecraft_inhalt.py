"""Was der Minecraft-Guide verspricht, muss auf dem Server auch laufen.

WARUM ES DIESE DATEI GIBT (2026-10-17):
Bis dahin stand unter Minecraft nur die gesammelte Liste der 27 Plugin-Dateien.
Die ist ehrlich (sie wird vom Wirt gelesen), beantwortet aber die falsche Frage:
„DeluxeMenus-1.14.1-Release“, „PlaceholderAPI“, „VaultUnlocked“ sind
Hilfsbibliotheken, und dass es auf diesem Server Berufe mit Gehalt, geschuetzte
Grundstuecke, sechs Welten und eine Schachwelt gibt, war daraus nicht ablesbar.

Das Feld `bietet` schliesst die Luecke, handelt sich damit aber ein neues Problem
ein: es ist **gepflegt und nicht gemessen** und damit der eine Teil des Guides, der
veralten kann, ohne je zu scheitern. Genau dagegen hat dieses Projekt die
Mod-Aufzaehlungen abgeschafft („in der DayZ-Anleitung stand, der Launcher ziehe die
Mods @CF, @VPPAdminTools und nannte damit zwei von fuenf").

Deshalb bindet diese Datei jede Zusage an das Plugin, das sie traegt. Wird eines
abgeschaltet, faellt der Test und nicht erst ein Spieler auf, der `/job` eintippt
und „Unknown command“ liest.

⚠️ GRENZE: geprueft wird gegen `mods.json`, also gegen das, was der Sammler auf dem
Wirt zuletzt GESEHEN hat. Ob das Plugin auch fehlerfrei geladen hat, steht dort
nicht. Ein Plugin, das beim Start abbricht, liegt weiter als Datei da.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import guides

WURZEL = Path(__file__).resolve().parent.parent

# Jede Zusage im Guide und das Plugin, ohne das sie nicht stimmt.
# Der Schluessel ist ein Stueck des Satzes aus `bietet`/`notes`, damit beim Umschreiben
# auffaellt, dass hier etwas mitgepflegt werden will.
# Die Werte sind die Dateinamen OHNE Version, so wie `mods-sammeln.py` sie liefert.
# Der Plugin-Name im Spiel ist nicht derselbe: das Berufe-Plugin meldet sich als
# „JobSystem", seine Datei heisst `vrx-jobsystem-1.1.3.jar`. Genau daran ist der
# erste Lauf dieser Datei gescheitert, und das ist der richtige Fehler gewesen:
# geprueft wird gegen die Liste, die die Seite ANZEIGT, nicht gegen die, die der
# Server intern fuehrt.
ZUSAGEN = {
    "Berufe mit Gehalt": "vrx-jobsystem",   # meldet sich im Spiel als „JobSystem"
    "Münzen": "PlayerPoints",               # die Waehrung, in der gezahlt wird
    "Grundstücke": "GriefPrevention",       # der Schutz des eigenen Gebiets
    "Zuhause-Punkte": "zHomes",
    "Teleport": "SimpleTPA",
    "Schach": "SchachSpiel",                # Eigenplugin
    "Skyblock": "IridiumSkyblock",
    "Sechs Welten": "multiverse-core",      # ohne Multiverse gibt es nur eine
}


def _gesammelte_plugins() -> list[str]:
    """Die Plugin-Namen, die der Sammler auf dem Wirt gelesen hat.

    Aus den Pruefdaten, nicht ueber das Netz: kein Test dieses Projekts geht auf
    einen Wirt. Die Pruefdaten sind ein Abzug der echten `mods.json`, und dass sie
    jedes Spiel kennen, haelt `test_vollstaendigkeit.py` fest.
    """
    daten = json.loads((WURZEL / "scripts" / "pruefdaten-mods.json")
                       .read_text(encoding="utf-8"))
    eintrag = (daten.get("spiele") or {}).get("minecraft") or {}
    return list(eintrag.get("mods") or [])


def _guide_text() -> str:
    g = guides.GUIDES["minecraft"]
    return " ".join(g.get("bietet") or []) + " " + " ".join(g.get("notes") or [])


@pytest.mark.parametrize("zusage,plugin", sorted(ZUSAGEN.items()))
def test_zusage_hat_ihr_plugin(zusage, plugin):
    """Steht die Zusage im Guide, muss das Plugin dazu auf dem Server liegen."""
    if zusage not in _guide_text():
        pytest.skip(f"Guide verspricht „{zusage}“ nicht (mehr)")
    vorhanden = [p for p in _gesammelte_plugins()
                 if p.lower().startswith(plugin.lower())]
    assert vorhanden, (
        f"Der Guide verspricht „{zusage}“, aber {plugin} liegt nicht auf dem Server. "
        "Entweder ist das Plugin weg und die Zusage falsch, oder es heisst jetzt "
        "anders und diese Zuordnung ist zu pflegen."
    )


def test_keine_rohen_dateinamen_im_guide():
    """Im gepflegten Text keine Plugin-Dateinamen, das ist die Rolle der Liste darunter.

    Der Unterschied ist der ganze Punkt dieses Abschnitts: die Liste sagt, WAS
    installiert ist (gemessen), der Text sagt, was man TUN kann (gepflegt). Wer
    Dateinamen in den Text schreibt, baut die Doppelung wieder auf, und dann veraltet
    die gepflegte Haelfte still."""
    text = _guide_text()
    treffer = [p for p in _gesammelte_plugins() if p in text]
    assert not treffer, f"Plugin-Dateinamen im Fliesstext: {treffer}"


def test_versprochene_befehle_sehen_wie_befehle_aus():
    """Jeder genannte Spielbefehl ist klein geschrieben und beginnt mit einem Schraegstrich.

    Billige Probe gegen den haeufigsten Tippfehler in Anleitungen: `Welten` statt
    `/welten` tippt ein Spieler wortwoertlich ab und bekommt nichts."""
    for befehl in re.findall(r"`([^`]+)`", " ".join(guides.GUIDES["minecraft"]["bietet"])):
        assert befehl.startswith("/"), f"„{befehl}“ sieht nicht wie ein Befehl aus"
        assert befehl == befehl.lower(), f"„{befehl}“ ist nicht klein geschrieben"
