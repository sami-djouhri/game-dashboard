"""Die BlueMap-Karte des Minecraft-Servers, ausgeliefert fuer Mitglieder.

WARUM DAS DASHBOARD DIE DATEIEN SELBST AUSLIEFERT und nicht BlueMaps eigener
Webserver (Port 8100) veroeffentlicht wird -- drei Gruende, der erste ist der
entscheidende:

  1. **Minecraft laeuft on-demand.** Schlaeft der Server, ist der Plugin-Webserver
     weg. Eine Karte, die man nur sehen kann, waehrend jemand spielt, ist fast
     wertlos: man schaut sie gerade dann an, wenn man NICHT spielt. Die gerenderten
     Kacheln sind statische Dateien und ueberleben den Schlaf; nur ihre
     Aktualisierung pausiert.
  2. Der Entscheid lautet „nur fuer Mitglieder". Vor dem Plugin-Webserver
     liegt keine Anmeldung, vor dieser Route die bestehende.
  3. Kein zusaetzlicher Port, keine zweite Firewall-Regel.

Gelesen wird aus einem read-only Mount, genau wie bei `mods.py` und `mcfakten.py`:
der Container kennt die Arbeitsverzeichnisse des Servers nicht und soll sie nicht
kennen.

⚠️ FastAPI ist hier langsamer als ein nginx, und das ist bewusst in Kauf genommen:
eine Clan-Seite mit einer Handvoll Mitgliedern liefert ein paar hundert Kacheln
auch so schnell genug. Wird die Karte einmal traege, gehoert ein Webserver davor
und nicht diese Datei optimiert.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

ORDNER = Path(os.getenv("MC_KARTE_DIR", "/app/karte"))

# Was ausgeliefert werden darf. BlueMap legt HTML, JS, CSS, Schriften, Bilder und
# seine Kachel-Daten (.json, teils .json.gz) ab.
# Allowlist und keine Sperrliste: was BlueMap kuenftig dazulegt, ist dann erst
# einmal nicht erreichbar -- das ist die richtige Richtung des Fehlers. Eine
# Sperrliste haette beim naechsten Dateityp stillschweigend alles durchgelassen.
ERLAUBTE_ENDUNGEN = frozenset({
    ".html", ".js", ".mjs", ".css", ".json", ".gz",
    ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".txt", ".map",
})


def vorhanden() -> bool:
    """Liegt eine gerenderte Karte vor?

    Geprueft wird die `index.html`, NICHT das Verzeichnis. Das Verzeichnis legt
    BlueMap beim ersten Start an, auch wenn es danach nichts rendert -- genau dieser
    Zustand bestand hier von der Installation bis zum 2026-10-17 (16 KB im
    data-Ordner, kein einziger Block). Ein Test auf `is_dir()` haette „Karte da"
    gemeldet und die Oberflaeche einen Link auf eine leere Seite zeigen lassen.
    """
    return (ORDNER / "index.html").is_file()


def datei(relpfad: str) -> tuple[Path, str] | None:
    """Einen Pfad unterhalb der Kartenwurzel aufloesen. None heisst: gibt es nicht.

    Containment wie in `vault.py`: beide Seiten `resolve()`, danach muss die Wurzel
    unter den Eltern liegen. Das faengt `..`, Symlinks und absolute Pfade in einem.
    """
    if not relpfad or relpfad.startswith("/"):
        relpfad = relpfad.lstrip("/")
    if not relpfad:
        relpfad = "index.html"
    # Kein Nullbyte, keine Backslash-Tricks: beides hat in BlueMap-Pfaden nichts zu
    # suchen und wuerde die Pruefung unten nur unnoetig belasten.
    if "\0" in relpfad or "\\" in relpfad:
        return None

    wurzel = ORDNER.resolve()
    ziel = (wurzel / relpfad).resolve()
    if wurzel != ziel and wurzel not in ziel.parents:
        return None
    if not ziel.is_file():
        return None
    if ziel.suffix.lower() not in ERLAUBTE_ENDUNGEN:
        return None

    typ, _ = mimetypes.guess_type(ziel.name)
    # BlueMap legt Kacheln als `*.json.gz` ab. `guess_type` meldet darauf
    # „application/json" MIT `encoding=gzip`; ohne den passenden Header haelt der
    # Browser den Inhalt fuer kaputtes JSON. Der Router setzt ihn, hier steht nur
    # der Typ.
    if ziel.name.endswith(".json.gz"):
        typ = "application/json"
    return ziel, typ or "application/octet-stream"


def ist_gzip(ziel: Path) -> bool:
    """Braucht die Antwort `Content-Encoding: gzip`?"""
    return ziel.name.endswith(".gz")
