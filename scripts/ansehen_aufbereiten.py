#!/usr/bin/env python3
"""Macht die gerenderten Seiten offline-tauglich und stellt der Oberflaeche Antworten.

Die Kacheln entstehen erst im Browser aus /api/status. Ohne gestellte Antwort
fotografiert man ein leeres Gitter mit drei grauen Platzhaltern, also genau das,
was man nicht pruefen wollte.

Die gestellten Daten zeigen ALLE Kachel-Zustaende auf einem Bild: laufend mit
Spielern, laufend+reserviert, startend, stumm, schlafend, schlafend-mit-zu-wenig-
Speicher, Mehr-Welten. Live bekommt man die nie zusammen zu sehen, und gerade die
seltenen sind die, in denen das Layout bricht.
"""
import json
import pathlib
import sys

OUT = pathlib.Path(sys.argv[1])

# Mod-Listen aus EINER Quelle: dieselbe Datei, die ansehen.sh dem Pruefstand-
# Container als /pruefmods/mods.json einhaengt. Sonst haette der Browser-Stub andere
# Mods gezeigt als die serverseitig gerenderten Guides, und man haette den
# Unterschied fuer einen Fehler in der Anzeige gehalten.
# Ein Schnappschuss vom Wirt (2026-09-06), bewusst nicht erfunden: an erfundenen
# Namen sieht man Umbrueche und Laengen nicht, die es wirklich gibt.
_MODS = json.loads((pathlib.Path(__file__).parent / "pruefdaten-mods.json")
                   .read_text(encoding="utf-8"))["spiele"]


def _mods(key: str, welt: str | None = None) -> dict:
    """Nachbildung von app.mods.fuer(). Muss dieselbe FORM liefern, nicht nur
    dieselben Namen: als hier `je_welt` fehlte, hielt die Kachel Zomboids Mods fuer
    serverweit und schrieb „alle Welten laufen mit denselben 7 Mods" unter ein
    Panel, das direkt darueber zwei verschiedene Listen zeigte. Ein Pruefstand, der
    eine andere Form stellt als das Backend liefert, prueft die falsche Seite.
    Wer app/mods.py aendert, aendert diese Funktion mit.
    """
    e = _MODS.get(key) or {}
    if not e.get("gelesen"):
        return {"bekannt": False, "mods": [], "serverseitig": False,
                "je_welt": False, "welten_bekannt": 0, "welt": ""}
    je_welt = bool(e.get("je_welt"))
    welten = e.get("welten") or {}
    liste = (list(welten[welt]) if (je_welt and welt and welt in welten)
             else list(e.get("mods") or []))
    return {"bekannt": True, "mods": liste, "je_welt": je_welt,
            "welten_bekannt": len(welten),
            "welt": welt if (je_welt and welt and welt in welten) else "",
            "serverseitig": bool(e.get("serverseitig"))}

# ── Name, Zeichen, Farbe, Platzzahl und Adresse aus DEM Modul, das die Seite auch
# benutzt. Bis zum 2026-10-17 standen sie hier abgeschrieben, und das war bereits
# falsch: die Terraria-Welten heissen seit dem 13.10. GreenForest und GreenerForest,
# der Pruefstand zeigte weiter „Terraria". Ein Pruefstand, der andere Namen zeigt als
# die Seite, prueft die Seite nicht mehr -- und niemand wird ihm das ansehen, weil ein
# Bild mit plausiblen Namen genau richtig aussieht.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.games import GAME_META, address  # noqa: E402


# Der Aktivitaets-Streifen kommt aus `play_sessions`, also aus der Datenbank,
# und die Wegwerf-Instanz des Prueflaufs startet mit einer LEEREN. Ohne gestellte
# Werte stuenden hier vierzehn leere Balken auf jeder Kachel: das Bild saehe
# vollstaendig aus und zeigte doch nur den Leerzustand. Gestellt sind deshalb
# bewusst alle drei Faelle, die im Betrieb vorkommen -- eine lebendige Runde,
# eine mit langer Pause und eine, auf der seit zwei Wochen niemand war.
_TAGE = 14


