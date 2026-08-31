"""Beitritts- und Installations-Anleitungen je Spiel.

Reine Inhalts-Daten (kein Live-Zustand). Die Adressen stehen NICHT hier, sondern
kommen aus `app.games` (die eine Wahrheit) — die Texte tragen nur Platzhalter.
Passwoerter/Details, die nicht oeffentlich sein sollen, werden im Mitglieder-
Bereich ergaenzt, nicht hier.

Anonyme Besucher sehen die Guides OHNE Server-Adressen (all_guides(public=True)
maskiert IP/Ports ueberall) — Adressen gibt es erst nach dem Login.
"""
from __future__ import annotations

import re
from functools import lru_cache

_ADDR_MASK = "···"


@lru_cache(maxsize=1)
def _addr_re() -> re.Pattern:
    """Muster fuer „hier steht eine Server-Adresse" — abgeleitet aus app.games.SERVER.

    ★ Frueher stand hier die IP fest verdrahtet. Als die Spiele am 2026-08-22 auf den
    Spiele-VPS zogen, aenderte sich die Adresse an ihrer einen Quelle — das Muster hier
    zeigte weiter auf den alten Host und traf nichts mehr. Die Maskierung lief seitdem
    ins Leere, ohne ein Zeichen zu geben: die Seite sah aus wie vorher, gab die Adressen
    samt Ports aber an jeden Besucher heraus. Aus derselben Quelle abgeleitet kann genau
    das nicht mehr passieren.
    """
    from app.games import SERVER
    return re.compile("(?:%s)(?::\\d+)?" % "|".join(re.escape(ip) for ip in SERVER.values()))

# store: Steam-/Download-Link des Clients.  address: oeffentlicher Join-Endpunkt.
GUIDES: dict[str, dict] = {
    "valheim": {
        "label": "Valheim",
        "emoji": "🪓",
        "platform": "Steam · Windows/Linux",
        "world": "Greenleaf",
        "address": "{addr}",
        "client": "Valheim (Steam)",
        "store": "https://store.steampowered.com/app/892970/Valheim/",
        "install": [
            "Valheim in Steam kaufen & installieren.",
            "Spiel starten, Charakter anlegen.",
        ],
        "join": [
            "Im Startmenü **Beitreten → Server hinzufügen**.",
            "Adresse `{addr}` eingeben (oder in der Community-Liste nach **„Greenleaf“** suchen).",
            "Server-Passwort eingeben (steht im Mitglieder-Bereich).",
        ],
        "notes": [
            "Läuft der Server gerade nicht? Einfach oben **Starten**, nach ~1–2 min ist er da.",
            "Leere Server gehen nach ~20 min automatisch aus; mehrere dürfen zusammen laufen, "
            "solange der Arbeitsspeicher reicht.",
        ],
    },
    "dayz": {
        "label": "DayZ",
        "emoji": "🎮",
        "platform": "Steam · Windows",
        "world": "Greenleaf Forest (Chernarus)",
        "address": "{addr}",
        "client": "DayZ (Steam) + DZSA-Launcher",
        "store": "https://store.steampowered.com/app/221100/DayZ/",
        "install": [
            "DayZ in Steam kaufen & installieren.",
            "**DZSA-Launcher** von dayzsalauncher.com installieren, er lädt die Server-Mods automatisch.",
        ],
        "join": [
            "DZSA-Launcher öffnen, nach **„Greenleaf Forest“** suchen (oder IP `{addr}` als Favorit).",
            "**Install & Play**, der Launcher zieht die Mods (@CF, @VPPAdminTools) und startet DayZ.",
        ],
        "notes": [
            "Direkter Beitritt ohne DZSA klappt **nicht** (Mods fehlen), der Launcher ist Pflicht.",
            "BattlEye ist aktiv; keine Cheats/fremde Mods.",
        ],
    },
    "zomboid": {
        "label": "Project Zomboid",
        "emoji": "🧟",
        "platform": "Steam · Windows/Linux",
        "world": "Greenleaf (Muldraugh, KY)",
        "address": "{addr}",
        "client": "Project Zomboid (Steam)",
        "store": "https://store.steampowered.com/app/108600/Project_Zomboid/",
        "install": [
            "Project Zomboid in Steam kaufen & installieren.",
        ],
        "join": [
            "**Join Server → Favorite/IP**, Adresse `{host}` Port `16261`.",
            "Konto-Name frei wählen, Server-Passwort eingeben (Mitglieder-Bereich).",
            "Alternativ in der Community-Serverliste nach **„Greenleaf“** suchen.",
        ],
        "notes": [
            "Langzeit-Welt, Fortschritt bleibt über Jahre erhalten.",
            "Mods werden beim Beitritt automatisch von Steam geladen, nichts vorab abonnieren.",
            "Aktive Mods: Spawn Selector (Startposition frei wählbar), This Is Your Life "
            "(Charakter-Vorgeschichte), Infirmities (Krankheiten), plus die Karten "
            "**Greenleaf** und **Vila Z**.",
        ],
    },
    "factorio": {
        "label": "Factorio",
        "emoji": "🏭",
        "platform": "Steam/Standalone · Windows/Linux",
        "world": "Greenleaf",
        "address": "{addr}",
        "client": "Factorio",
        "store": "https://factorio.com/",
        "install": [
            "Factorio installieren (Steam oder factorio.com).",
            "Version muss zum Server passen (aktuell v2.0.x + Overhaul-Mods, werden beim Beitritt geladen).",
        ],
        "join": [
            "**Multiplayer → Connect to address**.",
            "`{addr}` eingeben.",
            "Mods lädt Factorio beim Beitritt automatisch vom Server.",
        ],
        "notes": [
            "Kein factorio.com-Konto nötig (Direct-Connect).",
            "Bei 0 Spielern pausiert die Fabrik automatisch, kein Fortschritt geht verloren.",
        ],
    },
    "terraria": {
        "label": "Terraria",
        "emoji": "🌳",
        "platform": "Steam · Windows/Linux",
        "world": "Greenleaf (Large/Expert)",
        "address": "{addr}",
        "client": "tModLoader (Steam-App 1281930)",
        "store": "https://store.steampowered.com/app/1281930/tModLoader/",
        "install": [
            "**tModLoader** in Steam installieren (kostenlos, wenn Terraria vorhanden, App-ID 1281930).",
            "Vanilla-Terraria kann **nicht** beitreten, es muss tModLoader sein.",
        ],
        "join": [
            "tModLoader starten → **Mods** → Workshop-Mods werden beim Beitritt automatisch synchronisiert.",
            "**Multiplayer → Join via IP**, `{host}` Port `7777`.",
        ],
        "notes": [
            "Aktive Mods: Thorium, Fargo's + Souls, Magic Storage, Recipe Browser, Boss Checklist u. a.",
            "Keine Serverliste, Beitritt läuft über die IP (Direct-Connect).",
        ],
    },
    "avorion": {
        "label": "Avorion",
        "emoji": "🚀",
        "platform": "Steam · Windows/Linux",
        "world": "Galaxie „Greenleaf“",
        "address": "Steam-/Avorion-Serverliste „Greenleaf“",
        "client": "Avorion (Steam)",
        "store": "https://store.steampowered.com/app/445220/Avorion/",
        "install": [
            "Avorion in Steam kaufen & installieren.",
        ],
        "join": [
            "**Multiplayer → Server durchsuchen**, nach **„Greenleaf“** filtern.",
            "Beitreten, der Traffic läuft über Steam-Networking (kein Direct-IP nötig).",
        ],
        "notes": [
            "Langzeit-Sandbox mit Grind, die Galaxie wächst über Jahre.",
        ],
    },
    "minecraft": {
        "label": "Minecraft",
        "emoji": "⛏️",
        "platform": "Java Edition",
        "world": "Greenleaf",
        "address": "Adresse im Mitglieder-Bereich",
        "client": "Minecraft: Java Edition",
        "store": "https://www.minecraft.net/",
        "install": [
            "Minecraft: Java Edition installieren.",
            "Passende Java-Version verwenden (neuere MC-Versionen brauchen ein aktuelles Java).",
        ],
        "join": [
            "**Mehrspieler → Server hinzufügen**.",
            "Server-Adresse aus dem Mitglieder-Bereich eintragen.",
        ],
        "notes": [
            "Ist der Server aus, weckt ihn ein Beitrittsversuch bzw. der **Starten**-Button.",
        ],
    },
}



