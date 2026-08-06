/* ============================================================================
   Lead & Floor Board — client logic
   ----------------------------------------------------------------------------
   Runs unattended on a wall TV. Polls one JSON endpoint and renders three
   panels that follow the customer lifecycle:

     1. New Inquiries    — count-up since the inquiry arrived   (longer = worse)
     2. Appointments     — COUNTDOWN to a booked appointment time
     3. On the Floor     — count-up since check-in

   All timers/countdowns tick every second, client-side. The display does no
   pipeline-stage logic: n8n decides which array each record lands in, we just
   render what we receive.

   TUNE ME: every threshold and interval lives in the CONFIG block below so you
   never have to hunt through the code to adjust the color bands.
   ========================================================================== */
"use strict";

/* ------------------------------------------------------------------ CONFIG */

/* --- New Inquiries: count-up thresholds, in SECONDS (longer wait = worse). */
const INQUIRY_LEVELS = [
  { level: "calm",   maxSeconds:  5 * 60 }, //  0–5  min  — calm green
  { level: "amber",  maxSeconds: 15 * 60 }, //  5–15 min  — amber
  { level: "orange", maxSeconds: 30 * 60 }, // 15–30 min  — orange
  { level: "red",    maxSeconds: Infinity }, // 30+  min  — red + slow pulse
];

/* --- On the Floor: count-up thresholds, in SECONDS. */
const FLOOR_LEVELS = [
  { level: "neutral", maxSeconds: 10 * 60 }, //  0–10 min  — neutral
  { level: "amber",   maxSeconds: 20 * 60 }, // 10–20 min  — amber (check in)
  { level: "orange",  maxSeconds: 40 * 60 }, // 20–40 min  — orange (attention)
  { level: "red",     maxSeconds: Infinity }, // 40+  min  — red + slow pulse
];

/* --- Appointments: COUNTDOWN thresholds, in SECONDS relative to appt time.
   `remaining` is positive before the appointment, negative once it's past. */
const APPOINTMENT_THRESHOLDS = {
  neutralBeyondSec: 60 * 60, // remaining above this        -> neutral (dim)
  prepWithinSec:    15 * 60, // remaining above this (≤60m) -> blue (prep)
  // remaining at/below prepWithinSec, down to -lateAfterSec -> green (arriving)
  lateAfterSec:     10 * 60, // this many seconds PAST appt -> amber (late?)
  noShowAfterSec:   20 * 60, // this many seconds PAST appt -> red (no-show)
};

/* Every CSS urgency class we might add to a card (used to reset before re-tag). */
const ALL_LEVEL_CLASSES = [
  "lvl-calm", "lvl-neutral", "lvl-blue", "lvl-green",
  "lvl-amber", "lvl-orange", "lvl-red",
];

/* Fallbacks — overridden at runtime by /board/config. */
const CONFIG = {
  pollSeconds: 15, // how often we re-poll the feed
  staleSeconds: 90, // no successful poll within this window => "connection lost"
  feedUrl: "/board/feed",
  configUrl: "/board/config",
  storeName: "Lead & Floor Board",
};

/* --------------------------------------------------------------- utilities */

const $ = (sel) => document.querySelector(sel);
const now = () => Date.now();

/** Level lookup for a count-up age (seconds) against a threshold table. */
function levelFor(ageSeconds, table) {
  for (const band of table) {
    if (ageSeconds < band.maxSeconds) return band.level;
  }
  return table[table.length - 1].level;
}

/** Countdown -> {level, label} for an appointment, `remaining` in seconds. */
function appointmentLevel(remaining) {
  const T = APPOINTMENT_THRESHOLDS;
  if (remaining > T.neutralBeyondSec) return { level: "neutral", label: "Upcoming" };
  if (remaining > T.prepWithinSec) return { level: "blue", label: "Prep" };
  if (-remaining < T.lateAfterSec) return { level: "green", label: "Arriving" };
  if (-remaining < T.noShowAfterSec) return { level: "amber", label: "Late?" };
  return { level: "red", label: "No show — call" };
}

