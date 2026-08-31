"use strict";
// Oeffentlicher Live-Puls (kein Login): Hero-Zeile + Welten-Kacheln werden live.
const STATE = { active: "läuft", sleeping: "bereit", blocked: "belegt",
                starting: "startet …", stumm: "antwortet nicht",
                always_on: "läuft", offline: "keine Antwort",
                unbekannt: "unbekannt" };

async function pulse() {
  let s;
  try { s = await (await fetch("/api/public/status", { headers: { Accept: "application/json" } })).json(); }
  catch (_) { return; }

  const dot = document.getElementById("hero-dot");
  const txt = document.getElementById("hero-live-text");
  const hl = document.getElementById("hero-live");
  if (hl && txt) {
    // Steuerung nicht erreichbar: die Kachelliste ist dann leer oder unvollstaendig, und
    // "gerade ruhig, jederzeit weckbar" waere ein falsches Versprechen — wecken geht ja
    // gerade nicht. Bewusst ohne Innenzustand: die Seite ist oeffentlich, die genaue
    // Ursache steht im Log und in der Mitgliederansicht.
    if (s.arbiter_ok === false) {
      dot.className = "dot"; hl.classList.remove("on");
      txt.textContent = "Serverstatus gerade nicht abrufbar, ein Beitritt kann fehlschlagen";
    } else if (s.online_total > 0) {
      dot.className = "dot live"; hl.classList.add("on");
      txt.innerHTML = `<b>${s.online_total}</b> ${s.online_total === 1 ? "Person spielt" : "Personen spielen"} gerade${s.active_label ? " · " + s.active_label : ""}`;
    } else if (s.active_label) {
      dot.className = "dot live"; hl.classList.add("on");
      txt.innerHTML = `${s.active_label} läuft`;
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
document.addEventListener("visibilitychange", () => { if (!document.hidden) { pulse(); starteTakt(); } });
pulse();
starteTakt();