def _aktiv(muster: list[float] | None = None, zuletzt_s: int | None = None) -> dict:
    """Ein gestellter Streifen. `muster` wird rechtsbuendig eingesetzt (heute rechts)."""
    tage = [0.0] * _TAGE
    for i, wert in enumerate(muster or []):
        stelle = _TAGE - len(muster or []) + i
        if 0 <= stelle < _TAGE:
            tage[stelle] = float(wert)
    return {"tage": tage, "zuletzt_s": zuletzt_s}


def _spiel(key, **zustand):
    """Ein Kachel-Eintrag: Stammdaten aus GAME_META, Zustand aus dem Aufruf."""
    m = GAME_META[key]
    # `fakten` gehoert in die Vorgabe, nicht nur zu Minecraft: die echte App setzt
    # das Feld bei JEDEM Spiel (leer, wenn es keine gibt). Ein Stub, der es bei den
    # anderen weglaesst, bildet eine Struktur ab, die es so nicht gibt.
    grund = {"startet_seit_s": None, "startbar": True, "reserviert": False,
             "always_on": False, "pruefbar": True, "multi_world": False,
             "world": None, "worlds": [], "players": None, "fakten": {},
             # Vorgabe ist der LEERZUSTAND, nicht ein gefuellter Streifen: so
             # muss jedes Spiel, das Aktivitaet zeigen soll, sie ausdruecklich
             # bekommen, und der haeufigste Fall im Bild bleibt der echte.
             "aktivitaet": _aktiv()}
    return {"key": key, "label": m["label"], "emoji": m["emoji"], "color": m["color"],
            "join": m["join"], "slots": m["slots"], "address": address(key),
            **grund, **zustand}


