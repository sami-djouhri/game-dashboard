"use strict";
// Bescheid, sobald ein selbst gestarteter Server joinbar ist (2026-11-15).
//
// Ein Start dauert 1-3 Minuten. Bisher hiess das: Seite offen lassen und hinsehen,
// denn tick() fragt in einem Hintergrund-Tab bewusst nicht nach (sonst rund um die
// Uhr Statusabfragen je Tab). Solange hier ein Spiel wartet, fragt app.js auch im
// Hintergrund, und diese Funktion entscheidet nach jeder Abfrage, ob es etwas zu
// melden gibt.
//
// Reine Funktion ohne DOM, damit tests/test_bescheid.py sie unter node pruefen kann.
//
//   wartet  Map  key -> { seit: ms, gesehen: bool }
//           `gesehen` heisst: seit dem Klick einmal NICHT "active" gesehen. Bei einem
//           Neustart oder Weltwechsel steht der Server im ersten Status oft noch als
//           "active" da, das waere der alte Lauf und keine Bereitschaft. Beim Start
//           aus dem Schlaf ist es von Anfang an true (der Knopf gibt es nur dort).
//   games   die Spiele aus /api/status (roh, nicht die von card() umgedeuteten)
//   jetzt   Date.now()
//   maxMs   ab dann wird nicht mehr gewartet
//
// Liefert die Meldungen [{ key, name, bereit }] und nimmt gemeldete Spiele aus `wartet`.
function bescheidAuswerten(wartet, games, jetzt, maxMs) {
  const meldungen = [];
  for (const [key, w] of wartet) {
    const g = (games || []).find(x => x.key === key);
    const name = (g && g.label) || key;
    const state = g ? g.state : "";
    if (state !== "active") w.gesehen = true;
    if (state === "active" && w.gesehen) {
      wartet.delete(key);
      meldungen.push({ key, name, bereit: true });
    } else if (state === "stumm" || jetzt - w.seit > maxMs) {
      wartet.delete(key);
      // Nach Ablauf zaehlt, was jetzt ist: laeuft er, war er bereit, nur der
      // Neustart-Wechsel lag zwischen zwei Abfragen und wurde nie gesehen.
      meldungen.push({ key, name, bereit: state === "active" });
    }
  }
  return meldungen;
}

if (typeof module !== "undefined") module.exports = { bescheidAuswerten };
