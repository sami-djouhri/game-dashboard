"""Deklarative Anzeige-Metadaten + Transformation des Arbiter-Status in eine
UI-freundliche Kachel-Liste.

Die Liste der Games kommt DYNAMISCH aus dem Arbiter-Status (games.registry) +
Minecraft, neue Games (z. B. avorion) erscheinen automatisch, sobald sie in der
arbiter-Registry stehen, ohne Code-Aenderung hier. GAME_META liefert nur die
huebschen Extras (Emoji, Join-Hinweis); fehlt ein Eintrag, greift ein Fallback.
"""

import time

# ── Server-Adressen: EINE Wahrheit ───────────────────────────────────
# Bis zum 2026-08-22 stand die netcup-IP zwoelfmal verstreut in dieser Datei und in
# guides.py. Beim Umzug auf gamehost war jede Fundstelle einzeln zu suchen -- und eine
# uebersehene Zeile schickt Spieler auf einen Server, der dort nicht mehr steht (genau
# so war DayZ 13 Tage lang unbeitretbar). Zieht ein Spiel um, aendert sich hier EINE Zeile.
SERVER: dict[str, str] = {
    "gamehost": "192.0.2.10",    # netcup VPS Lite 3 - alle Spielserver, host-nativ
    "netcup": "192.0.2.10",    # netcup RS-1000 - Mail + Web (kein Spiel mehr)
}

ENDPOINTS: dict[str, tuple[str, int]] = {
    "dayz": ("gamehost", 2302),
    "valheim": ("gamehost", 2456),
    "terraria": ("gamehost", 7777),
    "zomboid": ("gamehost", 16261),
    "factorio": ("gamehost", 34197),
    "avorion": ("gamehost", 27020),
}


def host_of(game: str) -> str:
    ep = ENDPOINTS.get(game)
    return SERVER.get(ep[0], "") if ep else ""


def port_of(game: str) -> int | None:
    ep = ENDPOINTS.get(game)
    return ep[1] if ep else None


def address(game: str) -> str:
    ep = ENDPOINTS.get(game)
    return f"{SERVER[ep[0]]}:{ep[1]}" if ep else ""


# Statische Anzeige-Metadaten je Game-Key (arbiter-Name). Optional, Fallback unten.
# color = Akzentfarbe der Spiel-Identitaet (Karten-Topline, Emoji-Kachel, Badges) —
# entsaettigt genug fuers dunkle Wald-Theme.
GAME_META: dict[str, dict] = {
    "dayz":      {"label": "DayZ",            "emoji": "🎮", "color": "#97a45e", "join": f"DZSA-Launcher → „Greenleaf Forest“ ODER {address('dayz')}",   "slots": 4},
    "valheim":   {"label": "Valheim",         "emoji": "🪓", "color": "#6ea8dc", "join": f"Serverliste „Greenleaf“ ODER {address('valheim')}",              "slots": 10},
    "zomboid":   {"label": "Project Zomboid", "emoji": "🧟", "color": "#d96f5c", "join": f"Serverliste „Greenleaf“ ODER {address('zomboid')}",             "slots": 32},
    "factorio":  {"label": "Factorio",        "emoji": "🏭", "color": "#e0913f", "join": f"Direct-Connect {address('factorio')}",                                "slots": 8},
    "terraria":  {"label": "Terraria",        "emoji": "🌳", "color": "#58c98b", "join": f"Direct-Connect {address('terraria')}",                                 "slots": 8},
    "minecraft": {"label": "Minecraft",       "emoji": "⛏️", "color": "#7cc95e", "join": "Server hinzufügen (LAN/Java)",                                        "slots": 20},
    "avorion":   {"label": "Avorion",         "emoji": "🚀", "color": "#9b85e0", "join": "Steam-/Avorion-Serverliste „Greenleaf“",                         "slots": 8},
}

FALLBACK_COLOR = "#64d178"   # var(--leaf)

