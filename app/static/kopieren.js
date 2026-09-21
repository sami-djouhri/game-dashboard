"use strict";
// Kopier-Knoepfe, seitenweit: jeder <button class="copy" data-copy="…">.
//
// ★ Am document delegiert, nicht je Knopf gebunden. Die Guides sind statisches HTML,
// die Server-Karten baut app.js alle 5 Sekunden neu auf. Ein Listener je Knopf haette
// dort nach dem ersten Neuaufbau ins Leere gezeigt, und die Alternative waere eine
// zweite Kopie dieser Funktion in app.js gewesen: derselbe Knopf mit derselben
// Beschriftung, aber zwei Stellen, an denen sich sein Verhalten aendern kann.
document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.copy[data-copy]");
  if (!btn) return;
  const zurueck = btn.dataset.label || btn.textContent;
  btn.dataset.label = zurueck;
  try {
    await navigator.clipboard.writeText(btn.dataset.copy);
    btn.textContent = "✓ kopiert";
    btn.classList.add("ok");
  } catch (_) {
    // Die Zwischenablage gibt der Browser nur im sicheren Kontext frei (HTTPS oder
    // localhost). Ueber eine nackte LAN-Adresse scheitert das, und dann ist der
    // Hinweis "von Hand kopieren" die ehrliche Antwort statt eines stillen Nichts.
    btn.textContent = "von Hand kopieren";
  }
  clearTimeout(btn._zurueck);
  btn._zurueck = setTimeout(() => {
    btn.textContent = zurueck;
    btn.classList.remove("ok");
  }, 1800);
});
