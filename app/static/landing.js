"use strict";
// Oeffentlicher Live-Puls (kein Login): Hero-Zeile + Welten-Kacheln werden live.
const STATE = { active: "läuft", sleeping: "bereit", blocked: "belegt",
                starting: "startet …", stumm: "antwortet nicht",
                always_on: "läuft", offline: "keine Antwort",
                unbekannt: "unbekannt" };

// Die Zeile ueber den Knoepfen: wer spielt wo, oder was laeuft leer.
// Aus der Kachelliste, nicht aus `active_label`. Das Feld nennt nur das ERSTE
// laufende Spiel, und bis 2026-11-26 stand hier bei zwei belegten Servern
// "5 Personen spielen gerade · Valheim", obwohl 2 davon auf GreenForest waren.
// Leerer Text heisst: nichts wach, der Aufrufer zeigt dann den Ruhesatz.
const _esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function laufzeile(s) {
  const wach = (s.games || []).filter((g) => g.state === "active" || g.state === "always_on");
  const besetzt = wach.filter((g) => (g.players || 0) > 0)
    .sort((a, b) => (b.players || 0) - (a.players || 0));
  const gesamt = s.online_total || 0;
  if (gesamt > 0) {
    const wo = besetzt.map((g) => _esc(g.label)).join(", ");
    return `<b>${gesamt}</b> ${gesamt === 1 ? "Person spielt" : "Personen spielen"} gerade${wo ? " · " + wo : ""}`;
  }
  if (wach.length) {
    const namen = wach.map((g) => _esc(g.label)).join(", ");
    return `${namen} ${wach.length === 1 ? "läuft" : "laufen"}`;
  }
  return "";
}

async function pulse() {
  let s;
  try { s = await (await fetch("/api/public/status", { headers: { Accept: "application/json" } })).json(); }
  catch (_) {
    // Nicht stumm zurueckkehren. Der Cursor unten sagt aus, dass die Seite den
    // Status liest; blinkt er nach einem Abbruch weiter, behauptet er eine
    // Verbindung, die es nicht gibt, und die Zahlen darueber gelten als aktuell.
    const cur0 = document.getElementById("hero-cursor");
    if (cur0) cur0.classList.add("aus");
    const dot0 = document.getElementById("hero-dot");
    if (dot0) dot0.className = "dot";
    const txt0 = document.getElementById("hero-live-text");
    if (txt0) txt0.textContent = "keine Verbindung zur Leitstelle";
    return;
  }

  const dot = document.getElementById("hero-dot");
  const txt = document.getElementById("hero-live-text");
  const hl = document.getElementById("hero-live");

  // Messwerttafel im Kopf. Die Zahlen sind dieselben, die auch die Kacheln fuellen;
  // sie stehen hier nur noch einmal als Summe, weil das die Frage ist, mit der jemand
  // ankommt: laeuft hier gerade etwas, und ist jemand da?
  const wach = (s.games || []).filter(
    (g) => g.state === "active" || g.state === "always_on").length;
  const setz = (id, wert) => {
    const el = document.getElementById(id);
    if (el) el.textContent = wert;
  };
  setz("k-wach", s.arbiter_ok === false ? "?" : String(wach));
  setz("k-spieler", s.arbiter_ok === false ? "?" : String(s.online_total || 0));

  // Der Cursor blinkt, solange die Seite den Status wirklich liest, und steht
  // still, wenn die Verbindung haengt. Er ist damit keine Zierde, sondern die
  // kleinste ehrliche Betriebsanzeige der Seite: eine Kachelwand, die stehen
  // bleibt, sieht sonst genauso aus wie eine, die gerade aktualisiert wurde.
  const cur = document.getElementById("hero-cursor");
  if (cur) cur.classList.toggle("aus", s.arbiter_ok === false);

  if (hl && txt) {
    // Steuerung nicht erreichbar: die Kachelliste ist dann leer oder unvollstaendig, und
    // "gerade ruhig, jederzeit weckbar" waere ein falsches Versprechen: wecken geht ja
    // gerade nicht. Bewusst ohne Innenzustand: die Seite ist oeffentlich, die genaue
    // Ursache steht im Log und in der Mitgliederansicht.
    if (s.arbiter_ok === false) {
      dot.className = "dot"; hl.classList.remove("on");
      txt.textContent = "Serverstatus gerade nicht abrufbar, ein Beitritt kann fehlschlagen";
    } else if (laufzeile(s)) {
      dot.className = "dot live"; hl.classList.add("on");
      txt.innerHTML = laufzeile(s);
    } else {
      dot.className = "dot"; hl.classList.remove("on");
      txt.textContent = "gerade ruhig, jederzeit weckbar";
    }
  }

  // Welten-Kacheln live markieren (Badge + Rahmen), statt separater Server-Zeile.
  (s.games || []).forEach(g => {
    const card = document.getElementById(`world-${g.key}`);
    if (!card) return;
    card.classList.toggle("active", g.state === "active" || g.state === "always_on");
    const badge = card.querySelector('[data-live="badge"]');
    if (badge) {
      const on = g.state === "active" || g.state === "always_on";
      const count = (typeof g.players === "number" && g.players > 0) ? `${g.players} im Spiel`
                    : (on ? "läuft" : (STATE[g.state] || g.state));
      badge.className = "badge " + g.state;
      badge.textContent = count;
    }
  });
}

// Nicht im Hintergrund weiterfragen: die Landing ist die Seite, die am ehesten in einem
// vergessenen Tab offen bleibt. Beim Zurueckkehren sofort neu messen, damit der Puls
// nie einen alten Stand zeigt.
let takt = null;
function starteTakt() {
  if (takt) clearInterval(takt);
  takt = setInterval(() => { if (!document.hidden) pulse(); }, 15000);
}
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { pulse(); starteTakt(); } });
  pulse();
  starteTakt();
}

if (typeof module !== "undefined") module.exports = { laufzeile };
