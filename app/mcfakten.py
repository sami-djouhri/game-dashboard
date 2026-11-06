"""Zusatzangaben zur Minecraft-Kachel, die nur auf dem Wirt stehen.

Gefuellt werden die Dateien von den Helfern in `/opt/mc-helfer` (systemd-Timer auf
diesem Wirt). Hier werden sie nur GELESEN -- das Dashboard laeuft im Container und
hat die Arbeitsverzeichnisse des Servers bewusst nicht.

Handoff-Punkt E.16 (2026-10-17): "Statusseite im Dashboard. Zeigen: wach oder
schlafend, wer online, wann die Farmwelt zuletzt zurueckgesetzt wurde."
Die ersten zwei kommen schon aus dem Arbiter-Status. Der dritte stand nirgends:
die Ressourcenwelt wird montags neu erzeugt, und ein Spieler, der dort baut,
konnte vorher nicht sehen, wie viel Zeit ihm bleibt.

VERZEICHNIS-MOUNT, nicht Einzeldatei -- dieselbe Begruendung wie bei mods.py
und dort teuer gelernt: die Helfer schreiben ihre Stand-Dateien mit `os.replace`
neu, und ein Single-File-Bindmount haengt an der alten Inode fest. Die Anzeige
fröre genau dann ein, wenn sich etwas geaendert hat.

DREI ZUSTAENDE, nicht zwei: Wert, "gemessen und nichts da", "nicht gelesen".
Ein fehlender Mount als "letzter Reset: nie" anzuzeigen waere die bequeme Luege
und sieht wie eine Auskunft aus. `None` heisst hier ausdruecklich unbekannt, und
die Kachel zeigt dann nichts statt etwas Falsches.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ORDNER = Path(os.getenv("MC_HELFER_DIR", "/app/mc-helfer"))

_cache: dict[str, tuple[float, dict]] = {}


def _laden(name: str) -> dict | None:
    """Eine Stand-Datei lesen, neu nur wenn sie sich geaendert hat."""
    pfad = ORDNER / name
    try:
        mtime = pfad.stat().st_mtime
    except OSError:
        return None
    alt = _cache.get(name)
    if alt and alt[0] == mtime:
        return alt[1]
    try:
        d = json.loads(pfad.read_text())
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    _cache[name] = (mtime, d)
    return d


def farmwelt() -> dict | None:
    """Alter der Farmwelt und, wenn bekannt, wann die naechste kommt.

    `{'reset_zeit', 'reset_vor_s'}` plus optional `'naechster_in_s'`.

    Den Termin nennt systemd auf dem Wirt (`OnCalendar` der Unit), und das
    Reset-Skript schreibt ihn mit. Hier wird er NICHT nachgerechnet: ein im
    Dashboard gebautes „naechster Montag 05:00" waere eine zweite Wahrheit neben
    der Unit und beim ersten geaenderten Kalender still falsch. Ein Datum sieht
    immer plausibel aus, also faellt so etwas nie auf.

    ⚠️ Der Wert wird nur beim Reset-Lauf geschrieben, also woechentlich. Liegt er
    in der Vergangenheit, ist er veraltet (Timer abgeschaltet, Lauf ausgefallen)
    und wird weggelassen statt als „kommt gleich" angezeigt -- ein abgelaufener
    Countdown ist die unbrauchbarste Form dieser Angabe.
    """
    d = _laden("farmwelt-reset.json")
    if not d:
        return None
    zeit = d.get("letzter_reset")
    if not isinstance(zeit, (int, float)) or zeit <= 0:
        return None
    jetzt = time.time()
    erg = {"reset_zeit": int(zeit), "reset_vor_s": max(0, int(jetzt - zeit))}
    naechster = d.get("naechster_reset")
    if isinstance(naechster, (int, float)) and naechster > jetzt:
        erg["naechster_in_s"] = int(naechster - jetzt)
    return erg


def jobparkplatz() -> dict | None:
    """Wie viele Job-Staende pausiert sind und wie viele auf den Stopp warten.

    Fuer Spieler sichtbar, weil es eine Zusage einloest: wer kuendigt, liest im
    Chat "dein Fortschritt bleibt gesichert". Eine Zahl, die man nachsehen kann,
    ist der Unterschied zwischen einer Zusage und einem Beleg.
    """
    d = _laden("jobs-parkplatz.json")
    if not d:
        return None
    geparkt = d.get("geparkt")
    vorgemerkt = d.get("vorgemerkt")
    if not isinstance(geparkt, dict) or not isinstance(vorgemerkt, dict):
        return None
    return {"geparkt": len(geparkt), "vorgemerkt": len(vorgemerkt)}


def bonus() -> dict | None:
    """Der aktuell gueltige Einnahmen-Faktor (1 = kein Bonus)."""
    d = _laden("jobs-bonus.json")
    if not d:
        return None
    faktor = d.get("faktor")
    if not isinstance(faktor, (int, float)) or faktor < 1:
        return None
    return {"faktor": int(faktor), "gezahlt": int(d.get("gezahlt") or 0)}


def alles() -> dict:
    """Alle Angaben in einem Aufruf, leere Schluessel weggelassen.

    ⚠️ Weggelassen und nicht als `null` mitgeschickt: die Kachel prueft auf
    Anwesenheit, und ein `null` waere dort ein Wert, den jemand formatiert.
    """
    erg = {}
    for name, f in (("farmwelt", farmwelt), ("jobs", jobparkplatz), ("bonus", bonus)):
        wert = f()
        if wert:
            erg[name] = wert
    return erg
