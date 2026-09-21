#!/usr/bin/env python3
"""Macht die gerenderten Seiten offline-tauglich und stellt der Oberflaeche Antworten.

Die Kacheln entstehen erst im Browser aus /api/status. Ohne gestellte Antwort
fotografiert man ein leeres Gitter mit drei grauen Platzhaltern, also genau das,
was man nicht pruefen wollte.

★ Die gestellten Daten zeigen ALLE Kachel-Zustaende auf einem Bild: laufend mit
Spielern, laufend+reserviert, startend, stumm, schlafend, schlafend-mit-zu-wenig-
Speicher, Mehr-Welten. Live bekommt man die nie zusammen zu sehen, und gerade die
seltenen sind die, in denen das Layout bricht.
"""
import json
import pathlib
import sys

OUT = pathlib.Path(sys.argv[1])

# ★ Mod-Listen aus EINER Quelle: dieselbe Datei, die ansehen.sh dem Pruefstand-
# Container als /pruefmods/mods.json einhaengt. Sonst haette der Browser-Stub andere
# Mods gezeigt als die serverseitig gerenderten Guides, und man haette den
# Unterschied fuer einen Fehler in der Anzeige gehalten.
# Ein Schnappschuss vom Wirt (2026-09-06), bewusst nicht erfunden: an erfundenen
# Namen sieht man Umbrueche und Laengen nicht, die es wirklich gibt.
_MODS = json.loads((pathlib.Path(__file__).parent / "pruefdaten-mods.json")
                   .read_text(encoding="utf-8"))["spiele"]


def _mods(key: str, welt: str | None = None) -> dict:
    """Nachbildung von app.mods.fuer(). ★ Muss dieselbe FORM liefern, nicht nur
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

# ── Gestellter Arbiter-Status (Form wie games.build_view + api.status) ──
STATUS = {
    "ok": True, "arbiter_ok": True, "is_admin": True, "may_start": True,
    "node": "gamehost", "mode": "systemd", "gate_up": True,
    "ram_mb": 15200, "frei_mb": 6100, "startend_mb": 5700,
    "holder": None, "holder_label": None,
    "online_total": 5, "active_game": "valheim", "active_label": "Valheim",
    "games": [
        {"key": "valheim", "label": "Valheim", "emoji": "🪓", "color": "#6ea8dc",
         "join": "Serverliste „Greenleaf“ ODER 192.0.2.10:2456", "slots": 10,
         "address": "192.0.2.10:2456",
         "state": "active", "players": 3, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 2400, "schwelle_mb": 3000, "reserviert": True, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "terraria", "label": "Terraria", "emoji": "🌳", "color": "#58c98b",
         "join": "Direct-Connect 192.0.2.10:7777", "slots": 8,
         "address": "192.0.2.10:7777",
         "state": "active", "players": 2, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 900, "schwelle_mb": 1400, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": True, "world": "greenleaf",
         "worlds": ["greenleaf", "solo", "hardmode-versuch"]},
        {"key": "dayz", "label": "DayZ", "emoji": "🎮", "color": "#97a45e",
         "join": "DZSA-Launcher → „Greenleaf Forest“ ODER 192.0.2.10:2302", "slots": 4,
         "address": "192.0.2.10:2302",
         "state": "starting", "players": None, "startet_seit_s": 95, "startbar": True,
         "bedarf_mb": 5700, "schwelle_mb": 6500, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "zomboid", "label": "Project Zomboid", "emoji": "🧟", "color": "#d96f5c",
         "join": "Serverliste „Greenleaf“ ODER 192.0.2.10:16261", "slots": 32,
         "address": "192.0.2.10:16261",
         "state": "stumm", "players": None, "startet_seit_s": 430, "startbar": True,
         "bedarf_mb": 4200, "schwelle_mb": 4800, "reserviert": False, "always_on": False,
         # ★ Zwei Welten mit VERSCHIEDENEN Mods: der Fall, fuer den Zomboid seine
         # Liste je Welt haelt (eine Ini je Welt). Live existiert heute nur eine
         # Welt, deshalb waere er sonst nirgends zu sehen.
         "pruefbar": True, "multi_world": True, "world": "greenleaf",
         "worlds": ["greenleaf", "hardcore"]},
        {"key": "factorio", "label": "Factorio", "emoji": "🏭", "color": "#e0913f",
         "join": "Direct-Connect 192.0.2.10:34197", "slots": 8,
         "address": "192.0.2.10:34197",
         "state": "sleeping", "players": None, "startet_seit_s": None, "startbar": False,
         "bedarf_mb": 2200, "schwelle_mb": 8800, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "minecraft", "label": "Minecraft", "emoji": "⛏️", "color": "#7cc95e",
         "join": "Server hinzufügen (LAN/Java)", "slots": 20,
         "address": "",
         "state": "sleeping", "players": None, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 2400, "schwelle_mb": 3000, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "avorion", "label": "Avorion", "emoji": "🚀", "color": "#9b85e0",
         "join": "Steam-/Avorion-Serverliste „Greenleaf“", "slots": 8,
         "address": "",
         "state": "sleeping", "players": None, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 300, "schwelle_mb": 900, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
    ],
}

for _g in STATUS["games"]:
    _g["mods"] = _mods(_g["key"], _g.get("world"))
    # Mods je Welt fuer das Welten-Panel, genau wie games.build_view sie liefert.
    _e = _MODS.get(_g["key"]) or {}
    _g["mods_welten"] = _e.get("welten") or {} if _e.get("je_welt") else {}

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
</script>""" % (json.dumps(STATUS, ensure_ascii=False), json.dumps(PUBLIC, ensure_ascii=False))


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
# ★ Die Guides waren bis 2026-09-06 nicht im Prueflauf, obwohl sie die Seite sind, die
# ein neues Mitglied als erstes braucht, und die einzige, die im Kopf jeder anderen
# verlinkt ist. Sieben Karten mit Anleitung, Adresse und Kopier-Knopf: genau die Art
# Seite, auf der ein Umbruch kippt, ohne dass es jemandem auffaellt.
aufbereiten("roh-guides.html", "guides.html")
aufbereiten("roh-login.html", "login.html")
# Der Verlauf kam 2026-09-12 dazu: Filterzeile (vier Formularfelder nebeneinander)
# plus drei Tabellen mit sechs Spalten. Beides sind Formen, die auf einem 390er
# Handy als erstes kippen und im Quelltext tadellos aussehen.
aufbereiten("roh-verlauf.html", "verlauf.html")
