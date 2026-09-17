"use strict";
// Lagezeile der Admin-Seite: der eine Blick auf die Maschinen, den man beim
// Verwalten von Menschen braucht. Gesteuert wird auf /app.
//
// ★ Bewusst ein eigenes, winziges Skript statt app.js. Diese Seite hat kein
// Kachelgitter mehr; app.js haengt seine Listener fest an #grid und waere hier
// ueber ein null gestolpert, bevor irgendetwas gerendert ist.
//
// ★ Und bewusst ein langsamerer Takt als die 5 Sekunden des Gitters: eine
// Uebersichtszeile muss nicht sekundengenau sein, jede Abfrage laeuft aber durch
// Bridge und Arbiter bis auf den Spiele-Wirt. Wer hier Bewerbungen durchsieht,
// braucht keinen Live-Ticker.
const TAKT_MS = 20000;

const setz = (id, wert) => {
  const el = document.getElementById(id);
  if (el) el.textContent = wert;
};
const fmtGB = (mb) => (mb / 1024).toFixed(1).replace(".", ",") + " GB";

async function lage() {
  let s;
  try {
    const r = await fetch("/api/status", { headers: { Accept: "application/json" } });
    if (r.status === 401) { location.href = "/login"; return; }
    if (!r.ok) throw new Error(r.status);
    s = await r.json();
  } catch (_) {
    // Nicht stumm zurueckkehren: eine Zeile mit Strichen sagt „noch nicht gelesen",
    // eine mit alten Zahlen wuerde einen Stand behaupten, den niemand gemessen hat.
    ["lz-wach", "lz-gesamt", "lz-spieler", "lz-ram"].forEach((id) => setz(id, "?"));
    const hint = document.getElementById("slot-hint");
    if (hint) hint.textContent = "Die Seite erreicht die Steuerung gerade nicht. Es wird weiter versucht.";
    return;
  }

  const spiele = s.games || [];
  const wach = spiele.filter((g) => g.state === "active" || g.state === "always_on").length;
  const spieler = spiele.reduce((n, g) => n + (typeof g.players === "number" ? g.players : 0), 0);
  setz("lz-gesamt", String(spiele.length));
  setz("lz-wach", s.arbiter_ok === false ? "?" : String(wach));
  setz("lz-spieler", s.arbiter_ok === false ? "?" : String(spieler));
  // Derselbe wirksame Wert wie auf der Server-Seite: frei_mb beruecksichtigt den
  // Speicher, den ein gerade startendes Spiel schon zugesagt bekommen hat.
  const frei = s.frei_mb == null ? s.ram_mb : s.frei_mb;
  setz("lz-ram", frei == null ? "?" : fmtGB(frei));

  const hint = document.getElementById("slot-hint");
  if (hint) {
    hint.textContent = s.arbiter_ok === false
      ? "Steuerung nicht erreichbar, die Zustände sind ungeprüft."
      : (s.holder ? `${s.holder_label} ist im Wartungsmodus reserviert und hat Vorrang.` : "");
  }
}

// Kein Poll, solange niemand hinsieht; beim Zurueckkehren sofort neu lesen.
document.addEventListener("visibilitychange", () => { if (!document.hidden) lage(); });
lage();
setInterval(() => { if (!document.hidden) lage(); }, TAKT_MS);
