"use strict";
// Guides: Server-Adresse in die Zwischenablage kopieren (kurzes ✓-Feedback).
document.querySelectorAll("button.copy[data-copy]").forEach(btn => {
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(btn.dataset.copy);
      const old = btn.textContent;
      btn.textContent = "✓ kopiert";
      btn.classList.add("ok");
      setTimeout(() => { btn.textContent = old; btn.classList.remove("ok"); }, 1600);
    } catch (_) {
      // Clipboard braucht HTTPS/localhost — im LAN-Preview ggf. nicht verfuegbar.
      btn.textContent = "manuell kopieren";
      setTimeout(() => { btn.textContent = "Kopieren"; }, 2000);
    }
  });
});
