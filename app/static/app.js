"use strict";

const POLL_MS = 5000;
let ME = { is_admin: false, may_start: false, username: "" };
let busy = false;      // blockt Parallel-Aktionen (der .18-Slot ist seriell)
let pollTimer = null;

const $ = (id) => document.getElementById(id);

const STATE_LABEL = { active: "🟢 läuft", sleeping: "⚪ schläft", blocked: "🔒 belegt" };

async function api(path, method = "GET") {
  const r = await fetch(path, { method, headers: { "Accept": "application/json" } });
  if (!r.ok) {
    let detail = r.status;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return r.json();
}

function toast(msg, kind = "ok", ms = 6000) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (kind === "err" ? " err" : kind === "warn" ? " warn" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

async function loadMe() {
  try {
    ME = await api("/api/me");
    const b = $("role-badge");
    if (ME.is_admin) { b.textContent = "Admin"; b.className = "role-badge admin"; }
    else if (ME.may_start) { b.textContent = "Spieler"; b.className = "role-badge user"; }
    else { b.textContent = "Gast"; b.className = "role-badge"; }
  } catch (e) { /* forward-auth setzt das ohnehin */ }
}

function ramBar(mb) {
  if (mb == null) return "";
  const gb = (mb / 1024).toFixed(1);
  return `RAM frei auf .18: <b>${gb} GB</b>`;
}

function card(g) {
  const el = document.createElement("article");
  el.className = "card" + (g.state === "active" ? " active" : "");

  const slots = g.slots ? `· ${g.slots} Slots` : "";
  const players = (g.players != null)
    ? `<span class="players">${g.players} online</span>`
    : (g.state === "active" ? "läuft" : "");

  const canStart = ME.may_start && g.state === "sleeping";
  const startBtn = ME.may_start
    ? `<button class="primary" data-act="start" data-game="${g.key}" ${canStart ? "" : "disabled"}>▶ Starten</button>`
    : "";
  const adminBtns = ME.is_admin ? `
      <button class="ghost"  data-act="restart" data-game="${g.key}" ${g.state === "active" ? "" : "disabled"}>↻ Neustart</button>
      <button class="danger" data-act="stop"    data-game="${g.key}" ${g.state === "active" ? "" : "disabled"}>■ Stopp</button>
      ${g.state === "blocked" ? `<button class="force" data-act="force" data-game="${g.key}">⚡ Erzwingen</button>` : ""}
  ` : "";

  el.innerHTML = `
    <div class="card-head">
      <span class="card-emoji">${g.emoji}</span>
      <div>
        <div class="card-title">${g.label}</div>
        <div class="card-slots">${slots}</div>
      </div>
      <span class="badge ${g.state}">${STATE_LABEL[g.state] || g.state}</span>
    </div>
    <div class="card-meta">${players}</div>
    ${g.join ? `<div class="card-join">🔗 ${g.join}</div>` : ""}
    <div class="actions">${startBtn}${adminBtns}</div>
  `;
  return el;
}

async function doAction(act, game, btn) {
  if (busy) { toast("Ein anderer Vorgang läuft gerade — kurz warten.", "warn"); return; }
  busy = true;
  const grid = $("grid");
  grid.querySelectorAll("button").forEach(b => b.disabled = true);
  toast(`${act === "start" ? "Starte" : act === "stop" ? "Stoppe" : act === "restart" ? "Starte neu" : "Erzwinge"} ${game} … (kann 1–3 min dauern)`, "ok", 180000);
  try {
    const res = await api(`/api/games/${game}/${act}`, "POST");
    if (res.outcome === "ok") {
      toast(`✅ ${game}: ${res.message || "fertig"}`);
    } else if (res.outcome === "conflict") {
      const extra = res.can_force ? "\nDu kannst als Admin „⚡ Erzwingen“ nutzen." : "\nEin Admin kann den Start erzwingen.";
      toast(`🔒 ${res.message}${extra}`, "warn", 10000);
    } else {
      toast(`⚠️ ${game}: ${res.message}`, "err", 10000);
    }
  } catch (e) {
    toast(`⚠️ Fehler: ${e.message}`, "err", 10000);
  } finally {
    busy = false;
    await refresh();
  }
}

async function refresh() {
  try {
    const s = await api("/api/status");
    if (!s.ok) {
      $("grid").innerHTML = `<div class="loading">⚠️ ${s.error || "Status nicht abrufbar"}</div>`;
      $("foot-status").textContent = "Arbiter offline";
      return;
    }
    $("node-ram").innerHTML = ramBar(s.ram_mb);
    $("foot-status").textContent = `${s.node || ".18"} · ${s.ts || ""} · Modus ${s.mode || "?"}`;

    const hint = $("slot-hint");
    if (s.holder && s.holder !== "minecraft") {
      hint.textContent = `▶ Aktuell aktiv: ${s.holder_label}. Ein anderer Server kann erst starten, wenn dieser leer ist (oder ein Admin erzwingt).`;
    } else if (s.holder === "minecraft") {
      hint.textContent = "▶ Minecraft belegt gerade den Slot.";
    } else {
      hint.textContent = "";
    }

    const grid = $("grid");
    grid.innerHTML = "";
    (s.games || []).forEach(g => grid.appendChild(card(g)));
    grid.querySelectorAll("button[data-act]").forEach(b => {
      b.addEventListener("click", () => doAction(b.dataset.act, b.dataset.game, b));
    });
  } catch (e) {
    $("foot-status").textContent = "Verbindungsfehler";
  }
}

async function tick() {
  if (!busy) await refresh();
  pollTimer = setTimeout(tick, POLL_MS);
}

(async function init() {
  await loadMe();
  await refresh();
  pollTimer = setTimeout(tick, POLL_MS);
})();
