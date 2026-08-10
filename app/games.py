"""Deklarative Anzeige-Metadaten + Transformation des Arbiter-Status in eine
UI-freundliche Kachel-Liste.

Die Liste der Games kommt DYNAMISCH aus dem Arbiter-Status (games.registry) +
Minecraft — neue Games (z. B. avorion) erscheinen automatisch, sobald sie in der
arbiter-Registry stehen, ohne Code-Aenderung hier. GAME_META liefert nur die
huebschen Extras (Emoji, Join-Hinweis); fehlt ein Eintrag, greift ein Fallback.
"""

# Statische Anzeige-Metadaten je Game-Key (arbiter-Name). Optional — Fallback unten.
GAME_META: dict[str, dict] = {
    "dayz":      {"label": "DayZ",            "emoji": "🎮", "join": "DZSA-Launcher → „Greenleaf Forest“ ODER 192.0.2.10:2302",   "slots": 4},
    "valheim":   {"label": "Valheim",         "emoji": "🪓", "join": "Serverliste „Greenleaf“ ODER 192.0.2.10:2456",              "slots": 10},
    "zomboid":   {"label": "Project Zomboid", "emoji": "🧟", "join": "Serverliste „Greenleaf“ ODER 192.0.2.10:16261",             "slots": 32},
    "factorio":  {"label": "Factorio",        "emoji": "🏭", "join": "Direct-Connect 192.0.2.10:34197",                                "slots": 8},
    "terraria":  {"label": "Terraria",        "emoji": "🌳", "join": "Direct-Connect 192.0.2.10:7777",                                 "slots": 8},
    "minecraft": {"label": "Minecraft",       "emoji": "⛏️", "join": "Server hinzufügen (LAN/Java)",                                        "slots": 20},
    "avorion":   {"label": "Avorion",         "emoji": "🚀", "join": "Steam-/Avorion-Serverliste „Greenleaf“",                         "slots": 8},
}


def _meta(key: str) -> dict:
    m = GAME_META.get(key)
    if m:
        return m
    # Fallback fuer noch nicht kuratierte Games: Titel aus dem Key, generisches Icon.
    return {"label": key.capitalize(), "emoji": "🕹️", "join": "", "slots": None}


def build_view(status: dict) -> dict:
    """Formt den rohen wake-bridge-Status in eine UI-Struktur.

    Zeigt NUR Games + Minecraft — niemals das Windows-Lab (VM 210/211/350).
    Das Lab erscheint hoechstens als Grund „Slot belegt", nie als steuerbare Kachel.
    """
    games_blk = status.get("games") or {}
    mc_blk = status.get("mc") or {}
    lab_blk = status.get("lab") or {}
    ram_mb = (status.get("ram") or {}).get("avail_mb")

    reserved_game = games_blk.get("reserved")  # das Game, das den .18-Slot haelt
    lab_reserved = bool(lab_blk.get("reserved"))

    # Wer belegt gerade den einzigen schweren Slot? (fuer „blockiert"-Anzeige)
    if reserved_game:
        holder = reserved_game
    elif lab_reserved:
        holder = "__lab__"
    elif (mc_blk.get("state") == "running") or mc_blk.get("reserved"):
        holder = "minecraft"
    else:
        holder = None

    # Kachel-Reihenfolge: registry-Games + minecraft (dedupliziert, stabil).
    registry = list(games_blk.get("registry") or [])
    order = registry + [g for g in ("minecraft",) if g not in registry]

    tiles = []
    for key in order:
        meta = _meta(key)
        if key == "minecraft":
            active = (mc_blk.get("state") == "running") or bool(mc_blk.get("reserved"))
            players = mc_blk.get("players")
        else:
            active = reserved_game == key
            players = None  # per-Game-Spielerzahl ist (noch) nicht im status.json

        if active:
            state = "active"
        elif holder and holder != key:
            state = "blocked"
        else:
            state = "sleeping"

        tiles.append({
            "key": key,
            "label": meta["label"],
            "emoji": meta["emoji"],
            "join": meta["join"],
            "slots": meta.get("slots"),
            "state": state,
            "players": players,
        })

    holder_label = None
    if holder == "__lab__":
        holder_label = "Windows-Lab"
    elif holder:
        holder_label = _meta(holder)["label"]

    return {
        "node": status.get("node"),
        "ts": status.get("ts"),
        "mode": status.get("mode"),
        "ram_mb": ram_mb,
        "gate_up": bool((status.get("gate") or {}).get("up")),
        "holder": holder,
        "holder_label": holder_label,
        "games": tiles,
    }


def known_games(status: dict) -> set[str]:
    """Erlaubte Game-Keys fuer Steuer-Aktionen (Anti-Injection).

    Live aus der Registry abgeleitet -> neue Games sind automatisch erlaubt,
    Unfug-Strings werden abgewiesen.
    """
    games_blk = status.get("games") or {}
    return set(games_blk.get("registry") or []) | {"minecraft"}
