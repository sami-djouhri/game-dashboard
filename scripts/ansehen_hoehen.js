// Misst, wie hoch jede Seite bei der jeweiligen Breite WIRKLICH ist.
//
// WARUM ES DIESE DATEI GIBT (2026-10-17):
// Die Bildhoehen standen in ansehen.sh als feste Zahlen ("guides.html 1440 1700").
// Chromium schneidet alles darunter ab, und ein abgeschnittenes Bild sieht aus wie
// ein vollstaendiges: nichts fehlt sichtbar, es hoert nur auf. Als die Guides-Karte
// von Minecraft um den Abschnitt "Was dich erwartet" wuchs, lag genau dieser neue
// Abschnitt unterhalb der Kante -- im Prueflauf, dessen einziger Zweck es ist, das
// zu zeigen. Dieselbe Klasse wie die abgeschriebene Dateiliste weiter oben in
// ansehen.sh: eine Zahl, die einmal gestimmt hat.
//
// Ausgabe: je Zeile "<name> <hoehe>", von ansehen.sh gelesen. Die Hoehe im Skript
// bleibt als MINDESTwert stehen (ein Bild soll nicht winzig werden, wenn eine Seite
// mal kurz ist), gewinnt aber nie gegen die gemessene.
const puppeteer = require("puppeteer");

// datei : breite : mindesthoehe -- dieselbe Liste wie die schuss()-Aufrufe.
const SEITEN = [
  ["app.html", 1440, 1500, "app-desktop"],
  ["app.html", 390, 1800, "app-handy"],
  ["landing.html", 1440, 1500, "landing-desktop"],
  ["landing.html", 390, 1800, "landing-handy"],
  ["login.html", 1000, 900, "login"],
  ["guides.html", 1440, 1700, "guides-desktop"],
  ["guides.html", 390, 1900, "guides-handy"],
  ["datenschutz.html", 1000, 1750, "datenschutz"],
  ["admin.html", 1440, 2100, "admin-desktop"],
  ["admin.html", 390, 2000, "admin-handy"],
  ["verlauf.html", 1440, 2000, "verlauf-desktop"],
  ["verlauf.html", 390, 2200, "verlauf-handy"],
];

(async () => {
  const browser = await puppeteer.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  for (const [datei, breite, mindest, name] of SEITEN) {
    const page = await browser.newPage();
    await page.setViewport({ width: breite, height: mindest });
    try {
      await page.goto("file:///work/" + datei, { waitUntil: "networkidle0", timeout: 20000 });
      // Die Kacheln entstehen erst im Browser; ohne diese Pause misst man das leere Gitter.
      await new Promise((r) => setTimeout(r, 1200));
      const hoch = await page.evaluate(() => Math.ceil(Math.max(
        document.body.scrollHeight, document.documentElement.scrollHeight,
      )));
      // +40 px Rand: eine Seite, die auf den Pixel genau endet, schneidet ihren
      // letzten Rahmen an, und das sieht nach einem Darstellungsfehler aus.
      console.log(`${name} ${Math.max(mindest, hoch + 40)}`);
    } catch (e) {
      // Unmessbar heisst Mindesthoehe, nicht Abbruch: ein Bild ist besser als keines,
      // und der Grund steht auf stderr statt still im Nichts.
      console.error(`  !! Hoehe von ${name} nicht messbar: ${e.message}`);
      console.log(`${name} ${mindest}`);
    }
    await page.close();
  }
  await browser.close();
})();
