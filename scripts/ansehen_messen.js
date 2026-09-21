// Misst, was auf einem Bild nicht zu zaehlen ist: liegt ein Bedienelement ausserhalb
// des Schirms? Ein Screenshot zeigt die Kante, aber nicht, ob dahinter noch etwas
// steht, und eine Leiste mit verstecktem Scrollbalken sieht abgeschnitten genauso
// aus wie zu Ende. Genau dieser Unterschied war der Befund vom 2026-08-27.
//
// Aufruf aus ansehen.sh; Rueckgabe 1, wenn etwas ausserhalb liegt.
const puppeteer = require("puppeteer-core");

// 320 = kleinste noch verbreitete Geraetebreite; 360/390 die haeufigsten.
const BREITEN = [320, 360, 390, 620, 1440];
// ★ Gemessen wurde bis 2026-09-06 nur das Server-Gitter. Die Guides tragen aber die
// laengsten unteilbaren Zeichenketten der ganzen Seite (Server-Adressen, Mod-Namen),
// und ein zu breites Wort sprengt eine Karte, ohne dass die Kachelwand daneben etwas
// davon merkt. Die Landing ist dazugekommen, weil dort die einzigen Knoepfe stehen,
// die ein Nicht-Mitglied ueberhaupt sieht.
const SEITEN = ["app.html", "guides.html", "landing.html"];

