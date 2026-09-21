#!/usr/bin/env python3
"""Sammelt die aktiven Mods je Spiel und legt sie fuer die Clan-Seite ab.

Laeuft auf dem Spiele-VPS, nicht im Container: die Mod-Listen stehen in den
Arbeitsverzeichnissen der Dienstnutzer, jede in einem anderen Format, und das
Dashboard soll diese Verzeichnisstruktur nicht kennen muessen.

★ WARUM GESAMMELT UND NICHT GEPFLEGT: eine von Hand gefuehrte Liste stimmt am Tag
ihrer Entstehung und wird danach nur noch falscher, ohne je zu scheitern. Genau das
war hier schon der Fall: in den Beitritts-Anleitungen stand „der Launcher zieht die
Mods (@CF, @VPPAdminTools)" als Aufzaehlung im Fliesstext, waehrend der Server
laengst fuenf lud. Quelle ist deshalb immer die Datei, die der Server wirklich liest.

★ „NICHT GEFUNDEN" IST NICHT „KEINE MODS". Beides als leere Liste auszugeben waere
die bequeme Luege: ein Spiel, dessen Konfiguration umgezogen ist, saehe dann aus wie
ein Vanilla-Server. Deshalb traegt jeder Eintrag `gelesen`, und die Oberflaeche
schweigt lieber, als Vanilla zu behaupten.

Ausgabe: <ZIEL>/mods.json  (Verzeichnis, nicht Einzeldatei, siehe unten)
Aufruf:  mods-sammeln.py [zielverzeichnis]
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ★ Ein VERZEICHNIS als Ziel, das der Container read-only einhaengt, nicht die
# Datei selbst. Ein Single-File-Bindmount haengt an der Inode: sobald hier neu
# geschrieben wird (und das passiert genau dann, wenn sich Mods geaendert haben),
# zeigt der Mount im Container weiter auf die alte Datei. Die Anzeige fröre also
# ausgerechnet im relevanten Moment ein.
ZIEL = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/game-dashboard/mods")


def _lies(pfad: Path) -> str | None:
    try:
        return pfad.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def terraria() -> dict:
    """tModLoader: JSON-Liste der aktivierten Mods."""
    p = Path("/home/terraria/Mods/enabled.json")
    roh = _lies(p)
    if roh is None:
        return {"gelesen": False, "grund": f"{p} nicht lesbar"}
    try:
        namen = [str(m) for m in json.loads(roh)]
    except json.JSONDecodeError as e:
        return {"gelesen": False, "grund": f"{p}: {e}"}
    return {"gelesen": True, "quelle": str(p), "mods": sorted(namen)}


def factorio() -> dict:
    """Factorio: mod-list.json mit enabled-Schalter je Eintrag."""
    p = Path("/home/factorio/factorio/mods/mod-list.json")
    roh = _lies(p)
    if roh is None:
        return {"gelesen": False, "grund": f"{p} nicht lesbar"}
    try:
        eintraege = json.loads(roh).get("mods", [])
    except json.JSONDecodeError as e:
        return {"gelesen": False, "grund": f"{p}: {e}"}
    # „base" ist das Grundspiel und steht in jeder Liste; es als Mod zu zaehlen
    # haette jeden Vanilla-Server als modifiziert ausgewiesen.
    namen = [m["name"] for m in eintraege
             if m.get("enabled") and m.get("name") not in ("base",)]
    return {"gelesen": True, "quelle": str(p), "mods": sorted(namen)}


def zomboid() -> dict:
    """Project Zomboid: Mods= in der Server-Ini, je Eintrag mit fuehrendem Backslash.

    ★ Als einziges Spiel hier haelt Zomboid seine Mod-Liste JE WELT: die Ini heisst
    wie die Welt (greenleaf.ini). Zwei Welten koennen also verschiedene Mods haben,
    und deshalb wird hier je Datei gesammelt statt nur die erste zu nehmen. Heute
    gibt es genau eine Welt; die Struktur traegt trotzdem, sobald eine zweite
    dazukommt, ohne dass hier noch einmal jemand nachziehen muss.
    """
    ordner = Path("/home/zomboid/Zomboid/Server")
    inis = sorted(ordner.glob("*.ini")) if ordner.is_dir() else []
    if not inis:
        return {"gelesen": False, "grund": f"keine .ini in {ordner}"}
    welten: dict[str, list[str]] = {}
    for p in inis:
        roh = _lies(p)
        if roh is None:
            continue
        treffer = re.search(r"^Mods=(.*)$", roh, re.M)
        if treffer is None:
            continue
        welten[p.stem] = [t.lstrip("\\").strip()
                          for t in treffer.group(1).split(";") if t.strip()]
    if not welten:
        return {"gelesen": False, "grund": f"{ordner}: keine Zeile Mods= gefunden"}
    return {"gelesen": True, "quelle": str(ordner), "je_welt": True, "welten": welten,
            # Fuer Anzeigen, die keine Welt kennen (Landing, Kachel ohne laufende
            # Welt): die Vereinigung. Sie ist ehrlich, solange sie als solche
            # beschriftet wird, und bei einer Welt ohnehin genau deren Liste.
            "mods": sorted({m for liste in welten.values() for m in liste})}


def dayz() -> dict:
    """DayZ: -mod=@A;@B in der systemd-Unit (kein eigenes Konfigurationsformat)."""
    p = Path("/etc/systemd/system/dayz-server.service")
    roh = _lies(p)
    if roh is None:
        return {"gelesen": False, "grund": f"{p} nicht lesbar"}
    treffer = re.search(r"-mod=([^\s\"']+)", roh)
    if not treffer:
        return {"gelesen": True, "quelle": str(p), "mods": []}
    namen = [t.lstrip("@").strip() for t in treffer.group(1).split(";") if t.strip()]
    return {"gelesen": True, "quelle": str(p), "mods": namen}


def minecraft() -> dict:
    """Paper-Plugins. ★ Das sind SERVERSEITIGE Erweiterungen, keine Client-Mods:
    wer beitritt, muss nichts installieren. Sie deshalb als „Mods" auszuweisen
    haette Spieler auf die Suche nach Downloads geschickt, die es nicht gibt."""
    ordner = Path("/opt/mc/data/plugins")
    if not ordner.is_dir():
        return {"gelesen": False, "grund": f"{ordner} nicht vorhanden"}
    namen = sorted({
        re.sub(r"[-_]?\d[\d.]*$", "", j.stem).rstrip("-_")
        for j in ordner.glob("*.jar")
    })
    return {"gelesen": True, "quelle": str(ordner), "mods": namen, "serverseitig": True}


def valheim() -> dict:
    """Valheim: modifiziert waere es nur mit BepInEx daneben."""
    for kandidat in (Path("/home/valheim/BepInEx"), Path("/home/valheim/valheim/BepInEx")):
        if kandidat.is_dir():
            namen = sorted(p.stem for p in (kandidat / "plugins").glob("*.dll")) \
                if (kandidat / "plugins").is_dir() else []
            return {"gelesen": True, "quelle": str(kandidat), "mods": namen}
    return {"gelesen": True, "quelle": "/home/valheim", "mods": []}


def avorion() -> dict:
    """Avorion: Mods liegen je Galaxie; ohne Ordner laeuft es unmodifiziert."""
    wurzel = Path("/home/avorion/.avorion/galaxies")
    if not wurzel.is_dir():
        return {"gelesen": False, "grund": f"{wurzel} nicht vorhanden"}
    namen: set[str] = set()
    for mods in wurzel.glob("*/mods"):
        namen.update(p.name for p in mods.iterdir() if p.is_dir())
    return {"gelesen": True, "quelle": str(wurzel), "mods": sorted(namen)}


# ★ Wer laedt seine Mods JE WELT und wer fuer den ganzen Server? Gemessen am
# 2026-09-06: nur Zomboid haelt sie je Welt (eine Ini je Welt). tModLoader liest
# EINE enabled.json fuer alle Welten, gemessen an zwei Welten (Greenleaf, Solo) und
# genau einer Mod-Datei; Factorio ebenso eine mod-list.json fuer alle Saves. Der
# Welt-Wechsel des Arbiters fasst die Mod-Dateien nicht an (nachgesehen in
# ensure-world.sh und arbiter.py). Wer das aendert, aendert es hier mit.
SAMMLER = {
    "terraria": terraria, "factorio": factorio, "zomboid": zomboid,
    "dayz": dayz, "minecraft": minecraft, "valheim": valheim, "avorion": avorion,
}


def main() -> int:
    spiele = {}
    for key, fn in SAMMLER.items():
        try:
            spiele[key] = fn()
        except Exception as e:                      # ein kaputtes Spiel darf nicht
            spiele[key] = {"gelesen": False,        # die anderen sechs mitreissen
                           "grund": f"{type(e).__name__}: {e}"}

    ZIEL.mkdir(parents=True, exist_ok=True)
    ziel = ZIEL / "mods.json"
    # Erst daneben schreiben, dann umbenennen: ein Leser, der mitten im Schreiben
    # liest, bekaeme sonst halbes JSON zu sehen. os.replace ist auf demselben
    # Dateisystem atomar.
    tmp = ZIEL / "mods.json.neu"
    tmp.write_text(json.dumps({
        "stand": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spiele": spiele,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ziel)
    os.chmod(ziel, 0o644)                           # der Container liest unprivilegiert

    for key, d in sorted(spiele.items()):
        if not d.get("gelesen"):
            print(f"  !! {key}: {d.get('grund')}")
        else:
            n = len(d.get("mods", []))
            art = " (serverseitig)" if d.get("serverseitig") else ""
            print(f"  ok  {key}: {n} Mod(s){art}")
    print(f"  -> {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