# So lange gilt Schweigen nach dem Startbefehl als „bootet noch". Danach ist es ein
# Befund und wird auch so beschriftet. Grosszuegig gewaehlt: DayZ, das schwerste Spiel,
# braucht gemessene 2-3 Minuten.
STARTFENSTER_S = 360

# Dauerlaeufer: Server, die in KEINER Arbiter-Registry stehen und deshalb weder geweckt
# noch schlafen gelegt werden koennen. Ihr Zustand kommt aus einer eigenen Probe, nicht aus
# dem Arbiter-Status. `probe` bestimmt, WIE geprueft wird:
#   a2s   Steam-Abfrage, liefert echte Spielerzahl
#   tcp   nur "Port nimmt Verbindungen an" (Terraria kennt keine Abfrage)
#   keine gar nicht pruefbar -> eigener Zustand "unbekannt" statt eines roten "keine
#         Antwort" fuer einen Server, der in Wahrheit laeuft.
#
# Seit dem 2026-08-22 ist die Liste LEER: alle Spielserver liegen auf dem Spiele-VPS und
# werden dort vom zweiten Arbiter verwaltet — sie sind wieder weckbar und ihr Zustand steht
# im Arbiter-Status. Ein Eintrag hier waere jetzt schaedlich: die Seite meldete "dauerhaft
# an" fuer einen Server, der gerade schlaeft, und verschwiege den Weck-Knopf. Der
# Mechanismus bleibt fuer den naechsten Server, der ausserhalb steht.
ALWAYS_ON: dict[str, dict] = {}


def _meta(key: str) -> dict:
    m = GAME_META.get(key)
    if m:
        return m
    # Fallback fuer noch nicht kuratierte Games: Titel aus dem Key, generisches Icon.
    return {"label": key.capitalize(), "emoji": "🕹️", "color": FALLBACK_COLOR, "join": "", "slots": None}