# Adressen kommen aus app.games (die eine Wahrheit). Die Texte oben tragen nur
# Platzhalter -- so kann keine Fundstelle beim naechsten Serverumzug uebersehen werden.
def _adressen_einsetzen() -> None:
    from app.games import address, host_of
    for _key, _g in GUIDES.items():
        _addr, _host = address(_key), host_of(_key)
        if not _addr:
            continue
        _g["address"] = _addr
        for _feld in ("install", "join", "notes"):
            if _g.get(_feld):
                _g[_feld] = [s.replace("{addr}", _addr).replace("{host}", _host) for s in _g[_feld]]


_adressen_einsetzen()

def guide_for(key: str) -> dict | None:
    return GUIDES.get(key)


def _mask(text: str) -> str:
    return _addr_re().sub(_ADDR_MASK, text)


def all_guides(public: bool = False) -> list[dict]:
    """Guides als Liste (Key inklusive + Akzentfarbe), stabile Reihenfolge.

    public=True (anonymer Besucher): Server-Adressen werden ueberall maskiert,
    das address-Feld ist leer -> Template zeigt den Mitglieder-Hinweis."""
    from app.games import FALLBACK_COLOR, GAME_META   # kein Zyklus: games importiert nichts
    out = []
    for key, g in GUIDES.items():
        color = (GAME_META.get(key) or {}).get("color", FALLBACK_COLOR)
        entry = {"key": key, "color": color, **g}
        if public:
            entry["address"] = ""
            for fld in ("install", "join", "notes"):
                if entry.get(fld):
                    entry[fld] = [_mask(s) for s in entry[fld]]
        out.append(entry)
    return out