(async () => {
  const b = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-browser",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--user-data-dir=/tmp/chrome"],
  });
  const p = await b.newPage();
  let befunde = 0;

  for (const seite of SEITEN) {
    console.log(`\n======== ${seite} ========`);
    for (const w of BREITEN) {
      await p.setViewport({ width: w, height: 900 });
      await p.goto(`file:///work/${seite}`, { waitUntil: "networkidle0" });
      const r = await p.evaluate(() => {
        const sichtbar = (e) => {
          const s = getComputedStyle(e);
          return s.display !== "none" && s.visibility !== "hidden" && e.getBoundingClientRect().width > 0;
        };
        const nav = document.querySelector(".nav");
        const bedienbar = [...document.querySelectorAll(
          ".nav a, .nav button, .card button, .card select, .guide button, .guide a.btn, .hero .cta a")]
          .filter(sichtbar)
          .map((e) => ({
            t: (e.textContent || e.getAttribute("aria-label") || "?").trim().slice(0, 18),
            r: Math.round(e.getBoundingClientRect().right),
          }));
        // ★ Wer ist zu breit? Ohne diese Liste meldet die Messung nur DASS die Seite
        // waagerecht laeuft, und man sucht die Ursache danach von Hand durch das CSS.
        // Gezaehlt wird jedes Element, dessen rechte Kante ueber das Fenster
        // hinausragt und dessen Eltern-Element das nicht schon tut: so steht der
        // Verursacher oben statt seiner ganzen Ahnenreihe.
        const w = document.documentElement.clientWidth;
        // Eine Leiste, die absichtlich in sich scrollt (Sprung-Chips), schiebt ihre
        // Kinder ueber den Rand, ohne dass die Seite darunter leidet. Wer das nicht
        // ausnimmt, meldet vier Chips als Verursacher und den echten daneben.
        const imScroller = (e) => {
          for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
            if (getComputedStyle(p).overflowX !== "visible") return true;
          }
          return false;
        };
        const zuBreit = [...document.querySelectorAll("body *")]
          .filter((e) => {
            const r = e.getBoundingClientRect();
            if (r.width === 0 || r.right <= w + 1) return false;
            if (imScroller(e)) return false;
            const p = e.parentElement;
            return !p || p.getBoundingClientRect().right <= w + 1;
          })
          .slice(0, 6)
          .map((e) => ({
            tag: e.tagName.toLowerCase() + (e.className && typeof e.className === "string"
              ? "." + e.className.trim().split(/\s+/).join(".") : ""),
            r: Math.round(e.getBoundingClientRect().right),
            t: (e.textContent || "").trim().slice(0, 24),
          }));

        return {
          seite: document.documentElement.scrollWidth,
          fenster: w,
          navScroll: nav ? nav.scrollWidth : 0,
          navSicht: nav ? nav.clientWidth : 0,
          bedienbar, zuBreit,
        };
      });

      const draussen = r.bedienbar.filter((e) => e.r > r.fenster + 1);
      console.log(`\n--- ${w} px ---`);
      if (r.seite > r.fenster) {
        console.log(`  !! Seite scrollt waagerecht (${r.seite} > ${r.fenster})`);
        r.zuBreit.forEach((e) => console.log(`       rechts=${e.r}  ${e.tag}  „${e.t}“`));
        befunde++;
      }
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
  }


  // ── Kontrast ──────────────────────────────────────────────────────────
  // ★ Farben, die auf dem eigenen Schirm „gut lesbar" aussehen, sind der haeufigste
  // blinde Fleck einer dunklen Oberflaeche: der Entwickler sitzt im abgedunkelten
  // Raum, der Spieler nicht. Gemessen wird nach WCAG (4,5:1 fuer normalen Text,
  // 3:1 ab 24 px oder ab 18,7 px fett). Der Hintergrund wird durch Aufsteigen der
  // Ahnenreihe zusammengemischt, weil halbdurchsichtige Flaechen sonst als
  // schwarz durchgehen und jeden Wert schoenrechnen.
  console.log("\n======== Kontrast (1440 px) ========");
  await p.setViewport({ width: 1440, height: 1200 });
  let kBefunde = 0;
  for (const seite of SEITEN) {
    await p.goto(`file:///work/${seite}`, { waitUntil: "networkidle0" });
    const treffer = await p.evaluate(() => {
      const zahl = (c) => (c || "").match(/[\d.]+/g)?.map(Number) || [0, 0, 0, 0];
      const lum = ([r, g, b]) => {
        const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
        return .2126 * f(r) + .7152 * f(g) + .0722 * f(b);
      };
      const ueber = (v, h) => {   // Vordergrund mit Alpha ueber Hintergrund
        const a = v[3] === undefined ? 1 : v[3];
        return [0, 1, 2].map((i) => v[i] * a + h[i] * (1 - a));
      };
      const grund = (el) => {
        const schichten = [];
        for (let e = el; e; e = e.parentElement) {
          const bg = zahl(getComputedStyle(e).backgroundColor);
          if ((bg[3] === undefined ? 1 : bg[3]) > 0) schichten.push(bg);
          if ((bg[3] === undefined ? 1 : bg[3]) >= 1) break;
        }
        let farbe = [0, 0, 0];
        for (const s of schichten.reverse()) farbe = ueber(s, farbe);
        return farbe;
      };
      const out = [];
      document.querySelectorAll("body *").forEach((el) => {
        const txt = [...el.childNodes]
          .filter((n) => n.nodeType === 3 && n.textContent.trim())
          .map((n) => n.textContent.trim()).join(" ");
        if (!txt) return;
        const st = getComputedStyle(el);
        if (st.visibility === "hidden" || st.display === "none" || +st.opacity === 0) return;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        const px = parseFloat(st.fontSize);
        const fett = +st.fontWeight >= 700;
        const gross = px >= 24 || (px >= 18.66 && fett);
        const hg = grund(el);
        const vg = ueber(zahl(st.color), hg);
        const l1 = lum(vg), l2 = lum(hg);
        const k = (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
        const soll = gross ? 3 : 4.5;
        if (k < soll) out.push({ k: k.toFixed(2), soll, px: px.toFixed(1),
          t: txt.slice(0, 30), sel: el.tagName.toLowerCase() +
            (typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/)[0] : "") });
      });
      // Gleiche Stelle nur einmal melden: eine Tabelle mit 40 Zeilen erzeugt sonst
      // 40 identische Zeilen und begraebt die anderen Befunde.
      const gesehen = new Set();
      return out.filter((o) => { const s = o.sel + o.k; if (gesehen.has(s)) return false; gesehen.add(s); return true; });
    });
    if (treffer.length) {
      console.log(`\n--- ${seite} ---`);
      treffer.forEach((t) => {
        console.log(`  !! ${t.k}:1 (soll ${t.soll}) ${t.px}px  ${t.sel}  „${t.t}“`);
        kBefunde++;
      });
    }
  }
  console.log(kBefunde ? `\n  ${kBefunde} Kontrast-Befund(e)` : "\n  ok  Kontrast ueberall ausreichend");
  befunde += kBefunde;

  await b.close();
  process.exit(befunde ? 1 : 0);
})();