def build_view(status: dict, always_on: dict | None = None,
               arbiter_ok: bool = True) -> dict:
    """Formt den rohen wake-bridge-Status in eine UI-Struktur.

    Zeigt NUR Games + Minecraft, niemals das Windows-Lab (VM 210/211/350).
    Das Lab erscheint hoechstens als Grund „Slot belegt", nie als steuerbare Kachel.

    `arbiter_ok=False` heisst: die Bridge hat nicht geantwortet, `status` ist leer.
    Die Dauerlaeufer werden trotzdem angezeigt — sie haengen gar nicht am Arbiter,
    ihr Zustand kommt aus der eigenen Probe. Alles, was der Arbiter verwaltet, ist
    dann UNBEKANNT und wird auch so beschriftet: eine leere Seite sieht aus wie
    "nichts laeuft", und das waere die falsche Auskunft.
    """
    games_blk = status.get("games") or {}
    mc_blk = status.get("mc") or {}
    lab_blk = status.get("lab") or {}
    ram_mb = (status.get("ram") or {}).get("avail_mb")

    # Seit dem Mehr-Spiel-Umbau des Arbiters (2026-08-22) laufen mehrere Spiele
    # gleichzeitig: reserved_all ist die Wahrheit, reserved (Einzahl) blieb nur fuer
    # aeltere Leser erhalten. Wer weiter nur reserved liest, malt sechs von sieben
    # Kacheln faelschlich als „blockiert", weil er einen Slot annimmt, den es nicht
    # mehr gibt. detail liefert dazu die Spielerzahl je Spiel.
    reserved_all = games_blk.get("reserved_all")
    if reserved_all is None:
        einer = games_blk.get("reserved")
        reserved_all = [einer] if einer else []
    detail = games_blk.get("detail") or {}
    lab_reserved = bool(lab_blk.get("reserved"))

    # Startbarkeit VOR dem Klick: der Arbiter nennt in games.bedarf die Schwelle, gegen
    # die er selbst prueft (min_free_mb je Spiel), und zieht dabei ab, was gerade
    # startende Spiele noch belegen werden. Beides hier nachzurechnen ist die einzige
    # Art, dieselbe Antwort zu geben wie er — eine im Dashboard gepflegte Kopie der
    # Zahlen waere beim naechsten Nachmessen still falsch.
    bedarf = games_blk.get("bedarf") or {}
    startend_mb = (status.get("ram") or {}).get("reserviert_startend_mb") or 0
    frei_mb = (ram_mb - startend_mb) if isinstance(ram_mb, int) else None

    # „Blockiert" heisst jetzt nur noch: eine reservierte Lab-Sitzung hat Vorrang.
    # Zwischen Spielen blockiert nichts mehr — es entscheidet der freie Speicher,
    # und das sieht man erst beim Startversuch, nicht an der Kachel.
    holder = "__lab__" if lab_reserved else None

    # Kachel-Reihenfolge: registry-Games + minecraft (dedupliziert, stabil).
    registry = list(games_blk.get("registry") or [])
    dauerlaeufer = [g for g in ALWAYS_ON if g not in registry]
    order = registry + dauerlaeufer + [g for g in ("minecraft",) if g not in registry]
    a2s = always_on or {}

    # Multi-Welten (arbiter emit_state): je Game {active, list} — nur Games mit
    # multi_world in der Arbiter-Registry tauchen hier auf.
    worlds_blk = games_blk.get("worlds") or {}

    tiles = []
    for key in order:
        meta = _meta(key)
        pruefbar = True          # ist der Zustand dieser Kachel ueberhaupt messbar?
        seit_s = None            # Sekunden seit dem Startbefehl (nur waehrend des Startens)
        if key in ALWAYS_ON:
            info = a2s.get(key)
            # "dauerhaft an" ist eine Aussage ueber die Konfiguration und stimmt immer.
            # Fehlt die Messung (Factorio: UDP ohne Abfrage), heisst das NICHT "offline" —
            # das waere eine erfundene Fehlermeldung. Es heisst nur: keine Spielerzahl.
            pruefbar = not (info or {}).get("unbekannt", False)
            state = "always_on" if info else "offline"
            players = info.get("players") if info else None
        elif not arbiter_ok:
            # Ohne Arbiter wissen wir ueber diese Rolle nichts — nicht "schlaeft" behaupten.
            state, players = "unbekannt", None
        elif key in reserved_all:
            # Vom Arbiter verwaltet und reserviert -> soll laufen. „Soll" ist aber nicht
            # „ist": ein Spielserver braucht nach dem Startbefehl 1-3 Minuten (DayZ eher
            # 3), bis er Beitritte annimmt. Bis 2026-08-24 zeigte die Kachel in dieser
            # Zeit „läuft" — wer daraufhin beitrat, lief in einen Timeout und hielt den
            # Server fuer kaputt. erreichbar=False heisst genau: gefragt, noch keine
            # Antwort. Fehlt die Angabe (aeltere Arbiter-Version), bleibt es bei „läuft".
            d = detail.get(key) or {}
            players = d.get("players")
            if players is None and key == "minecraft":
                players = mc_blk.get("players")
            state = "active"
            if d.get("erreichbar") is False:
                # Nach dieser Zeit ist Schweigen kein Startvorgang mehr, sondern ein
                # Befund. Ein ewiges „startet gerade …" waere die bequemere Anzeige und
                # die falsche: sie sieht nach Fortschritt aus, wo keiner mehr stattfindet.
                seit = time.time() - (d.get("since") or 0) if d.get("since") else 0
                state = "stumm" if seit > STARTFENSTER_S else "starting"
                seit_s = int(seit)
        elif key == "minecraft" and ((mc_blk.get("state") == "running") or mc_blk.get("reserved")):
            # Rueckfall fuer den Ort, an dem Minecraft noch die eingebaute Sonderrolle ist.
            players, state = mc_blk.get("players"), "active"
        else:
            players = None
            state = "blocked" if holder else "sleeping"

        winfo = worlds_blk.get(key) or {}
        # Reicht der Speicher fuer DIESEN Start? Dieselbe Rechnung wie precheck_game im
        # Arbiter. None heisst „keine Aussage" (kein Bedarf hinterlegt oder Sensorfehler)
        # und darf nie zu einem gesperrten Knopf fuehren: eine geratene Absage ist
        # schlechter als ein Versuch, der ehrlich abgelehnt wird.
        b = bedarf.get(key) or {}
        schwelle = b.get("min_free_mb")
        startbar = None if (frei_mb is None or schwelle is None) else frei_mb >= schwelle
        tiles.append({
            "key": key,
            "label": meta["label"],
            "emoji": meta["emoji"],
            "color": meta.get("color", FALLBACK_COLOR),
            "join": meta["join"],
            "slots": meta.get("slots"),
            "state": state,
            "players": players,
            "startet_seit_s": seit_s,
            "startbar": startbar,
            "bedarf_mb": b.get("ram_mb"),
            "schwelle_mb": schwelle,
            # Reserviert = kein Auto-Off, keine Verdraengung. Die Oberflaeche braucht
            # den Zustand, um den Knopf richtig herum zu beschriften (Reservieren vs.
            # Reservierung aufheben) — ein Schalter, der seinen Zustand nicht kennt,
            # laedt zum Doppelklick auf das Falsche ein.
            "reserviert": bool((detail.get(key) or {}).get("geschuetzt")),
            "always_on": key in ALWAYS_ON,
            "pruefbar": pruefbar,
            "multi_world": bool(winfo),
            "world": winfo.get("active"),
            "worlds": winfo.get("list") or [],
        })

    holder_label = None
    if holder == "__lab__":
        holder_label = "Windows-Lab"
    elif holder:
        holder_label = _meta(holder)["label"]

    # Wer laeuft gerade + wie viele spielen? (fuer Landing-Puls / Herb-Presence)
    online_total = sum(t["players"] for t in tiles if isinstance(t.get("players"), int) and t["players"] > 0)
    active_tile = next((t for t in tiles if t["state"] == "active" and not t["always_on"]), None)

    return {
        "node": status.get("node"),
        "ts": status.get("ts"),
        "mode": status.get("mode"),
        "ram_mb": ram_mb,
        # Der Wert, gegen den die Kacheln ihre Startbarkeit rechnen. Ohne ihn zeigte
        # die Kopfzeile den ROHEN freien Speicher, waehrend die Kacheln daneben
        # "braucht 2,4 GB frei, so viel ist es gerade nicht" schrieben — bei 5,1 GB
        # in der Ueberschrift. Beides stimmte, aber nur eines war gemeint: ein
        # startender Server hat seinen Speicher noch nicht belegt und bekommt ihn
        # trotzdem. Zwei Zahlen, die sich auf einem Bild widersprechen, liest man
        # als Fehler der Seite.
        "frei_mb": frei_mb,
        "startend_mb": startend_mb,
        "gate_up": bool((status.get("gate") or {}).get("up")),
        "holder": holder,
        "holder_label": holder_label,
        "online_total": online_total,
        "active_game": active_tile["key"] if active_tile else None,
        "active_label": active_tile["label"] if active_tile else None,
        "games": tiles,
    }


def public_summary(view: dict) -> dict:
    """Reduzierte Sicht fuer die oeffentliche Landing (kein RAM/Node-Interna,
    keine Steuerung), nur, was gerade laeuft und wie viele spielen."""
    return {
        "online_total": view.get("online_total", 0),
        "active_game": view.get("active_game"),
        "active_label": view.get("active_label"),
        "games": [
            {"key": g["key"], "label": g["label"], "emoji": g["emoji"],
             "color": g.get("color"), "always_on": g.get("always_on", False),
             "state": g["state"], "players": g["players"], "slots": g.get("slots"),
             "world": g.get("world")}
            for g in view.get("games", [])
        ],
    }


def known_games(status: dict) -> set[str]:
    """Erlaubte Game-Keys fuer Steuer-Aktionen (Anti-Injection).

    Live aus der Registry abgeleitet -> neue Games sind automatisch erlaubt,
    Unfug-Strings werden abgewiesen.
    """
    games_blk = status.get("games") or {}
    return set(games_blk.get("registry") or []) | {"minecraft"}
