"use strict";
// Member-Dashboard: Live-Grid + Steuerung. Rollen kommen aus /api/status
// (is_admin/may_start); CSRF-Token aus dem <meta>-Tag.
const POLL_MS = 5000;
// Laufende Vorgaenge, EINER JE SPIEL. Frueher war das ein einziges globales Flag: waehrend
// Valheim startete, waren die Knoepfe aller sieben Kacheln tot. Das passte zu der Zeit, als
// nur ein Server gleichzeitig laufen durfte — seit dem Mehr-Spiel-Umbau des Arbiters ist es
// eine Sperre, die es in der Sache nicht mehr gibt.
const busy = new Set();
let ROLE = { is_admin: false, may_start: false };

const $ = (id) => document.getElementById(id);
const CSRF = (document.querySelector('meta[name="csrf"]') || {}).content || "";
// always_on/offline: Server ausserhalb der Arbiter-Registry — nicht weckbar, eigene Labels.
// "unbekannt" trifft eine Rolle, ueber die der Arbiter gerade nichts sagt (Bridge weg).
// Das ist etwas anderes als "schlaeft" — behaupten wuerde man sonst Ruhe, die keiner mass.
// "starting"/"stumm" trennen "Startbefehl abgesetzt, antwortet noch nicht" von "antwortet
// seit Minuten nicht mehr" — beides sah frueher wie "laeuft" aus.
const STATE_LABEL = { active: "läuft", sleeping: "schläft", blocked: "belegt",
                      starting: "startet …", stumm: "antwortet nicht",
                      always_on: "dauerhaft an", offline: "keine Antwort",
                      unbekannt: "Zustand unbekannt" };

