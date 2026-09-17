"""Mod-Listen je Spiel, gesammelt auf dem Wirt.

Gefuellt wird `mods.json` vom Sammler `gamehost/mods-sammeln.py` (systemd-Timer,
taeglich und bei jedem Ausrollen). Hier wird sie nur gelesen: das Dashboard laeuft
im Container und hat die Arbeitsverzeichnisse der Spiele bewusst nicht.

★ „Nicht gelesen" ist NICHT „keine Mods". Beides als leere Liste zu behandeln waere
die bequeme Luege, und sie faellt niemandem auf: ein Spiel, dessen Konfiguration
umgezogen ist, saehe aus wie ein Vanilla-Server, und wer sich darauf verlaesst,
steht beim Beitritt ohne die noetigen Mods da. Deshalb gibt es drei Zustaende und
nicht zwei: Liste, leere Liste (gemessen), unbekannt (nichts gemessen).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Verzeichnis-Mount, nicht Einzeldatei: der Sammler schreibt die Datei bei jeder
# Aenderung neu, und ein Single-File-Bindmount haengt an der alten Inode fest.
# Ausserhalb von /app/data: dort liegt das benannte Volume, und ein Bind
# darunter wird von ihm ueberdeckt (siehe gamehost/docker-compose.yml).
PFAD = Path(os.getenv("MODS_FILE", "/app/mods/mods.json"))

_cache: dict = {}
_mtime: float = -1.0


def _laden() -> dict:
    """Liest die Datei neu, sobald sie sich geaendert hat (mtime als Merkmal)."""
    global _cache, _mtime
    try:
        st = PFAD.stat()
    except OSError:
        _cache, _mtime = {}, -1.0
        return _cache
    if st.st_mtime != _mtime:
        try:
            _cache = json.loads(PFAD.read_text(encoding="utf-8"))
            _mtime = st.st_mtime
        except (OSError, json.JSONDecodeError):
            # Halb geschriebene Datei: den letzten guten Stand behalten. Der Sammler
            # schreibt zwar atomar (os.replace), aber eine kaputte Datei darf die
            # Seite nicht mit in den Fehler ziehen.
            return _cache
    return _cache


def fuer(key: str, welt: str | None = None) -> dict:
    """Mod-Angabe fuer ein Spiel, wenn moeglich fuer eine bestimmte Welt.

    Rueckgabe immer mit `bekannt`: False heisst „darueber liegt keine Messung vor",
    nicht „unmodifiziert". Die Oberflaeche schweigt dann, statt Vanilla zu behaupten.

    ★ `je_welt` sagt, ob die Angabe zu DIESER Welt gehoert oder zum ganzen Server.
    Der Unterschied ist keine Feinheit: bei Terraria liegen zwei Welten (Greenleaf,
    Solo) hinter EINER enabled.json, wer dort „8 Mods" an einer Welt liest, haelt
    das leicht fuer deren Eigenschaft. Nur Zomboid haelt die Liste je Welt (eine
    Ini je Welt). Die Oberflaeche schreibt deshalb dazu, wofuer die Liste gilt.
    """
    eintrag = (_laden().get("spiele") or {}).get(key)
    if not eintrag or not eintrag.get("gelesen"):
        return {"bekannt": False, "mods": [], "serverseitig": False, "je_welt": False}
    je_welt = bool(eintrag.get("je_welt"))
    welten = eintrag.get("welten") or {}
    if je_welt and welt and welt in welten:
        liste = list(welten[welt])
    else:
        liste = list(eintrag.get("mods") or [])
    return {
        "bekannt": True,
        "mods": liste,
        "je_welt": je_welt,
        # Wieviele Welten kennt die Messung? Erst ab zwei ist „je Welt" ein
        # sichtbarer Unterschied, vorher waere der Hinweis nur Rauschen.
        "welten_bekannt": len(welten),
        "welt": welt if (je_welt and welt in welten) else "",
        # Paper-Plugins und Aehnliches: der Server ist erweitert, der Client braucht
        # nichts. Das ist fuer jemanden, der beitreten will, der ganze Unterschied.
        "serverseitig": bool(eintrag.get("serverseitig")),
    }


def je_welt(key: str) -> dict[str, list[str]]:
    """Mods je Welt, leer wenn das Spiel sie serverweit laedt."""
    eintrag = (_laden().get("spiele") or {}).get(key) or {}
    if not eintrag.get("gelesen") or not eintrag.get("je_welt"):
        return {}
    return {w: list(m) for w, m in (eintrag.get("welten") or {}).items()}


def stand() -> str:
    """Zeitpunkt des letzten Sammellaufs (ISO, UTC) oder leer."""
    return str(_laden().get("stand") or "")
