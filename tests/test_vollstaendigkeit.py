"""Jedes Spiel muss ueberall ankommen, wo es hingehoert.

WARUM ES DIESE DATEI GIBT (2026-10-17):
Ein Spiel steht an fuenf Stellen: `ENDPOINTS` und `GAME_META` in `app/games.py`,
`GUIDES` in `app/guides.py`, der Szenen-Zweig in `_scenes.html` und `SAMMLER` in
`gamehost/mods-sammeln.py`. Die dritte Terraria-Instanz (Calamity, live seit dem
2026-10-13) stand in zweien davon und fehlte in dreien. Gemessen am 2026-10-17 war
die Folge:

  * keine Kachel auf der OEFFENTLICHEN Landing (die rendert aus `GUIDES`, nicht aus
    dem Arbiter-Status) und damit „welten registriert: 8", wo live neun standen,
  * keine Beitritts-Anleitung -- ausgerechnet fuer die Instanz, bei der ein
    unvorbereiteter Beitritt den Charakter kostet,
  * `mods.bekannt: false`, also gar keine Mod-Angabe, obwohl die Datei dalag.

Keiner dieser drei Zustaende ist ein Fehler, der auffaellt: eine fehlende Kachel
sieht aus wie ein Spiel, das es nicht gibt, und die Seite war durchgehend gruen.
Genau deshalb steht die Pruefung hier und nicht in einer Doku-Zeile.

⚠️ GRENZE DIESER DATEI: sie prueft die Stellen GEGENEINANDER, nicht gegen die
Arbiter-Registry auf dem Spiele-VPS -- die ist im Test nicht erreichbar, und das
soll so bleiben (kein Test geht ins Netz). Ein Spiel, das in der Registry steht und
in `app/games.py` gar nicht erst eingetragen wurde, findet sie also NICHT. Dafuer
gibt es den zweiten Waechter zur Laufzeit: `games.kacheln()` zaehlt die Spiele aus
dem Arbiter-Status ohne Guide und meldet sie (siehe `ohne_anleitung`).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app import games, guides

WURZEL = Path(__file__).resolve().parent.parent

# Pflichtfelder eines Guides. `label`/`emoji` stehen bewusst NICHT dabei: die traegt
# `_namen_uebernehmen()` aus GAME_META nach. Siehe test_kein_zweiter_name unten.
PFLICHTFELDER = ("platform", "world", "client", "store", "install", "join")


def _spiele() -> set[str]:
    """Alle Spiele, die der Code kennt."""
    return set(games.ENDPOINTS) | set(games.GAME_META)


def test_jedes_spiel_hat_eine_anleitung():
    """Ohne GUIDES-Eintrag: keine Landing-Kachel und keine Anleitung."""
    fehlen = sorted(_spiele() - set(guides.GUIDES))
    assert not fehlen, (
        f"Spiele ohne GUIDES-Eintrag in app/guides.py: {fehlen}. "
        "Folge: keine Kachel auf der oeffentlichen Landing, falsche Zahl im Puls "
        "(die zaehlt guides|length) und keine Beitritts-Anleitung."
    )


def test_jede_anleitung_hat_ein_spiel():
    """Die Gegenrichtung: ein Guide ohne GAME_META-Eintrag bekaeme einen aus dem Key
    geratenen Namen, und ein Guide ohne ENDPOINTS-Eintrag keine Adresse -- dann steht
    in der Anleitung der rohe Platzhalter `{addr}`."""
    ohne_meta = sorted(set(guides.GUIDES) - set(games.GAME_META))
    assert not ohne_meta, f"Guides ohne GAME_META (Name/Farbe/Emoji fehlen): {ohne_meta}"


def test_keine_rohen_platzhalter_in_den_texten():
    """`{addr}`/`{host}` muessen ersetzt sein, sonst steht die Klammer in der Oberflaeche.

    Trifft jedes Spiel ohne ENDPOINTS-Eintrag, denn `_adressen_einsetzen()`
    ueberspringt es (`if not _addr: continue`) und laesst den Platzhalter stehen.
    Genau so sah Minecrafts Anleitung bis zum 2026-09-11 aus."""
    fundstellen = []
    for key, g in guides.GUIDES.items():
        for feld in ("address", "install", "join", "notes"):
            wert = g.get(feld) or []
            for text in ([wert] if isinstance(wert, str) else wert):
                if "{addr}" in text or "{host}" in text:
                    fundstellen.append(f"{key}.{feld}: {text[:60]}")
    assert not fundstellen, "Nicht ersetzte Platzhalter: " + "; ".join(fundstellen)


def test_jedes_textfeld_wird_maskiert():
    """Jede Liste von Saetzen in GUIDES muss in `TEXTFELDER` stehen.

    An dieser Liste haengen ZWEI Dinge: das Ersetzen der `{addr}`-Platzhalter und
    die Maskierung der Adressen fuer anonyme Besucher. Ein Feld, das sie nicht kennt,
    bekommt beides nicht. Die harmlose Haelfte waere ein stehengebliebenes `{addr}`
    im Text; die andere gibt die Server-Adresse an jeden Besucher heraus, und genau
    das ist in diesem Projekt schon zweimal passiert, beide Male unbemerkt, weil die
    Seite danach aussah wie vorher.

    Geprueft wird nach FORM, nicht nach einer zweiten Namensliste: alles, was eine
    Liste von Zeichenketten ist, ist Fliesstext und gehoert maskiert."""
    uebersehen = sorted({
        feld for g in guides.GUIDES.values()
        for feld, wert in g.items()
        if feld not in guides.TEXTFELDER
        and isinstance(wert, list) and wert and all(isinstance(s, str) for s in wert)
    })
    assert not uebersehen, (
        f"Textfelder ausserhalb von TEXTFELDER: {uebersehen}. Sie werden weder von "
        "_adressen_einsetzen() noch von der Maskierung in all_guides(public=True) "
        "erfasst."
    )


def test_pflichtfelder_vollstaendig():
    luecken = [f"{key}.{feld}" for key, g in guides.GUIDES.items()
               for feld in PFLICHTFELDER if not g.get(feld)]
    assert not luecken, f"Leere Pflichtfelder: {luecken}"


def test_kein_zweiter_name():
    """Name und Zeichen duerfen nur in GAME_META stehen.

    Der konkrete Anlass: der Owner benannte die Terraria-Welten am 2026-10-13 in
    GreenForest/GreenerForest um. `GAME_META` bekam es mit, das damals zweite
    `label` in `guides.py` nicht -- vier Tage lang hiess dieselbe Welt oeffentlich
    „Terraria" und intern „GreenForest". Wer das Feld wieder in die Literale
    eintraegt, baut genau diesen Drift neu, und er wird wieder nicht auffallen."""
    quelle = (WURZEL / "app" / "guides.py").read_text(encoding="utf-8")
    literal = None
    for knoten in ast.walk(ast.parse(quelle)):
        # BEIDE Zuweisungsformen. `GUIDES: dict[str, dict] = {...}` ist ein
        # ast.AnnAssign mit `.target` (Singular), kein ast.Assign mit `.targets`.
        # Der erste Entwurf dieser Pruefung kannte nur die zweite Form, fand damit
        # nie einen Knoten, lief durch die Schleife und war gruen -- auch mit einem
        # testweise wieder eingetragenen `label`. Ein Pruefer, der seinen
        # Gegenstand nicht findet, muss scheitern und nicht schweigen; deshalb
        # steht unter der Schleife die Behauptung, dass es ihn gibt.
        if isinstance(knoten, ast.AnnAssign):
            ziele = [knoten.target]
        elif isinstance(knoten, ast.Assign):
            ziele = knoten.targets
        else:
            continue
        if any(getattr(z, "id", "") == "GUIDES" for z in ziele):
            literal = knoten.value
            break

    assert isinstance(literal, ast.Dict), \
        "GUIDES-Literal in app/guides.py nicht gefunden -- diese Pruefung greift so nicht"
    for key, eintrag in zip(literal.keys, literal.values):
        felder = {k.value for k in eintrag.keys if isinstance(k, ast.Constant)}
        doppelt = felder & {"label", "emoji"}
        assert not doppelt, (
            f"GUIDES['{key.value}'] fuehrt {sorted(doppelt)} selbst. "
            "Diese Felder kommen aus GAME_META in app/games.py (eine Wahrheit), "
            "sonst laeuft eine Umbenennung auseinander."
        )


def test_jedes_spiel_hat_eine_eigene_szene():
    """Ohne eigenen Zweig in `_scenes.html` bekommt ein Spiel die Fallback-Zeichnung.

    Die ist nicht kaputt, aber sie ist fuer jedes Spiel dieselbe -- auf einer
    Kachelwand, auf der die Zeichnung sagt, WELCHE Welt gemeint ist, hebt ein Spiel
    damit seine Unterscheidbarkeit auf. Calamity sah bis zum 2026-10-17 so aus."""
    vorlage = (WURZEL / "app" / "templates" / "_scenes.html").read_text(encoding="utf-8")
    # Jeden `key == 'x'` und `key in ('x', 'y')`-Zweig einsammeln.
    abgedeckt = set(re.findall(r"key\s*==\s*'([^']+)'", vorlage))
    for gruppe in re.findall(r"key\s+in\s+\(([^)]*)\)", vorlage):
        abgedeckt |= set(re.findall(r"'([^']+)'", gruppe))
    fehlen = sorted(_spiele() - abgedeckt)
    assert not fehlen, f"Spiele ohne eigene Szene in _scenes.html: {fehlen}"


def test_mod_sammler_deckt_alle_spiele():
    """`gamehost/mods-sammeln.py` laeuft auf dem Wirt, nicht hier -- geprueft wird
    deshalb seine SAMMLER-Tabelle im Quelltext.

    Ein fehlender Eintrag ist der leiseste der fuenf Faelle: das Spiel bekommt
    `bekannt: false`, und die Oberflaeche zeigt daraufhin voellig richtig gar keine
    Mods. Von „dieser Server hat keine Mods" ist das von aussen nicht zu
    unterscheiden, und genau darum wird es nicht gemeldet, sondern geprueft."""
    quelle = (WURZEL / "gamehost" / "mods-sammeln.py").read_text(encoding="utf-8")
    block = re.search(r"SAMMLER\s*=\s*\{(.*?)\}", quelle, re.S)
    assert block, "SAMMLER-Tabelle in gamehost/mods-sammeln.py nicht gefunden"
    abgedeckt = set(re.findall(r"\"([^\"]+)\"\s*:", block.group(1)))
    fehlen = sorted(_spiele() - abgedeckt)
    assert not fehlen, f"Spiele ohne Mod-Sammler: {fehlen}"


def test_pruefstand_hat_jedes_spiel_im_bild():
    """Was im Pruefstand fehlt, sieht nie jemand an.

    Zwei Dateien, zwei verschiedene Luecken, beide waren offen:
      * `scripts/ansehen_aufbereiten.py` bestimmt, WELCHE Kacheln fotografiert
        werden. `terraria-wildwuchs` stand dort seit seiner Einfuehrung nicht, war
        also in keinem einzigen Bild.
      * `scripts/pruefdaten-mods.json` speist ihre Mod-Angaben. Fehlt ein Spiel
        dort, zeigt seine Kachel im Bild keine Mods, und auf einem Pruefbild sieht
        „keine Mods" genau wie die Wahrheit aus.

    Die erste Luecke fand diese Pruefung in ihrer ersten Fassung NICHT: die sah nur
    in die JSON-Datei, und der fehlende Kachel-Eintrag fiel erst im Bild auf. Ein
    Pruefer findet eben nur, wonach er sieht."""
    import json
    daten = json.loads((WURZEL / "scripts" / "pruefdaten-mods.json")
                       .read_text(encoding="utf-8"))
    fehlen = sorted(_spiele() - set(daten.get("spiele") or {}))
    assert not fehlen, f"Spiele ohne Mod-Pruefdaten (Kachel zeigt im Bild nichts): {fehlen}"

    stub = (WURZEL / "scripts" / "ansehen_aufbereiten.py").read_text(encoding="utf-8")
    gestellt = set(re.findall(r"_spiel\(\s*\"([^\"]+)\"", stub))
    fehlen = sorted(_spiele() - gestellt)
    assert not fehlen, f"Spiele in keinem Pruefbild: {fehlen}"


@pytest.mark.parametrize("key", sorted(set(games.ENDPOINTS) - games.NUR_ABFRAGE))
def test_adresse_je_spiel_aufloesbar(key):
    """Jeder Beitritts-Endpunkt ergibt eine Adresse mit Host und Port.

    Faengt den Tippfehler im Server-Namen ab: `("gamevpn", 7777)` wuerde sonst eine
    Adresse `":7777"` liefern, die wie eine Adresse aussieht und keine ist."""
    adresse = games.address(key)
    assert re.fullmatch(r"[\w.-]+:\d+", adresse), f"{key}: unbrauchbare Adresse {adresse!r}"


@pytest.mark.parametrize("key", sorted(games.NUR_ABFRAGE))
def test_abfrage_endpunkte_geben_keine_adresse_aus(key):
    """Die Gegenrichtung, und der eigentliche Punkt.

    Avorions Port 27020 ist sein Steam-Abfrageport, kein Beitrittsweg. Solange
    `address()` ihn ausgab, ueberschrieb `_adressen_einsetzen()` damit den bewusst
    gesetzten Guide-Text „Steam-/Avorion-Serverliste" -- die Anleitung nannte also
    eine IP und sagte eine Zeile darunter „kein Direct-IP noetig" -- und die Kachel
    bot einen Kopier-Knopf fuer eine Adresse an, auf der kein Client beitritt."""
    assert games.address(key) == "", \
        f"{key} steht in NUR_ABFRAGE, liefert aber eine Beitritts-Adresse"
    text = guides.GUIDES[key]["address"]
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", text), \
        f"{key}: im Guide steht trotzdem eine IP ({text!r})"