# ── Gestellter Arbiter-Status (Form wie games.build_view + api.status) ──
STATUS = {
    "ok": True, "arbiter_ok": True, "is_admin": True, "may_start": True,
    "node": "gamehost", "mode": "systemd", "gate_up": True,
    "ram_mb": 15200, "frei_mb": 6100, "startend_mb": 5700,
    "holder": None, "holder_label": None,
    "online_total": 5, "active_game": "valheim",
    "active_label": GAME_META["valheim"]["label"],
    # BEWUSST gefuellt, obwohl live leer: sonst ist der Pflege-Hinweis der
    # Admin-Lagezeile in keinem Pruefbild, und ein Banner mit Text ist genau das, was
    # ein Layout sprengt. Wer das Admin-Bild ansieht, liest hier also einen
    # GESTELLTEN Befund, keinen echten. Der Leerzustand braucht kein Bild: er zeigt
    # nichts, und dass `.banner:empty` greift, belegt das leere `#slot-hint` daneben.
    "ohne_anleitung": ["irgendein-neues-spiel"],
    # Gestellt auf „da", sonst fehlt der Knopf „Weltkarte" auf der
    # Minecraft-Kachel in jedem Pruefbild. Live haengt der Wert daran, ob BlueMap
    # wirklich gezeichnet hat.
    "karte_vorhanden": True,
    "games": [
        # Fall 1: lebendige Runde, heute im Spiel. Der heutige Balken ist der
        # rechte und traegt die Heute-Marke.
        _spiel("valheim", state="active", players=3, reserviert=True,
               bedarf_mb=2400, schwelle_mb=3000,
               aktivitaet=_aktiv([0, 0, 180, 40, 0, 0, 320, 95, 0, 0, 0, 210, 60, 145],
                                 zuletzt_s=900)),
        _spiel("terraria", state="active", players=2,
               bedarf_mb=900, schwelle_mb=1400, multi_world=True, world="greenleaf",
               worlds=["greenleaf", "solo", "hardmode-versuch"],
               aktivitaet=_aktiv([0, 55, 0, 0, 0, 130, 240, 0, 0, 0, 0, 0, 90, 70],
                                 zuletzt_s=1800)),
        # Die zweite Thorium-Instanz fehlte hier seit ihrer Einfuehrung und war
        # damit in keinem Pruefbild. Sie gehoert neben die erste: nur nebeneinander
        # sieht man, dass zwei Kacheln mit gleicher Szene und gleichem Mod-Satz
        # trotzdem als verschiedene Welten lesbar bleiben muessen.
        # Fall 2: lange Pause. Ein einzelner Balken am linken Rand und darunter
        # „zuletzt vor 11 Tagen" -- genau die Auskunft, fuer die der Streifen da
        # ist, und die man einer schlafenden Kachel sonst nicht ansieht.
        _spiel("terraria-wildwuchs", state="sleeping",
               bedarf_mb=900, schwelle_mb=1400, world="wildwuchs",
               aktivitaet=_aktiv([85, 40] + [0] * 12, zuletzt_s=11 * 86400)),
        _spiel("dayz", state="starting", startet_seit_s=95,
               bedarf_mb=5700, schwelle_mb=6500,
               aktivitaet=_aktiv([0, 0, 0, 0, 240, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                                 zuletzt_s=9 * 86400)),
        # Zwei Welten mit VERSCHIEDENEN Mods: der Fall, fuer den Zomboid seine
        # Liste je Welt haelt (eine Ini je Welt). Live existiert heute nur eine
        # Welt, deshalb waere er sonst nirgends zu sehen.
        _spiel("zomboid", state="stumm", startet_seit_s=430,
               bedarf_mb=4200, schwelle_mb=4800, multi_world=True, world="greenleaf",
               worlds=["greenleaf", "hardcore"]),
        _spiel("factorio", state="sleeping", startbar=False,
               bedarf_mb=2200, schwelle_mb=8800),
        # Die dritte Terraria-Instanz gehoert ins Bild, seit es sie gibt: sie traegt
        # als einzige einen eigenen Mod-Satz und eine eigene Szene, und beides sieht
        # man nur hier nebeneinander mit den zwei Thorium-Welten.
        _spiel("terraria-calamity", state="sleeping",
               bedarf_mb=900, schwelle_mb=1400, world="calamity"),
        # `fakten` gibt es nur bei Minecraft, und nur dort liest die Kachel sie
        # (app/mcfakten.py, gefuellt von den Helfern auf dem Wirt). Ohne sie im Stub
        # stand die ganze Zusatzzeile in keinem Pruefbild -- also genau die Angaben,
        # die hier zuletzt dazugekommen sind. Gestellt mit Absicht so, dass alle drei
        # Faelle vorkommen: ein Termin NACH VORN (die seit 2026-10-17 bevorzugte
        # Form), ein laufender Bonus und gesicherte Job-Staende.
        _spiel("minecraft", state="sleeping", bedarf_mb=2400, schwelle_mb=3000,
               fakten={
                   "farmwelt": {"reset_zeit": 0, "reset_vor_s": 5 * 86400,
                                "naechster_in_s": 2 * 86400},
                   "bonus": {"faktor": 2, "gezahlt": 1480},
                   "jobs": {"geparkt": 3, "vorgemerkt": 1},
               }),
        _spiel("avorion", state="sleeping", bedarf_mb=300, schwelle_mb=900),
    ],
}

for _g in STATUS["games"]:
    _g["mods"] = _mods(_g["key"], _g.get("world"))
    # Mods je Welt fuer das Welten-Panel, genau wie games.build_view sie liefert.
    _e = _MODS.get(_g["key"]) or {}
    _g["mods_welten"] = _e.get("welten") or {} if _e.get("je_welt") else {}

# Gestellter Verlauf fuer das Panel. Beide Herkuenfte muessen vorkommen, sonst
# zeigt das Bild nur die eine: was ein MENSCH ausgeloest hat (heller, mit Namen)
# und was der BEOBACHTER festgestellt hat (gedaempft, ohne Namen). Der
# Unterschied zwischen beiden ist das einzige, was die Liste gestaltet, und er
# ist nur nebeneinander zu beurteilen. Dazu ein fehlgeschlagener Vorgang, damit
# der Ausgang-Zusatz „(conflict)" im Bild steht und nicht nur im Quelltext.
# ⚠️ Die Zeitstempel sind FEST und altern. Sie tragen keine Aussage, das Panel
# zeigt nur, wie eine Zeile aussieht; ein nachgerechnetes „vor zwei Stunden"
# haette den Prueflauf von der Uhr abhaengig gemacht.
VERLAUF = {"game": "valheim", "eintraege": [
    {"ts": "2026-10-23T16:01:00+00:00", "actor": "arbiter", "action": "spiel.aus",
     "detail": "ausgegangen nach 1 h 59 min, 3 Spieler"},
    {"ts": "2026-10-23T15:40:00+00:00", "actor": "arbiter", "action": "spiel.leer",
     "detail": "niemand mehr drin"},
    {"ts": "2026-10-23T14:21:00+00:00", "actor": "arbiter", "action": "spiel.spieler",
     "detail": "3 im Spiel"},
    {"ts": "2026-10-23T14:09:00+00:00", "actor": "arbiter", "action": "spiel.spieler",
     "detail": "erster Spieler ist drin"},
    {"ts": "2026-10-23T14:02:00+00:00", "actor": "sami", "action": "spiel.wach",
     "detail": "geweckt von sami"},
    {"ts": "2026-10-22T20:14:00+00:00", "actor": "tobi", "action": "snapshot.create",
     "detail": "valheim -> ok"},
    {"ts": "2026-10-22T19:58:00+00:00", "actor": "tobi", "action": "game.start",
     "detail": "valheim -> conflict"},
]}

PUBLIC = {
    "ok": True, "arbiter_ok": True,
    "online_total": STATUS["online_total"],
    "active_game": STATUS["active_game"], "active_label": STATUS["active_label"],
    "games": [{k: g[k] for k in ("key", "label", "emoji", "color", "always_on",
                                 "state", "players", "slots", "world", "mods")}
              for g in STATUS["games"]],
}

# Der Abfang muss VOR app.js laufen und alles beantworten, was die Seite fragt:
# ein durchgereichter Aufruf ins Leere endete sonst im neuen Stillstands-Banner und
# faerbte das Gitter blass, also ausgerechnet den Zustand, den man nicht sehen will.
STUB = """<script>
(function () {
  const ANTWORTEN = {
    "/api/status": %s,
    "/api/public/status": %s,
    "/api/games/valheim/verlauf": %s,
    "/api/games/terraria/snapshots": {"snapshots": [
      {"file": "terraria/greenleaf-20260827-0523.tar.gz", "world": "greenleaf",
       "kind": "nightly", "size": 128000000, "mtime": "2026-08-27 05:23"},
      {"file": "terraria/solo-20260826-1811.tar.gz", "world": "solo",
       "kind": "manual", "size": 12500000, "mtime": "2026-08-26 18:11"}]}
  };
  window.fetch = (pfad) => {
    const p = String(pfad).split("?")[0];
    const d = ANTWORTEN[p];
    return Promise.resolve({ ok: d !== undefined, status: d === undefined ? 404 : 200,
                             json: () => Promise.resolve(d ?? {detail: "Prüfstand: " + p}) });
  };
})();
</script>""" % (json.dumps(STATUS, ensure_ascii=False), json.dumps(PUBLIC, ensure_ascii=False),
            json.dumps(VERLAUF, ensure_ascii=False))


def aufbereiten(roh: str, ziel: str) -> None:
    html = (OUT / roh).read_text(encoding="utf-8")
    html = html.replace('"/static/', '"').replace("'/static/", "'")
    # Der Abfang vor das erste <script src=...>: danach waere app.js schon gelaufen.
    i = html.find("<script src=")
    if i == -1:
        i = html.rfind("</body>")
    html = html[:i] + STUB + html[i:]
    (OUT / ziel).write_text(html, encoding="utf-8")
    print(f"  {ziel}")


aufbereiten("roh-app.html", "app.html")
aufbereiten("roh-landing.html", "landing.html")
aufbereiten("roh-datenschutz.html", "datenschutz.html")
aufbereiten("roh-admin.html", "admin.html")
# Die Guides waren bis 2026-09-06 nicht im Prueflauf, obwohl sie die Seite sind, die
# ein neues Mitglied als erstes braucht, und die einzige, die im Kopf jeder anderen
# verlinkt ist. Sieben Karten mit Anleitung, Adresse und Kopier-Knopf: genau die Art
# Seite, auf der ein Umbruch kippt, ohne dass es jemandem auffaellt.
aufbereiten("roh-guides.html", "guides.html")
aufbereiten("roh-login.html", "login.html")
# Der Verlauf kam 2026-09-12 dazu: Filterzeile (vier Formularfelder nebeneinander)
# plus drei Tabellen mit sechs Spalten. Beides sind Formen, die auf einem 390er
# Handy als erstes kippen und im Quelltext tadellos aussehen.
aufbereiten("roh-verlauf.html", "verlauf.html")
