"""Beitritts- und Installations-Anleitungen je Spiel.

Reine Inhalts-Daten (kein Live-Zustand). Die Adressen stehen NICHT hier, sondern
kommen aus `app.games` (die eine Wahrheit), die Texte tragen nur Platzhalter.
Passwoerter/Details, die nicht oeffentlich sein sollen, werden im Mitglieder-
Bereich ergaenzt, nicht hier.

Anonyme Besucher sehen die Guides OHNE Server-Adressen (all_guides(public=True)
maskiert IP/Ports ueberall): Adressen gibt es erst nach dem Login.
"""
from __future__ import annotations

import re
from functools import lru_cache

_ADDR_MASK = "···"


@lru_cache(maxsize=1)
def _addr_re() -> re.Pattern:
    """Muster fuer „hier steht eine Server-Adresse", abgeleitet aus app.games.

    Frueher stand hier die IP fest verdrahtet. Als die Spiele am 2026-08-22 auf den
    Spiele-VPS zogen, aenderte sich die Adresse an ihrer einen Quelle, das Muster hier
    zeigte weiter auf den alten Host und traf nichts mehr. Die Maskierung lief seitdem
    ins Leere, ohne ein Zeichen zu geben: die Seite sah aus wie vorher, gab die Adressen
    samt Ports aber an jeden Besucher heraus. Aus derselben Quelle abgeleitet kann genau
    das nicht mehr passieren.

    `adress_bausteine()` statt `SERVER.values()`, seit Minecraft seine Adresse hat:
    die ist ein Hostname und keine IP, und ein Muster aus lauter IPs haette sie
    unmaskiert durchgelassen. Derselbe Fehler, nur mit anderer Schreibweise.
    """
    from app.games import adress_bausteine
    return re.compile("(?:%s)(?::\\d+)?" % "|".join(re.escape(a) for a in adress_bausteine()))

