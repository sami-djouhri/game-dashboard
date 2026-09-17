// Fotografiert die AUFGEKLAPPTEN Zustaende der Karte.
//
// ★ WARUM EIGENS: die drei Panels der Server-Karte (Anleitung, Welten, Sicherungen)
// entstehen erst durch einen Klick. Ein Screenshot der Seite zeigt sie nie, und
// damit war ausgerechnet der Teil ungeprueft, in dem die folgenreichsten Knoepfe
// sitzen: Welt loeschen und Sicherung zurueckspielen. Bis 2026-09-06 hat sie
// niemand im Bild gesehen.
//
// Aufruf aus ansehen.sh, schreibt panels.png nach /work.
const puppeteer = require("puppeteer-core");

(async () => {
  const b = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-browser",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--user-data-dir=/tmp/chrome"],
  });
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 1700 });
  await p.goto("file:///work/app.html", { waitUntil: "networkidle0" });

  // Drei Panels auf einmal: sie haben je einen eigenen Zustand im Skript und
  // schliessen einander nicht. Anleitung bei Valheim, die beiden Admin-Panels bei
  // Terraria, weil nur Terraria mehrere Welten hat.
  // ★ Die Anleitung bei DayZ, nicht bei Valheim: Valheim laeuft unmodifiziert, und
  // dann fehlt im Panel genau der Block, den man sehen will. Ein Prueflauf soll den
  // gefuellten Fall zeigen, nicht den leeren.
  const klicks = [
    ['.card[data-game="dayz"] button[data-act="anleitung"]', "Anleitung"],
    ['.card[data-game="zomboid"] button[data-act="worlds"]', "Welten (je Welt eigene Mods)"],
    ['.card[data-game="terraria"] button[data-act="snapshots"]', "Sicherungen"],
  ];
  for (const [sel, name] of klicks) {
    const el = await p.$(sel);
    if (!el) { console.log(`  !! ${name}: Knopf nicht gefunden (${sel})`); continue; }
    await el.click();
    console.log(`  ok  ${name} aufgeklappt`);
  }
  // Die Sicherungen kommen ueber fetch; dem Stub eine Runde Zeit lassen.
  await new Promise((r) => setTimeout(r, 600));

  // Gegenprobe, dass wirklich etwas sichtbar ist. Ein Bild von drei zugeklappten
  // Panels saehe aus wie ein normales Gitter und wuerde nichts verraten.
  const offen = await p.evaluate(() =>
    [...document.querySelectorAll(".snap-panel")].filter((e) => !e.hidden).length);
  console.log(offen >= 3 ? `  ok  ${offen} Panels offen`
                         : `  !! nur ${offen} Panel(s) offen, erwartet 3`);

  await p.screenshot({ path: "/work/panels.png" });
  console.log("  panels.png");
  await b.close();
  process.exit(offen >= 3 ? 0 : 1);
})();
