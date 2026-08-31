#!/usr/bin/env python3
"""Macht die gerenderten Seiten offline-tauglich und stellt der Oberflaeche Antworten.

Die Kacheln entstehen erst im Browser aus /api/status. Ohne gestellte Antwort
fotografiert man ein leeres Gitter mit drei grauen Platzhaltern — also genau das,
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
         "state": "active", "players": 3, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 2400, "schwelle_mb": 3000, "reserviert": True, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "terraria", "label": "Terraria", "emoji": "🌳", "color": "#58c98b",
         "join": "Direct-Connect 192.0.2.10:7777", "slots": 8,
         "state": "active", "players": 2, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 900, "schwelle_mb": 1400, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": True, "world": "greenleaf",
         "worlds": ["greenleaf", "solo", "hardmode-versuch"]},
        {"key": "dayz", "label": "DayZ", "emoji": "🎮", "color": "#97a45e",
         "join": "DZSA-Launcher → „Greenleaf Forest“ ODER 192.0.2.10:2302", "slots": 4,
         "state": "starting", "players": None, "startet_seit_s": 95, "startbar": True,
         "bedarf_mb": 5700, "schwelle_mb": 6500, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "zomboid", "label": "Project Zomboid", "emoji": "🧟", "color": "#d96f5c",
         "join": "Serverliste „Greenleaf“ ODER 192.0.2.10:16261", "slots": 32,
         "state": "stumm", "players": None, "startet_seit_s": 430, "startbar": True,
         "bedarf_mb": 4200, "schwelle_mb": 4800, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "factorio", "label": "Factorio", "emoji": "🏭", "color": "#e0913f",
         "join": "Direct-Connect 192.0.2.10:34197", "slots": 8,
         "state": "sleeping", "players": None, "startet_seit_s": None, "startbar": False,
         "bedarf_mb": 2200, "schwelle_mb": 8800, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "minecraft", "label": "Minecraft", "emoji": "⛏️", "color": "#7cc95e",
         "join": "Server hinzufügen (LAN/Java)", "slots": 20,
         "state": "sleeping", "players": None, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 2400, "schwelle_mb": 3000, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
        {"key": "avorion", "label": "Avorion", "emoji": "🚀", "color": "#9b85e0",
         "join": "Steam-/Avorion-Serverliste „Greenleaf“", "slots": 8,
         "state": "sleeping", "players": None, "startet_seit_s": None, "startbar": True,
         "bedarf_mb": 300, "schwelle_mb": 900, "reserviert": False, "always_on": False,
         "pruefbar": True, "multi_world": False, "world": None, "worlds": []},
    ],
}

PUBLIC = {
    "ok": True, "arbiter_ok": True,
    "online_total": STATUS["online_total"],
    "active_game": STATUS["active_game"], "active_label": STATUS["active_label"],
    "games": [{k: g[k] for k in ("key", "label", "emoji", "color", "always_on",
                                 "state", "players", "slots", "world")}
              for g in STATUS["games"]],
}

# Der Abfang muss VOR app.js laufen und alles beantworten, was die Seite fragt —
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
    # Der Abfang vor das erste <script src=...> — danach waere app.js schon gelaufen.
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