# store: Steam-/Download-Link des Clients.  address: oeffentlicher Join-Endpunkt.
GUIDES: dict[str, dict] = {
    "valheim": {
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
            "**Install & Play**, der Launcher zieht die Mods automatisch und startet DayZ.",
        ],
        "notes": [
            "Direkter Beitritt ohne DZSA klappt **nicht** (Mods fehlen), der Launcher ist Pflicht.",
            "BattlEye ist aktiv; keine Cheats/fremde Mods.",
        ],
    },
    "zomboid": {
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
            "Was die Mods ändern: Startposition frei wählbar, Charakter-Vorgeschichte, "
            "Krankheiten, dazu die Karten **Greenleaf** und **Vila Z**. Die vollständige "
            "Liste steht oben, direkt vom Server gelesen.",
        ],
    },
    "factorio": {
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
            "Content-Overhaul: mehr Bosse, mehr Ausrüstung, komfortablere Lagerhaltung. "
            "Welche Mods genau, steht oben.",
            "Keine Serverliste, Beitritt läuft über die IP (Direct-Connect).",
        ],
    },
    "terraria-wildwuchs": {
        "platform": "Steam · Windows/Linux",
        "world": "Wildwuchs (Large/Classic)",
        "address": "{addr}",
        "client": "tModLoader (Steam-App 1281930)",
        "store": "https://store.steampowered.com/app/1281930/tModLoader/",
        "install": [
            "**tModLoader** in Steam installieren (kostenlos, wenn Terraria vorhanden, App-ID 1281930).",
            "Vanilla-Terraria kann **nicht** beitreten, es muss tModLoader sein.",
        ],
        "join": [
            "tModLoader starten → **Mods** → Workshop-Mods werden beim Beitritt automatisch synchronisiert.",
            "**Multiplayer → Join via IP**, `{host}` Port `7778`.",
        ],
        "notes": [
            "Content-Overhaul: mehr Bosse, mehr Ausrüstung, komfortablere Lagerhaltung. "
            "Welche Mods genau, steht oben.",
            "Keine Serverliste, Beitritt läuft über die IP (Direct-Connect).",
            "Zweite Welt neben Greenleaf: gleiche Mods, gleiches Passwort, eigener Port 7778. Beide können gleichzeitig laufen.",
        ],
    },
    "terraria-calamity": {
        "platform": "Steam · Windows/Linux",
        "world": "Calamity (Large/Expert)",
        "address": "{addr}",
        "client": "tModLoader (Steam-App 1281930)",
        "store": "https://store.steampowered.com/app/1281930/tModLoader/",
        "install": [
            "**tModLoader** in Steam installieren (kostenlos, wenn Terraria vorhanden, App-ID 1281930).",
            "Vanilla-Terraria kann **nicht** beitreten, es muss tModLoader sein.",
        ],
        "join": [
            "tModLoader starten → **Mods** → Workshop-Mods werden beim Beitritt automatisch synchronisiert.",
            "**Multiplayer → Join via IP**, `{host}` Port `7780`.",
        ],
        "notes": [
            # Diese Zeile ist der Grund, warum dieser Guide existiert. Die Instanz
            # laeuft mit einem EIGENEN Mod-Satz (Calamity statt Thorium), und bei
            # tModLoader uebernimmt der CLIENT beim Beitritt die Mod-Liste des Servers.
            # Ein Charakter aus GreenForest/GreenerForest verliert dabei alle
            # Thorium-Items, alle Vanilla-Items in Mod-Slots und seine Konfiguration,
            # dauerhaft und ohne Rueckfrage. Dagegen laeuft hier SSC: der Charakter
            # liegt auf dem Server, der lokale wird nie angefasst. Wer das nicht weiss,
            # haelt den leeren Charakter beim ersten Beitritt fuer einen Verlust.
            "**Eigener Charakter.** Hier liegt dein Charakter auf dem Server (Server Side "
            "Characters), nicht auf deinem Rechner. Beim ersten Beitritt fängst du also neu "
            "an, und dein Charakter aus **GreenForest**/**GreenerForest** bleibt dabei "
            "unangetastet. Genau dafür ist das da: ohne SSC würde dein Thorium-Charakter "
            "beim Beitritt seine Items verlieren.",
            "Anderer Mod-Satz als die beiden Greenleaf-Welten: **Calamity** statt Thorium. "
            "Welche Mods genau, steht oben.",
            "Keine Serverliste, Beitritt läuft über die IP (Direct-Connect).",
            "Dritte Terraria-Welt neben GreenForest (7777) und GreenerForest (7778), "
            "eigener Port 7780. Alle drei können gleichzeitig laufen.",
        ],
    },
    "avorion": {
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
        "platform": "Java Edition",
        "world": "Greenleaf",
        "address": "Adresse im Mitglieder-Bereich",
        "client": "Minecraft: Java Edition",
        "store": "https://www.minecraft.net/",
        # Dieser Abschnitt ist der Grund, warum es das Feld `bietet` gibt. Bis zum
        # 2026-10-17 stand unter Minecraft nur die gesammelte Liste der 27
        # Plugin-Dateien -- „DeluxeMenus-1.14.1-Release", „PlaceholderAPI",
        # „VaultUnlocked", „LuckPerms-Bukkit". Das sind Hilfsbibliotheken, die für
        # einen Mitspieler nichts bedeuten, und was der Server tatsächlich IST, stand
        # nirgends. Genau der Fehler, den dieses Projekt bei den anderen Spielen
        # schon einmal behoben hat (dort flogen die Mod-Aufzählungen raus zugunsten
        # dessen, was die Mods bewirken) -- bei Minecraft nur andersherum.
        #
        # ⚠️ Gepflegt, nicht gemessen, und deshalb der eine Ort hier, der veralten
        # KANN. Gegen die Plugin-Liste darunter (die vom Wirt gelesen wird) prüft
        # `tests/test_minecraft_inhalt.py`, ob das Genannte überhaupt noch läuft.
        "bietet": [
            "**Sechs Welten.** Eine Spawn-Insel zum Ankommen, **Freebuild** als "
            "Bauland mit eigenen Grundstücken, eine **Farmwelt** zum Abbauen (die "
            "montags neu erzeugt wird), **Skyblock**-Inseln und eine **Schachwelt**. "
            "Gewechselt wird mit `/welten`, `/hub`, `/farm` oder `/build`.",
            "**Dein Inventar kommt überall mit.** Die Welten teilen sich eines, du "
            "musst vor dem Wechseln nichts einlagern.",
            "**14 Berufe mit Gehalt.** Abbauen, Bauen, Angeln, Kochen, Verzaubern, "
            "Jagen und acht weitere zahlen **Münzen**, je nach Tätigkeit.",
            "**Grundstücke in Freebuild.** Dein Gebiet gehört dir: fremde können "
            "darin nichts abbauen, hinstellen oder öffnen.",
            "**Zuhause-Punkte und Teleport.** Mehrere `/home`-Punkte, dazu "
            "Teleport-Anfragen zu Mitspielern.",
            "**Schach.** Gegen Mitspieler oder gegen den Rechner, mit Uhr und "
            "Wertung, in einer eigenen Welt.",
            # Kein Markdown-Link: `_md` in app/web.py kennt nur **fett** und
            # `code`, ein `[Text](ziel)` stuende hier woertlich. Erweitert wird der
            # Filter dafuer NICHT -- er muesste dann beliebige Ziele aus Guide-Texten
            # zu href machen, und das ist mehr Angriffsflaeche als ein Satz wert ist.
            # Der Weg zur Karte ist der Knopf auf der Server-Kachel, und genau den
            # nennt dieser Satz.
            "**Weltkarte.** Eine gezeichnete Karte der Bauwelt, von oben und in 3D. "
            "Der Knopf dafür steht auf der Minecraft-Kachel unter **Server**. Sie "
            "bleibt auch sichtbar, wenn der Server gerade schläft.",
        ],
        "install": [
            "Minecraft: Java Edition installieren.",
            "Passende Java-Version verwenden (neuere MC-Versionen brauchen ein aktuelles Java).",
        ],
        "join": [
            "**Mehrspieler → Server hinzufügen**.",
            "Als Serveradresse `{addr}` eintragen.",
        ],
        "notes": [
            "Ist der Server aus, weckt ihn ein Beitrittsversuch bzw. der **Starten**-Button. "
            "Du landest solange in einem Warteraum und wirst hinübergezogen, sobald die "
            "Welt geladen ist, statt in einen Timeout zu laufen.",
            "Die **Farmwelt wird montags früh neu erzeugt.** Was du dort baust oder in "
            "Kisten legst, ist danach weg: sie ist zum Abbauen da. Dauerhaft gebaut "
            "wird in Freebuild oder auf der eigenen Skyblock-Insel.",
            "Die Plugin-Liste oben ist **vom Server gelesen**, nicht gepflegt. Du "
            "brauchst nichts davon zu installieren, auch nicht die, deren Namen nach "
            "Technik klingen: das sind Bausteine, auf denen die anderen aufsetzen.",
        ],
    },
}



