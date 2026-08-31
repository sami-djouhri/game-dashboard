// Misst, was auf einem Bild nicht zu zaehlen ist: liegt ein Bedienelement ausserhalb
// des Schirms? Ein Screenshot zeigt die Kante, aber nicht, ob dahinter noch etwas
// steht — und eine Leiste mit verstecktem Scrollbalken sieht abgeschnitten genauso
// aus wie zu Ende. Genau dieser Unterschied war der Befund vom 2026-08-27.
//
// Aufruf aus ansehen.sh; Rueckgabe 1, wenn etwas ausserhalb liegt.
const puppeteer = require("puppeteer-core");

// 320 = kleinste noch verbreitete Geraetebreite; 360/390 die haeufigsten.
const BREITEN = [320, 360, 390, 620, 1440];

(async () => {
  const b = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-browser",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--user-data-dir=/tmp/chrome"],
  });
  const p = await b.newPage();
  let befunde = 0;

  for (const w of BREITEN) {
    await p.setViewport({ width: w, height: 900 });
    await p.goto("file:///work/app.html", { waitUntil: "networkidle0" });
    const r = await p.evaluate(() => {
      const sichtbar = (e) => {
        const s = getComputedStyle(e);
        return s.display !== "none" && s.visibility !== "hidden" && e.getBoundingClientRect().width > 0;
      };
      const nav = document.querySelector(".nav");
      const bedienbar = [...document.querySelectorAll(".nav a, .nav button, .card button, .card select")]
        .filter(sichtbar)
        .map((e) => ({
          t: (e.textContent || e.getAttribute("aria-label") || "?").trim().slice(0, 18),
          r: Math.round(e.getBoundingClientRect().right),
        }));
      return {
        seite: document.documentElement.scrollWidth,
        fenster: document.documentElement.clientWidth,
        navScroll: nav ? nav.scrollWidth : 0,
        navSicht: nav ? nav.clientWidth : 0,
        bedienbar,
      };
    });

    const draussen = r.bedienbar.filter((e) => e.r > r.fenster + 1);
    console.log(`\n--- ${w} px ---`);
    if (r.seite > r.fenster)
      console.log(`  !! Seite scrollt waagerecht (${r.seite} > ${r.fenster})`), befunde++;
    if (r.navScroll > r.navSicht)
      console.log(`  ~  Navigation scrollt in sich (${r.navScroll} > ${r.navSicht})`);
    if (draussen.length) {
      console.log(`  !! ${draussen.length} Bedienelement(e) ausserhalb des Schirms:`);
      draussen.forEach((e) => console.log(`       rechts=${e.r}  „${e.t}“`));
      befunde++;
    } else {
      console.log(`  ok  alle ${r.bedienbar.length} Bedienelemente im Schirm`);
    }
  }

  await b.close();
  process.exit(befunde ? 1 : 0);
})();