async function api(path, method = "GET", body = null) {
  const opt = { method, headers: { Accept: "application/json" } };
  if (method !== "GET") opt.headers["X-CSRF-Token"] = CSRF;
  if (body) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  if (!r.ok) {
    let detail = r.status;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    // ★ Der Statuscode gehoert AN den Fehler, nicht in seinen Text. Der Text ist die
    // Klartext-Begruendung des Servers ("Nicht angemeldet") und wechselt mit der
    // Formulierung; nur bei einer Antwort OHNE JSON-Koerper blieb hier zufaellig die
    // Zahl stehen. Die Abmelde-Erkennung unten verglich genau diesen Text mit "401"
    // und hat deshalb nie gegriffen: eine abgelaufene Sitzung fuehrte nicht zur
    // Anmeldung, die Kachelwand stand einfach still weiter.
    const err = new Error(detail);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

// 401 heisst: die Sitzung ist weg (abgelaufen, abgemeldet, vom Admin gesperrt).
// Weitermachen hat dann keinen Zweck — jeder Klick faende dieselbe tote Sitzung.
function abgemeldet(e) {
  if (e && e.status === 401) { location.href = "/login"; return true; }
  return false;
}

// Einheitliche Fehlerausgabe: erst die Sitzung pruefen, dann melden.
function fehler(e, praefix = "Fehler", ms = 8000) {
  if (abgemeldet(e)) return;
  toast(`${praefix}: ${e.message}`, "err", ms);
}

const capWorld = (w) => w ? w.charAt(0).toUpperCase() + w.slice(1) : "";
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtSize(b) {
  if (b == null) return "";
  if (b < 1024 * 1024) return (b / 1024).toFixed(0) + " KB";
  if (b < 1024 * 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + " MB";
  return (b / 1024 / 1024 / 1024).toFixed(2) + " GB";
}

function sceneFor(key) {
  const tpl = $("scene-" + key) || $("scene-fallback");
  return tpl ? `<div class="scene-wrap">${tpl.innerHTML}</div>` : "";
}

// ── Dialog statt prompt()/confirm() ──────────────────────────────────
// Die Browser-Fenster waren auf dem Handy kaum lesbar, nicht gestaltbar und lassen sich
// in manchen Browsern dauerhaft unterdruecken — dann verschwindet ohne Rueckmeldung auch
// die Sicherheitsabfrage vor dem Zurueckspielen. Ein <dialog> ist Teil der Seite:
// Escape schliesst, Enter bestaetigt, der Fokus bleibt gefangen.
//
// Rueckgabe: mit `expect` oder ohne Eingabefeld -> true/false. Mit `pattern` -> der
// eingegebene Wert oder null bei Abbruch.
function ask({ title, text, placeholder = "", pattern = null, patternHint = "",
               expect = null, ok = "OK", danger = false }) {
  return new Promise((resolve) => {
    const braucht = pattern || expect;
    const dlg = document.createElement("dialog");
    dlg.className = "ask" + (danger ? " danger" : "");
    dlg.innerHTML = `
      <form method="dialog">
        <h3>${esc(title)}</h3>
        ${text ? `<p>${esc(text)}</p>` : ""}
        ${braucht ? `<input type="text" autocomplete="off" spellcheck="false"
                       placeholder="${esc(placeholder)}" aria-label="${esc(title)}">` : ""}
        <p class="ask-err" hidden></p>
        <div class="ask-btns">
          <button value="abbruch" class="ghost">Abbrechen</button>
          <button value="ok" class="${danger ? "danger" : "primary"}">${esc(ok)}</button>
        </div>
      </form>`;
    document.body.appendChild(dlg);
    const inp = dlg.querySelector("input");
    const err = dlg.querySelector(".ask-err");
    const fertig = (wert) => { dlg.close(); dlg.remove(); resolve(wert); };

    dlg.querySelector("form").addEventListener("submit", (ev) => {
      if (ev.submitter && ev.submitter.value !== "ok") { ev.preventDefault(); fertig(null); return; }
      if (!braucht) { ev.preventDefault(); fertig(true); return; }
      const v = (inp.value || "").trim();
      if (expect) {
        // Gross-/Kleinschreibung egal: die Abfrage soll Versehen abfangen, nicht Tippgenauigkeit pruefen.
        if (v.toLowerCase() !== String(expect).toLowerCase()) {
          ev.preventDefault();
          err.textContent = `Bitte „${expect}“ genau so eintippen.`; err.hidden = false;
          return;
        }
        ev.preventDefault(); fertig(true); return;
      }
      if (pattern && !pattern.test(v.toLowerCase())) {
        ev.preventDefault();
        err.textContent = patternHint || "Ungültige Eingabe."; err.hidden = false;
        return;
      }
      ev.preventDefault(); fertig(v.toLowerCase());
    });
    // Escape / Klick auf den Hintergrund = Abbruch, nie ein stilles "ja".
    dlg.addEventListener("cancel", (ev) => { ev.preventDefault(); fertig(null); });
    dlg.addEventListener("click", (ev) => { if (ev.target === dlg) fertig(null); });
    dlg.showModal();
    if (inp) inp.focus();
  });
}

function toast(msg, kind = "ok", ms = 6000) {
  let t = $("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.className = "toast" + (kind === "err" ? " err" : kind === "warn" ? " warn" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

// Zeigt den Speicher, gegen den die Kacheln tatsaechlich rechnen. Solange nichts
// startet, sind roh und wirksam derselbe Wert und es steht nur eine Zahl da. Startet
// gerade etwas, hat es seinen Speicher noch nicht belegt, bekommt ihn aber sicher —
// dann nennt die Zeile den wirksamen Wert und sagt dazu, wo der Rest hin ist. Vorher
// stand hier der Rohwert, waehrend die Kachel daneben "braucht 2,4 GB frei, so viel
// ist es gerade nicht" schrieb: ein Widerspruch, den man der Seite anlastet.
// Deutsches Dezimaltrennzeichen — die einzige Stelle, an der Groessen formatiert werden.
const fmtGB = (mb) => (mb / 1024).toFixed(1).replace(".", ",") + " GB";

// ★ Dieselbe Zahlenschreibweise wie die Kacheln. Bis 2026-08-27 rechnete diese Zeile mit
// toFixed(1) und schrieb „6.0 GB", waehrend die Kachel darunter „8,6 GB frei" verlangte —
// Punkt und Komma fuer dieselbe Groesse auf einem Bild. Und die Ueberschrift sprach von
// „RAM" und „Node", wo der Satz am Fuss derselben Seite „Arbeitsspeicher" sagt: das hier
// ist eine Clan-Seite fuer Spieler, nicht die Ops-Ansicht.
function ramBar(mb, freiMb, startendMb) {
  if (mb == null) return "";
  const wirksam = (freiMb == null) ? mb : freiMb;
  const kopf = `Arbeitsspeicher frei: <b style="color:var(--leaf)">${fmtGB(wirksam)}</b>`;
  if (!startendMb || freiMb == null) return kopf;
  return kopf + ` <span class="hint">(${fmtGB(mb)} im Server, `
              + `${fmtGB(startendMb)} für startende Spiele vorgemerkt)</span>`;
}

// Snapshot-Panel: welcher Kachel-Ausklapper ist offen + gecachte Liste,
// damit der 5s-Grid-Rebuild den offenen Zustand nicht zerstoert.
let snapOpen = null;
const snapCache = {};
const gameInfo = {};

// "vor 2 min" statt einer nackten Sekundenzahl — waehrend eines Startvorgangs will man
// wissen, wie lange es schon dauert, nicht wie viele Sekunden vergangen sind.
function fmtDauer(s) {
  if (s == null) return "";
  if (s < 90) return `${Math.round(s)} s`;
  return `${Math.round(s / 60)} min`;
}

function card(g) {
  // Ueberbrueckung der Tick-Luecke: Solange der Arbiter den eigenen Startbefehl noch nicht
  // im Status hat, gilt unser Wissen. Sobald er das Spiel als laufend fuehrt, faellt der
  // Vermerk weg — und nach ANLAUF_MS ebenfalls, damit ein fehlgeschlagener Start nicht
  // ewig als "startet …" stehen bleibt und die Kachel wieder ehrlich "schläft" sagt.
  const seitKlick = frischGestartet.get(g.key);
  if (seitKlick !== undefined) {
    if (g.state !== "sleeping" || Date.now() - seitKlick > ANLAUF_MS) {
      frischGestartet.delete(g.key);
    } else {
      g = { ...g, state: "starting", startet_seit_s: (Date.now() - seitKlick) / 1000 };
    }
  }
  gameInfo[g.key] = g;
  const el = document.createElement("article");
  el.className = "card" + (g.state === "active" || g.state === "always_on" ? " active" : "");
  if (g.color) el.style.setProperty("--gac", g.color);
  el.dataset.game = g.key;
  const slots = g.slots ? `${g.slots} Plätze` : "";
  const players = (g.players != null && g.players !== undefined)
    ? `<span class="players big">${g.players}</span> <span class="plabel">im Spiel</span>`
    : (g.state === "active" || g.state === "always_on"
        ? (g.pruefbar === false ? "läuft · nicht fernprüfbar" : "läuft")
        : g.state === "starting"
          ? `<span class="boothint">wird gestartet, seit ${fmtDauer(g.startet_seit_s)} · Beitritt klappt erst, wenn hier „läuft“ steht</span>`
        : g.state === "stumm"
          ? `<span class="boothint warn">seit ${fmtDauer(g.startet_seit_s)} gestartet, antwortet aber nicht. Bitte einem Admin sagen</span>`
        : "");

  // Speicher-Vorschau. ★ Bewusst nur ein HINWEIS, kein gesperrter Knopf: reicht der freie
  // Speicher nicht, sagt der Arbiter nicht ab, sondern raeumt zuerst leere, ungeschuetzte
  // Server ab (_evict_for_ram) und startet dann meist doch. Ein deaktivierter Knopf waere
  // eine Sperre, die es in der Sache nicht gibt — er wuerde Starts verhindern, die
  // funktioniert haetten. Endgueltig abgelehnt wird nur, wenn danach noch immer zu wenig
  // frei ist UND jemand spielt; diese Absage kommt im Klartext vom Arbiter zurueck.
  const zuEng = g.state === "sleeping" && g.startbar === false;
  const bedarfHint = zuEng
    ? `<div class="lowmem">Eng: ${g.label} braucht ${fmtGB(g.schwelle_mb)} frei, so viel ist es gerade nicht.
       Ein Start räumt zuerst leere Server ab. Wer spielt, wird dabei nie unterbrochen.</div>`
    : "";

  // "laeuft" im Sinne von belegt: auch ein startender oder stummer Server haelt seinen
  // Platz und seinen Speicher. Wer hier nur `active` prueft, bietet mitten im Startvorgang
  // einen zweiten Startknopf an und laesst den Stopp-Knopf grau, obwohl gerade genau der
  // gebraucht wird (etwa wenn ein Server nicht hochkommt).
  const laeuft = g.state === "active" || g.state === "starting" || g.state === "stumm";
  const canStart = ROLE.may_start && g.state === "sleeping";
  const dauerlaeufer = !!g.always_on;
  const isMulti = g.multi_world && (g.worlds || []).length > 0;

  // Multi-Welten: schlafend darf jedes Mitglied die Welt fuers Starten waehlen.
  // Der Wechsel einer laufenden Welt sitzt im Welten-Panel (Admin), nicht mehr hier —
  // zwei Auswahlfelder mit gleichem Aussehen und verschiedener Wirkung auf einer Karte
  // waren die Vorlage fuer den falschen Klick.
  const worldSel = isMulti ? `
      <select class="world-sel" data-game="${g.key}" data-current="${g.world || ""}" aria-label="Welt wählen">
        ${g.worlds.map(w => `<option value="${w}" ${w === g.world ? "selected" : ""}>${capWorld(w)}</option>`).join("")}
      </select>` : "";
  const worldMeta = (isMulti && laeuft)
    ? `<span class="world-tag">${capWorld(g.world)}</span>` : "";

  // ★ Auf einer LAUFENDEN Karte ist ein grauer „Starten" reine Fuellung — und er stand an
  // erster Stelle, vor „Neustart"/„Stopp", auf dem Handy als volle Zeile. Was der Server
  // gerade tut, sagt schon das Abzeichen daneben. Bei „belegt"/„unbekannt" bleibt er
  // dagegen sichtbar und grau: dort sagt er etwas, naemlich dass es den Weg gibt, nur
  // gerade nicht — genau der Unterschied, den ein weggelassener Knopf verschluckt.
  const startBtn = (ROLE.may_start && !dauerlaeufer && !laeuft)
    ? `${g.state === "sleeping" ? worldSel : ""}<button class="primary" data-act="start" data-game="${g.key}" ${canStart ? "" : "disabled"}>Starten</button>` : "";
  // Gegenstueck zur Regel oben: auf einer SCHLAFENDEN Karte tun „Neustart" und „Stopp"
  // nichts, und dass nichts laeuft, steht schon im Abzeichen. Bei „belegt"/„unbekannt"
  // bleiben beide grau stehen — dort ist die Faehigkeit vorhanden, nur der Zeitpunkt
  // nicht, und das erklaert das Banner oben. Ein Knopf gehoert auf die Karte, wenn er
  // etwas tut oder wenn sein Nichtstun nicht schon woanders auf der Karte steht.
  const unklar = g.state === "blocked" || g.state === "unbekannt";
  const adminBtns = (ROLE.is_admin && !dauerlaeufer) ? `
      ${(laeuft || unklar) ? `
      <button class="ghost"  data-act="restart" data-game="${g.key}" ${laeuft ? "" : "disabled"}>Neustart</button>
      <button class="danger" data-act="stop"    data-game="${g.key}" ${laeuft ? "" : "disabled"}>Stopp</button>` : ""}
      ${laeuft ? (g.reserviert
        ? `<button class="ghost" data-act="release" data-game="${g.key}" title="Der Server geht wieder von selbst aus, wenn ihn niemand nutzt">Reservierung aufheben</button>`
        : `<button class="ghost" data-act="reserve" data-game="${g.key}" title="Server bleibt an und wird nicht verdrängt, bis die Reservierung fällt">Reservieren</button>`) : ""}
      ${isMulti ? `<button class="ghost tiny" data-act="worlds" data-game="${g.key}">Welten (${g.worlds.length})</button>` : ""}
      <button class="ghost tiny" data-act="snapshots" data-game="${g.key}">Sicherungen</button>` : "";

  el.innerHTML = `
    ${sceneFor(g.key)}
    <div class="card-head">
      <div><div class="card-title">${g.label}</div><div class="card-slots">${slots}</div></div>
      <span class="badge ${g.state}">${STATE_LABEL[g.state] || g.state}</span>
    </div>
    <div class="card-meta">${players}${worldMeta ? " " + worldMeta : ""}</div>
    ${g.join ? `<div class="card-join">${g.join}</div>` : ""}
    ${bedarfHint}
    <div class="actions">${startBtn}${adminBtns}</div>
    <div class="snap-panel" data-world="${g.key}" hidden></div>
    <div class="snap-panel" data-snap="${g.key}" hidden></div>`;
  return el;
}

// Gerade angestossene Starts: Spiel -> Zeitpunkt des Klicks.
// ★ Der Arbiter schreibt seinen Status nur im 60-Sekunden-Tick. Zwischen dem Startbefehl
// und dem naechsten Tick meldet er das Spiel unveraendert als "schlaeft" — die Kachel
// sprang also nach dem Klick zurueck auf schlafend, obwohl der Server hochfuhr. Das ist
// die Situation, in der jeder ein zweites Mal klickt. Bis der Arbiter den Start bestaetigt,
// zeigen wir hier, was wir sicher wissen: wir haben gerade gestartet.
const frischGestartet = new Map();
const ANLAUF_MS = 90000;

function markBusy() {
  $("grid").querySelectorAll(".card").forEach(c =>
    c.classList.toggle("busy", busy.has(c.dataset.game)));
}

// ── Welten (Admin): anlegen, wechseln, loeschen ───────────────────────
// Bis 2026-08-24 lagen diese drei Dinge an drei Stellen — ein Auswahlfeld in der
// Kopfzeile, ein kleiner grauer "Neue Welt"-Knopf zwischen den Steuerknoepfen und
// das Loeschen versteckt im Sicherungen-Panel. Wer nicht wusste, dass es die
// Funktion gibt, fand sie nicht. Jetzt ein Panel, das alles zeigt und den einen
// Satz dazuschreibt, der zum Missverstaendnis einlaedt: es laeuft eine Welt.
let worldOpen = null;

function renderWorldPanel(game) {
  const panel = $("grid").querySelector(`.snap-panel[data-world="${game}"]`);
  if (!panel) return;
  if (worldOpen !== game) { panel.hidden = true; return; }
  panel.hidden = false;
  const g = gameInfo[game] || {};
  const worlds = g.worlds || [];
  const laeuft = g.state === "active" || g.state === "starting" || g.state === "stumm";
  const rows = worlds.map(w => {
    const aktiv = w === g.world;
    return `
    <div class="snap-row">
      <div class="meta">
        <b>${esc(capWorld(w))}</b>
        ${aktiv ? `<span class="tag">${laeuft ? "läuft gerade" : "zuletzt gespielt"}</span>` : ""}
        <div class="sub"><code>${esc(w)}</code></div>
      </div>
      <span class="snap-btns">
        ${aktiv ? "" : `<button class="tiny primary" data-worldact="switch" data-game="${game}" data-world="${esc(w)}"
           title="${laeuft ? "Laufende Welt speichern, beenden und diese starten" : "Diese Welt beim nächsten Start verwenden"}"
           >${laeuft ? "Hierhin wechseln" : "Diese starten"}</button>`}
        ${aktiv ? "" : `<button class="tiny danger" data-worldact="delworld" data-game="${game}" data-world="${esc(w)}">Löschen</button>`}
      </span>
    </div>`;
  }).join("");
  const voll = worlds.length >= 6;
  panel.innerHTML = `
    <div class="snap-head">
      <b>Welten</b>
      <button class="tiny primary" data-worldact="new" data-game="${game}" ${voll ? "disabled" : ""}
        title="${voll ? "Höchstens 6 Welten je Spiel" : "Neue Welt anlegen"}">Neue Welt</button>
    </div>
    ${rows}
    <p class="sub" style="margin:8px 0 2px">
      ★ Es läuft immer nur <b style="color:var(--text)">eine</b> Welt je Spiel: mehrere Welten heißt
      wechseln, nicht nebeneinander. Beim Wechsel wird die laufende Welt gespeichert und beendet.
      Die Dateien einer neuen Welt entstehen erst beim ersten Start (dauert dann etwas länger).
      Höchstens 6 Welten je Spiel, 2 neue pro Tag.
    </p>`;
}

async function worldAction(act, game, world) {
  if (act === "new") {
    const wid = await ask({
      title: "Neue Welt anlegen",
      text: `Der Name wird zugleich der Weltname im Spiel. Erlaubt sind Kleinbuchstaben, Ziffern und
             Bindestrich, 3–24 Zeichen. Die Welt entsteht beim ersten Start.`,
      placeholder: "z. B. solo",
      pattern: /^[a-z0-9-]{3,24}$/,
      patternHint: "Nur a–z, 0–9 und Bindestrich, 3–24 Zeichen.",
      ok: "Anlegen",
    });
    if (!wid) return;
    try {
      const res = await api(`/api/games/${game}/worlds`, "POST", { id: wid, label: capWorld(wid) });
      toast(res.outcome === "ok" ? res.message : `Achtung: ${res.message}`, res.outcome === "ok" ? "ok" : "err", 8000);
    } catch (e) { fehler(e, "Fehler", 8000); }
    await refresh();
    renderWorldPanel(game);
    return;
  }
  if (act === "switch") {
    // Laeuft der Server, ist der Wechsel ein Neustart mit anderer Welt (Speichern +
    // Beenden + Start). Steht er still, ist es schlicht ein Start mit dieser Welt —
    // /switch wuerde dort einen Neustart von etwas verlangen, das gar nicht laeuft.
    const g = gameInfo[game] || {};
    const laeuft = g.state === "active" || g.state === "starting" || g.state === "stumm";
    await doAction(laeuft ? "switch" : "start", game, world);
    renderWorldPanel(game);
    return;
  }
  if (act === "delworld") {
    const ok = await ask({
      title: `Welt „${capWorld(world)}“ löschen?`,
      text: `Vorher entsteht eine letzte Sicherung, über die sich die Welt zurückholen lässt
             (Panel „Sicherungen“). Zum Bestätigen den Welt-Namen eintippen.`,
      placeholder: world,
      expect: world,
      ok: "Endgültig löschen",
      danger: true,
    });
    if (!ok) return;
    try {
      const res = await api(`/api/games/${game}/worlds/delete`, "POST", { id: world });
      if (res.outcome === "ok") toast(`Welt „${capWorld(world)}“ gelöscht.`);
      else toast(res.message, res.outcome === "blocked" ? "warn" : "err", 10000);
    } catch (e) { fehler(e, "Fehler", 10000); }
    await refresh();
    renderWorldPanel(game);
  }
}

// ── Snapshots (Admin): Liste, jetzt sichern, zurückspielen, löschen ──
function renderSnapPanel(game) {
  const panel = $("grid").querySelector(`.snap-panel[data-snap="${game}"]`);
  if (!panel) return;
  if (snapOpen !== game) { panel.hidden = true; return; }
  panel.hidden = false;
  const data = snapCache[game];
  const g = gameInfo[game] || {};
  if (!data) { panel.innerHTML = `<div class="loading" style="padding:10px 2px">Lade Sicherungen …</div>`; return; }
  // Auch ein startender oder stummer Server schreibt gleich wieder in seine Welt —
  // ein Restore waere dann ein Wettrennen zwischen Arbiter und Spielprozess.
  const running = g.state === "active" || g.state === "starting" || g.state === "stumm";
  const rows = (data.snapshots || []).map(s => `
    <div class="snap-row">
      <div class="meta">
        <b>${esc(capWorld(s.world) || s.file)}</b>
        <span class="tag ${s.kind === "manual" ? "pending" : ""}">${s.kind === "manual" ? "manuell" : "nächtlich"}</span>
        <div class="sub">${esc(s.mtime)} · ${fmtSize(s.size)} · <code>${esc(s.file)}</code></div>
      </div>
      <span class="snap-btns">
        <button class="tiny warn" data-snapact="restore" data-game="${game}" data-file="${esc(s.file)}" data-world="${esc(s.world)}"
          ${running ? 'disabled title="Zum Zurückspielen erst den Server stoppen"' : ""}>Zurückspielen</button>
        <button class="tiny danger" data-snapact="delsnap" data-game="${game}" data-file="${esc(s.file)}">Löschen</button>
      </span>
    </div>`).join("");
  // Das Welten-Loeschen sass frueher hier als kleines "×" hinter einem Namens-Chip —
  // die folgenreichste Aktion der Seite, versteckt im Sicherungen-Panel. Sie steht jetzt
  // im Welten-Panel, wo man sie sucht.
  panel.innerHTML = `
    <div class="snap-head">
      <b>Sicherungen</b>
      <button class="tiny primary" data-snapact="create" data-game="${game}">Jetzt sichern</button>
    </div>
    ${rows || `<p class="sub" style="margin:6px 0">Noch keine Sicherungen, nachts entsteht automatisch eine.</p>`}
    <p class="sub" style="margin:8px 0 2px">Zurückspielen geht nur bei gestopptem Server und legt vorher selbst eine Sicherung an.</p>`;
}

async function loadSnapshots(game, force = false) {
  if (!force && snapCache[game]) { renderSnapPanel(game); return; }
  renderSnapPanel(game);
  try {
    snapCache[game] = await api(`/api/games/${game}/snapshots`);
  } catch (e) {
    snapCache[game] = { snapshots: [] };
    fehler(e, "Sicherungen nicht abrufbar", 6000);
  }
  renderSnapPanel(game);
}

async function snapAction(act, game, file, world) {
  const g = gameInfo[game] || {};
  if (act === "create") {
    let w = null;
    if (g.multi_world && g.state !== "active" && (g.worlds || []).length > 1) {
      const sel = $("grid").querySelector(`select.world-sel[data-game="${game}"]`);
      w = sel ? sel.value : null;
    }
    toast("Erstelle Sicherung … (kann eine Minute dauern)", "ok", 60000);
    try {
      const res = await api(`/api/games/${game}/snapshot${w ? `?world=${encodeURIComponent(w)}` : ""}`, "POST");
      toast(res.outcome === "ok" ? "Sicherung erstellt." : res.message, res.outcome === "ok" ? "ok" : "err", 8000);
    } catch (e) { fehler(e, "Fehler", 8000); }
    await loadSnapshots(game, true);
    return;
  }
  if (act === "delsnap") {
    const ok = await ask({ title: "Sicherung löschen?", text: file, ok: "Löschen", danger: true });
    if (!ok) return;
    try {
      const res = await api(`/api/games/${game}/snapshots/delete`, "POST", { file });
      toast(res.outcome === "ok" ? "Sicherung gelöscht." : res.message, res.outcome === "ok" ? "ok" : "err", 8000);
    } catch (e) { fehler(e, "Fehler", 8000); }
    await loadSnapshots(game, true);
    return;
  }
  if (act === "restore") {
    const expect = world || game;
    const ok = await ask({
      title: "Diesen Stand zurückspielen?",
      text: `${file}\n\nDer jetzige Stand wird vorher automatisch gesichert. Zum Bestätigen „${expect}“ eintippen.`,
      placeholder: expect, expect, ok: "Zurückspielen", danger: true,
    });
    if (!ok) return;
    toast("Spiele Sicherung zurück … (kann ein paar Minuten dauern)", "ok", 180000);
    try {
      const res = await api(`/api/games/${game}/restore`, "POST", { file });
      if (res.outcome === "ok") toast("Sicherung zurückgespielt.");
      else toast(res.message, res.outcome === "blocked" ? "warn" : "err", 10000);
    } catch (e) { fehler(e, "Fehler", 10000); }
    await loadSnapshots(game, true);
  }
}

async function doAction(act, game, weltVorgabe = "") {
  if (act === "worlds") {
    worldOpen = worldOpen === game ? null : game;
    renderWorldPanel(game);
    return;
  }
  if (act === "snapshots") {
    snapOpen = snapOpen === game ? null : game;
    if (snapOpen) await loadSnapshots(game); else renderSnapPanel(game);
    return;
  }
  // Nur DIESES Spiel sperren. Zwei Spiele parallel zu starten ist seit dem
  // Mehr-Spiel-Umbau ein gueltiger Wunsch, kein Bedienfehler.
  if (busy.has(game)) { toast(`Für ${game} läuft schon ein Vorgang.`, "warn"); return; }
  // Welt: entweder ausdruecklich uebergeben (Welten-Panel) oder aus dem Auswahlfeld
  // der Karte (Start durch ein Mitglied).
  let world = weltVorgabe;
  if (!world && act === "start") {
    const sel = $("grid").querySelector(`select.world-sel[data-game="${game}"]`);
    world = sel ? sel.value : "";
  }
  if (act === "switch" && world && world === (gameInfo[game] || {}).world) {
    toast(`${capWorld(world)} läuft bereits.`, "warn"); return;
  }
  busy.add(game); markBusy();
  // Nur die Knoepfe dieser Karte sperren — die anderen Karten bleiben bedienbar.
  const eigene = $("grid").querySelector(`.card[data-game="${game}"]`);
  if (eigene) eigene.querySelectorAll("button").forEach(b => b.disabled = true);
  const verb = { start: "Starte", stop: "Stoppe", restart: "Starte neu", switch: "Wechsle Welt auf",
                 reserve: "Reserviere", release: "Gebe frei" }[act];
  toast(`${verb} ${act === "switch" ? capWorld(world) + " (" + game + ")" : game} … (kann 1–3 min dauern)`, "ok", 180000);
  try {
    const q = world ? `?world=${encodeURIComponent(world)}` : "";
    const res = await api(`/api/games/${game}/${act}${q}`, "POST");
    if (res.outcome === "ok") {
      // Nach dem Startbefehl ist der Server noch nicht da. Das hier zu sagen ist der
      // Unterschied zwischen "fertig" und "gleich" — die Kachel zeigt danach "startet …".
      if (act === "start" || act === "switch" || act === "restart") {
        frischGestartet.set(game, Date.now());
        toast(`${game}: ${res.message || "gestartet"}. Er braucht jetzt 1–3 Minuten, bis der Beitritt klappt.`);
      } else {
        frischGestartet.delete(game);   // Stopp/Reservierung: kein Anlauf zu ueberbruecken
        toast(`${game}: ${res.message || "fertig"}`);
      }
    } else if (res.outcome === "conflict") {
      // Kein Erzwingen-Hinweis mehr: die Absage ist endgueltig, auch fuer Admins.
      // Ein Angebot, das es nicht gibt, laesst den Nutzer nach dem Knopf suchen.
      toast(res.message, "warn", 10000);
    } else toast(`${game}: ${res.message}`, "err", 10000);
  } catch (e) {
    fehler(e, "Fehler", 10000);
  } finally { busy.delete(game); await refresh(); }
}

// Aussetzer der eigenen Verbindung, seit dem letzten geglueckten Abruf. Eine
// Kachelwand, die stehen bleibt, ist von einer aktuellen nicht zu unterscheiden —
// man liest den alten Stand als den jetzigen und tritt einem Server bei, der
// laengst wieder schlaeft. Erst ab dem dritten Fehlversuch gemeldet, damit ein
// einzelner Aussetzer keine Warnung blinken laesst.
let fehlversuche = 0;
let letzterStand = 0;
const STILLSTAND_AB = 3;

function zeigeStillstand() {
  $("grid").classList.add("stale");
  const alter = letzterStand ? fmtDauer((Date.now() - letzterStand) / 1000) : null;
  $("slot-hint").textContent =
    "Die Seite erreicht den Server gerade nicht" +
    (alter ? `: die Kacheln zeigen den Stand von vor ${alter}.` : ".") +
    " Es wird weiter versucht.";
}

async function refresh() {
  try {
    const s = await api("/api/status");
    fehlversuche = 0;
    letzterStand = Date.now();
    $("grid").classList.remove("stale");
    ROLE.is_admin = !!s.is_admin; ROLE.may_start = !!s.may_start;
    if (!s.ok) {
      $("grid").innerHTML = `<div class="loading">${s.error || "Status nicht abrufbar"}</div>`;
      return;
    }
    $("node-ram").innerHTML = ramBar(s.ram_mb, s.frei_mb, s.startend_mb);
    const hint = $("slot-hint");
    // Bridge weg: die Dauerlaeufer stehen trotzdem da (eigene Probe), alles andere ist
    // unbekannt. Das gehoert gesagt — eine Liste ohne Hinweis liest sich wie Normalbetrieb.
    if (s.arbiter_ok === false) {
      hint.textContent = "Steuerung nicht erreichbar, die Zustände unten sind ungeprüft. "
                       + "Starten und Stoppen geht gerade nicht.";
      const grid0 = $("grid");
      grid0.innerHTML = "";
      (s.games || []).forEach(g => grid0.appendChild(card(g)));
      return;
    }
    // „Belegt" gibt es nur noch, wenn das Windows-Lab im Wartungsmodus reserviert ist —
    // zwischen Spielen blockiert nichts mehr. Der frühere Zusatz „(oder du erzwingst)"
    // stand hier noch, nachdem der Erzwingen-Knopf am 2026-08-23 ersatzlos entfernt
    // wurde: ein Angebot, das es nicht gibt, schickt Admins auf die Suche danach.
    hint.textContent = s.holder
      ? `${s.holder_label} ist im Wartungsmodus reserviert und hat Vorrang. Spielserver starten erst wieder, wenn die Reservierung fällt.`
      : "";

    const grid = $("grid");
    grid.innerHTML = "";
    (s.games || []).forEach(g => grid.appendChild(card(g)));
    grid.querySelectorAll("button[data-act]").forEach(b =>
      b.addEventListener("click", () => doAction(b.dataset.act, b.dataset.game)));
    if (worldOpen) renderWorldPanel(worldOpen);
    if (snapOpen) renderSnapPanel(snapOpen);
    markBusy();
  } catch (e) {
    if (abgemeldet(e)) return;
    // Nicht schlucken: bis 2026-08-27 endete jeder andere Fehler hier lautlos, und die
    // Seite zeigte den letzten Stand unbegrenzt weiter, als waere er der jetzige.
    if (++fehlversuche >= STILLSTAND_AB) zeigeStillstand();
  }
}

// Kein Poll, solange niemand hinsieht. Bei offenem Hintergrund-Tab waren das rund um die
// Uhr 17.000 Statusabfragen am Tag je Tab — jede eine Runde durch Bridge und Arbiter.
// Beim Zurueckkehren wird sofort aktualisiert, damit man nie einen alten Stand sieht.
async function tick() {
  if (!document.hidden && busy.size === 0) await refresh();
  setTimeout(tick, POLL_MS);
}
(async function () {
  // Delegierte Listener EINMAL am (statischen) Grid-Element — uebersteht jeden
  // innerHTML-Rebuild der Karten.
  $("grid").addEventListener("click", (ev) => {
    const s = ev.target.closest("button[data-snapact]");
    if (s && !s.disabled) { snapAction(s.dataset.snapact, s.dataset.game, s.dataset.file || "", s.dataset.world || ""); return; }
    const w = ev.target.closest("button[data-worldact]");
    if (w && !w.disabled) worldAction(w.dataset.worldact, w.dataset.game, w.dataset.world || "");
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  await refresh();
  setTimeout(tick, POLL_MS);
})();