# EINE Liste, zwei Verwendungen: hier werden die Platzhalter ersetzt, in
# `all_guides(public=True)` werden Adressen maskiert. Bis zum 2026-10-17 stand die
# Aufzaehlung an beiden Stellen getrennt, und ein neues Textfeld haette nur in einer
# der beiden landen koennen. Die harmlose Haelfte waere ein stehengebliebenes
# `{addr}`; die andere gibt einem anonymen Besucher die Server-Adresse heraus, ohne
# dass irgendetwas auffaellt. Genau diese Maskierung lief in diesem Projekt schon
# zweimal ins Leere, beide Male unbemerkt.
TEXTFELDER = ("bietet", "install", "join", "notes")


# Adressen kommen aus app.games (die eine Wahrheit). Die Texte oben tragen nur
# Platzhalter -- so kann keine Fundstelle beim naechsten Serverumzug uebersehen werden.
def _adressen_einsetzen() -> None:
    from app.games import address, host_of
    for _key, _g in GUIDES.items():
        _addr, _host = address(_key), host_of(_key)
        if not _addr:
            continue
        _g["address"] = _addr
        for _feld in TEXTFELDER:
            if _g.get(_feld):
                _g[_feld] = [s.replace("{addr}", _addr).replace("{host}", _host) for s in _g[_feld]]


# Name und Zeichen kommen aus GAME_META, genau wie die Adressen aus `address()`.
# Bis zum 2026-10-17 standen sie hier ein ZWEITES Mal, und das ist nicht theoretisch
# schlecht gewesen: der Owner benannte die Terraria-Welten am 2026-10-13 in GreenForest
# und GreenerForest um, GAME_META bekam es mit, diese Datei nicht. Danach hiess dieselbe
# Welt auf der oeffentlichen Seite „Terraria" und im Mitglieder-Bereich „GreenForest",
# vier Tage lang, ohne dass irgendetwas rot wurde. Eine Umbenennung fasst jetzt eine
# Stelle an. Welche Felder hier fehlen DUERFEN, haelt `test_vollstaendigkeit.py` fest.
def _namen_uebernehmen() -> None:
    from app.games import GAME_META
    for _key, _g in GUIDES.items():
        _m = GAME_META.get(_key) or {}
        _g["label"] = _m.get("label", _key.replace("-", " ").title())
        _g["emoji"] = _m.get("emoji", "🎲")


_adressen_einsetzen()
_namen_uebernehmen()

def guide_for(key: str) -> dict | None:
    return GUIDES.get(key)


def _mask(text: str) -> str:
    return _addr_re().sub(_ADDR_MASK, text)


def all_guides(public: bool = False) -> list[dict]:
    """Guides als Liste (Key inklusive + Akzentfarbe), stabile Reihenfolge.

    public=True (anonymer Besucher): Server-Adressen werden ueberall maskiert,
    das address-Feld ist leer -> Template zeigt den Mitglieder-Hinweis."""
    from app import mods
    from app.games import FALLBACK_COLOR, GAME_META   # kein Zyklus: games importiert nichts
    out = []
    for key, g in GUIDES.items():
        color = (GAME_META.get(key) or {}).get("color", FALLBACK_COLOR)
        # Die Mods kommen gesammelt vom Wirt, nicht aus dem Fliesstext hier. In den
        # Schritten unten stand die Aufzaehlung „(@CF, @VPPAdminTools)" und nannte
        # damit zwei von fuenf: eine Liste, die einmal stimmte und beim naechsten
        # Mod-Update still falsch wurde, ohne je zu scheitern.
        entry = {"key": key, "color": color, "mods": mods.fuer(key), **g}
        if public:
            entry["address"] = ""
            for fld in TEXTFELDER:
                if entry.get(fld):
                    entry[fld] = [_mask(s) for s in entry[fld]]
        out.append(entry)
    return out