/** MM:SS under an hour, then H:MM. */
function fmtTimer(ageSeconds) {
  const s = Math.max(0, Math.floor(ageSeconds));
  const h = Math.floor(s / 3600);
  if (h > 0) return `${h}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Live countdown text: "in 42:15", "in 2:40", or "12:30 late". */
function fmtCountdown(remaining) {
  const s = Math.abs(Math.floor(remaining));
  let body;
  if (s >= 3600) body = `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
  else body = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  return remaining >= 0 ? `in ${body}` : `${body} late`;
}

/** A wall-clock time like "2:30 PM". */
function fmtClock(ms) {
  return new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** Local calendar-day key, for today/tomorrow bucketing. */
function dayKey(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

function parseMs(iso) {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? now() : t;
}

/* ------------------------------------------------------------------- chime */
/* A short two-tone beep when a card crosses into red. Muted by default; the
   only interactive control on the whole board is the mute toggle, and its click
   doubles as the user gesture that unlocks audio. */
const Chime = {
  on: false,
  ctx: null,
  enable() {
    this.on = true;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (this.ctx.state === "suspended") this.ctx.resume();
    } catch (_) {
      /* no audio available — toggle still flips, just silent */
    }
  },
  disable() { this.on = false; },
  play() {
    if (!this.on || !this.ctx) return;
    const t0 = this.ctx.currentTime;
    [880, 660].forEach((freq, i) => {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = t0 + i * 0.18;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
      osc.connect(gain).connect(this.ctx.destination);
      osc.start(start);
      osc.stop(start + 0.18);
    });
  },
};

/* -------------------------------------------------------------- feed/state */

/* Per-panel registry: id -> { el, sortMs, level }. `sortMs` is the reference
   time — receivedAt/checkedInAt for count-up panels, appointmentAt for the
   countdown panel. Cards are ordered by sortMs ascending, which puts the
   oldest inquiry / soonest appointment first (top-left). */
const panels = {
  leads: { root: $("#leads"), items: new Map(), levels: INQUIRY_LEVELS, kind: "lead" },
  appts: { root: $("#appts"), items: new Map(), levels: null, kind: "appt" },
  floor: { root: $("#floor"), items: new Map(), levels: FLOOR_LEVELS, kind: "floor" },
};

let lastOkMs = now(); // last successful poll — drives the stale indicator
let hasLoaded = false; // becomes true after the first good poll

/* -------------------------------------------------------------- rendering */

function leadCardHTML(d) {
  const rep = d.assignedTo
    ? `<span class="meta-assignee">${esc(d.assignedTo)}</span>`
    : `<span class="meta-assignee unassigned">Unassigned</span>`;
  const n = Number(d.attempts) || 0;
  const attempts = n === 0 ? "No attempts" : `${n} attempt${n === 1 ? "" : "s"}`;
  return `
    <div class="card-head">
      <span class="card-name">${esc(d.name)}</span>
      <span class="card-timer">--:--</span>
    </div>
    <div class="card-sub">
      <span class="badge">${esc(d.source || "—")}</span>
      ${rep}
      <span class="meta-side">${attempts}</span>
    </div>`;
}

function floorCardHTML(d) {
  const assoc = d.assignedTo
    ? `<span class="meta-assignee">${esc(d.assignedTo)}</span>`
    : `<span class="meta-assignee unassigned">Needs greeter</span>`;
  return `
    <div class="card-head">
      <span class="card-name">${esc(d.party)}</span>
      <span class="card-timer">--:--</span>
    </div>
    <div class="card-interest"><span class="lbl">Here for:</span> ${esc(d.interest || "—")}</div>
    <div class="card-sub">
      <span class="badge">👥 ${Number(d.headcount) || 1}</span>
      ${assoc}
    </div>`;
}

function apptCardHTML(d, appointmentMs) {
  const assoc = d.assignedTo
    ? `<span class="meta-assignee">${esc(d.assignedTo)}</span>`
    : `<span class="meta-assignee unassigned">No associate</span>`;
  const confirm = d.confirmed
    ? `<span class="confirm-badge confirmed">✓ Confirmed</span>`
    : `<span class="confirm-badge unconfirmed">Unconfirmed</span>`;
  return `
    <div class="card-head">
      <span class="card-name">${esc(d.name)}</span>
      <span class="card-timer appt-time">${esc(fmtClock(appointmentMs))}</span>
    </div>
    <div class="appt-row">
      <span class="card-countdown">--:--</span>
      <span class="card-status">—</span>
    </div>
    <div class="card-interest"><span class="lbl">Here for:</span> ${esc(d.interest || "—")}</div>
    <div class="card-sub">
      ${assoc}
      ${confirm}
    </div>`;
}

function cardHTML(d, kind, sortMs) {
  if (kind === "lead") return leadCardHTML(d);
  if (kind === "floor") return floorCardHTML(d);
  return apptCardHTML(d, sortMs);
}

/** Update mutable text fields of an existing card in place. */
function refreshCardFields(entry, d, kind) {
  const el = entry.el;
  if (kind === "lead") {
    el.querySelector(".card-name").textContent = d.name ?? "";
    el.querySelector(".badge").textContent = d.source || "—";
    const n = Number(d.attempts) || 0;
    el.querySelector(".meta-side").textContent =
      n === 0 ? "No attempts" : `${n} attempt${n === 1 ? "" : "s"}`;
    setAssignee(el, d.assignedTo, "Unassigned");
  } else if (kind === "floor") {
    el.querySelector(".card-name").textContent = d.party ?? "";
    el.querySelector(".badge").textContent = "👥 " + (Number(d.headcount) || 1);
    el.querySelector(".card-interest").innerHTML =
      `<span class="lbl">Here for:</span> ${esc(d.interest || "—")}`;
    setAssignee(el, d.assignedTo, "Needs greeter");
  } else {
    el.querySelector(".card-name").textContent = d.name ?? "";
    el.querySelector(".appt-time").textContent = fmtClock(entry.sortMs);
    el.querySelector(".card-interest").innerHTML =
      `<span class="lbl">Here for:</span> ${esc(d.interest || "—")}`;
    setAssignee(el, d.assignedTo, "No associate");
    const cb = el.querySelector(".confirm-badge");
    cb.textContent = d.confirmed ? "✓ Confirmed" : "Unconfirmed";
    cb.className = "confirm-badge " + (d.confirmed ? "confirmed" : "unconfirmed");
    el.classList.toggle("unconfirmed", !d.confirmed);
  }
}

function setAssignee(el, value, emptyLabel) {
  const a = el.querySelector(".meta-assignee");
  if (value) {
    a.textContent = value;
    a.classList.remove("unassigned");
  } else {
    a.textContent = emptyLabel;
    a.classList.add("unassigned");
  }
}

/** Reference time used for sorting + timers for a given record. */
function refMs(d, kind) {
  if (kind === "appt") return parseMs(d.appointmentAt);
  if (kind === "floor") return parseMs(d.checkedInAt);
  return parseMs(d.receivedAt);
}

/** Diff incoming feed items against what's on screen for one panel. */
function syncPanel(panel, list) {
  const incoming = new Map((list || []).map((d) => [String(d.id), d]));

  // Remove cards no longer present — fade them out first.
  for (const [id, entry] of panel.items) {
    if (!incoming.has(id)) {
      const el = entry.el;
      el.classList.add("leaving");
      panel.items.delete(id);
      setTimeout(() => el.remove(), 600);
    }
  }

  // Add new cards / update existing ones.
  for (const [id, d] of incoming) {
    const sortMs = refMs(d, panel.kind);
    let entry = panel.items.get(id);
    if (!entry) {
      const el = document.createElement("div");
      el.className = "card flash";
      if (panel.kind === "appt" && !d.confirmed) el.classList.add("unconfirmed");
      el.innerHTML = cardHTML(d, panel.kind, sortMs);
      setTimeout(() => el.classList.remove("flash"), 1300);
      entry = { el, sortMs };
      panel.items.set(id, entry);
      panel.root.appendChild(el);
    } else {
      entry.sortMs = sortMs;
      refreshCardFields(entry, d, panel.kind);
    }
  }

  reorder(panel);
  updatePanelTimers(panel); // paint immediately, don't wait for the 1s tick
  reflowOverflow(panel);
}

/** Ascending sortMs => oldest inquiry / soonest appointment first (top-left). */
function reorder(panel) {
  [...panel.items.values()]
    .sort((a, b) => a.sortMs - b.sortMs)
    .forEach((entry) => panel.root.appendChild(entry.el));
}

/** Apply an urgency level class, chiming on a genuine crossing into red. */
function applyLevel(entry, level) {
  if (level === entry.level) return;
  const prev = entry.level;
  entry.el.classList.remove(...ALL_LEVEL_CLASSES);
  entry.el.classList.add("lvl-" + level);
  entry.level = level;
  if (level === "red" && prev && prev !== "red") Chime.play();
}

/** Recompute timers/countdowns + urgency level for every card in a panel. */
function updatePanelTimers(panel) {
  const t = now();
  for (const entry of panel.items.values()) {
    if (entry.el.classList.contains("leaving")) continue;
    if (panel.kind === "appt") {
      const remaining = (entry.sortMs - t) / 1000;
      entry.el.querySelector(".card-countdown").textContent = fmtCountdown(remaining);
      const { level, label } = appointmentLevel(remaining);
      entry.el.querySelector(".card-status").textContent = label;
      applyLevel(entry, level);
    } else {
      const ageSec = (t - entry.sortMs) / 1000;
      entry.el.querySelector(".card-timer").textContent = fmtTimer(ageSec);
      applyLevel(entry, levelFor(ageSec, panel.levels));
    }
  }
}

/** Hide the least-urgent overflow rather than shrinking text; show a "+N" chip. */
function reflowOverflow(panel) {
  const root = panel.root;
  root.querySelectorAll(".overflow-chip, .empty").forEach((n) => n.remove());
  const cards = [...root.querySelectorAll(".card:not(.leaving)")];

  if (cards.length === 0) {
    root.appendChild(emptyState(panel.kind));
    return;
  }
  cards.forEach((c) => (c.style.display = ""));
  let hidden = 0;
  for (let i = cards.length - 1; i >= 1; i--) {
    if (root.scrollHeight <= root.clientHeight + 1) break;
    cards[i].style.display = "none";
    hidden++;
  }
  if (hidden > 0) {
    const chip = document.createElement("div");
    chip.className = "overflow-chip";
    chip.textContent = `+${hidden} more`;
    root.appendChild(chip);
  }
}

function emptyState(kind) {
  const el = document.createElement("div");
  el.className = "empty";
  if (!hasLoaded) {
    el.innerHTML = `<div class="em-ic">📡</div>
      <div class="em-title" style="color:var(--ink-dim)">Connecting…</div>
      <div class="em-sub">Waiting for the first update</div>`;
    return el;
  }
  const copy = {
    lead: ["✅", "All caught up", "No leads awaiting a callback"],
    appt: ["📅", "No appointments left", "Nothing else booked for today"],
    floor: ["🛋️", "All caught up", "No customers on the floor right now"],
  }[kind];
  el.innerHTML = `<div class="em-ic">${copy[0]}</div>
    <div class="em-title">${copy[1]}</div>
    <div class="em-sub">${copy[2]}</div>`;
  return el;
}

/* ------------------------------------------------------------- header/stats */

function updateHeaderCounts(data, apptsTodayCount) {
  const awaiting = (data.inquiries || []).length;
  const onFloor = (data.floor || []).length;
  const total = data.stats && Number.isFinite(data.stats.inquiriesToday)
    ? data.stats.inquiriesToday
    : awaiting;
  $("#count-awaiting").textContent = awaiting;
  $("#count-appts").textContent = apptsTodayCount;
  $("#count-floor").textContent = onFloor;
  $("#count-total").textContent = total;
  $("#panel-leads-count").textContent = awaiting;
  $("#panel-appts-count").textContent = apptsTodayCount;
  $("#panel-floor-count").textContent = onFloor;
}

function updateTomorrowChip(n) {
  const chip = $("#appts-tomorrow");
  chip.hidden = n <= 0;
  chip.textContent = `Tomorrow: ${n}`;
}

function updateClock() {
  $("#clock").textContent = new Date().toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function updateStale() {
  $("#stale").hidden = now() - lastOkMs <= CONFIG.staleSeconds * 1000;
}

/* --------------------------------------------------------------- lifecycle */

/** Split appointments into today's cards vs a tomorrow count. Arrived
    appointments are on the floor now, so they drop out of this panel. */
function bucketAppointments(appts) {
  const todayKey = dayKey(now());
  const tomKey = dayKey(now() + 86400000);
  const today = [];
  let tomorrow = 0;
  for (const a of appts || []) {
    if (a.arrived) continue;
    const k = dayKey(parseMs(a.appointmentAt));
    if (k === todayKey) today.push(a);
    else if (k === tomKey) tomorrow++;
  }
  return { today, tomorrow };
}

async function poll() {
  try {
    const res = await fetch(CONFIG.feedUrl, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    lastOkMs = now();
    hasLoaded = true;

    const { today, tomorrow } = bucketAppointments(data.appointments);
    syncPanel(panels.leads, data.inquiries);
    syncPanel(panels.appts, today);
    syncPanel(panels.floor, data.floor);
    updateHeaderCounts(data, today.length);
    updateTomorrowChip(tomorrow);
    updateStale();
  } catch (err) {
    // Never blank the screen: keep the last data on-screen, timers keep
    // ticking, and the stale indicator appears once we cross the threshold.
    console.warn("Feed poll failed:", err.message);
    updateStale();
  }
}

/** One-second heartbeat: timers, countdowns, clock, colors, stale — no network. */
function tick() {
  updatePanelTimers(panels.leads);
  updatePanelTimers(panels.appts);
  updatePanelTimers(panels.floor);
  updateClock();
  updateStale();
}

async function loadConfig() {
  try {
    const res = await fetch(CONFIG.configUrl, { cache: "no-store" });
    if (res.ok) {
      const c = await res.json();
      if (c.pollSeconds) CONFIG.pollSeconds = c.pollSeconds;
      if (c.staleSeconds) CONFIG.staleSeconds = c.staleSeconds;
      if (c.storeName) CONFIG.storeName = c.storeName;
    }
  } catch (_) {
    /* fall back to defaults */
  }
  $("#store-name").textContent = CONFIG.storeName;
  document.title = CONFIG.storeName + " — Lead & Floor Board";
}

function wireChimeToggle() {
  const btn = $("#chime-toggle");
  btn.addEventListener("click", () => {
    if (Chime.on) {
      Chime.disable();
      btn.setAttribute("aria-pressed", "false");
      btn.querySelector(".chime-ic").textContent = "🔕";
    } else {
      Chime.enable();
      btn.setAttribute("aria-pressed", "true");
      btn.querySelector(".chime-ic").textContent = "🔔";
    }
  });
}

async function main() {
  wireChimeToggle();
  updateClock();
  // Render initial "Connecting…" states so the screen is never blank.
  reflowOverflow(panels.leads);
  reflowOverflow(panels.appts);
  reflowOverflow(panels.floor);

  await loadConfig();
  await poll();

  setInterval(poll, CONFIG.pollSeconds * 1000);
  setInterval(tick, 1000);

  window.addEventListener("resize", () => {
    reflowOverflow(panels.leads);
    reflowOverflow(panels.appts);
    reflowOverflow(panels.floor);
  });
}

main();
