/* ============================================================================
   Lead & Appointment Board — client logic
   ----------------------------------------------------------------------------
   Two panels: New Inquiries (count-up) and Appointments Today (countdown).
   Everything renders on a fixed 1920x1080 canvas that is scaled to fit the
   display. Timers/countdowns tick every second, client-side.

   TUNE ME: all color thresholds and intervals are named constants below.
   ========================================================================== */
"use strict";

/* ------------------------------------------------------------------ CONFIG */

/* New Inquiries: count-up thresholds in SECONDS (longer wait = more urgent).
   Goal is a callback within ~10 min, so the scale is tight: green -> yellow ->
   orange -> red, hitting red at 20 min. Tune the minutes freely. */
const INQUIRY_LEVELS = [
  { level: "green",  maxSeconds:  5 * 60 }, //  0–5   min  (fresh)
  { level: "yellow", maxSeconds: 10 * 60 }, //  5–10  min  (approaching the 10-min goal)
  { level: "orange", maxSeconds: 20 * 60 }, // 10–20  min  (past the goal)
  { level: "red",    maxSeconds: Infinity }, // 20+   min  (too long, pulses)
];

/* Appointments: COUNTDOWN thresholds in SECONDS relative to the appt time.
   `remaining` is positive before the appointment, negative once it's past.
   Each level also has a `rank` used for urgency sorting (0 = most urgent). */
const APPOINTMENT_THRESHOLDS = {
  neutralBeyondSec: 60 * 60, // remaining above this        -> neutral (later today)
  prepWithinSec:    15 * 60, // remaining above this (≤60m) -> blue (prep)
  // remaining at/below prepWithinSec, down to -lateAfterSec -> green (arriving)
  lateAfterSec:     10 * 60, // this many seconds PAST appt -> orange (late)
  noShowAfterSec:   20 * 60, // this many seconds PAST appt -> red (no-show)
};

const ALL_LEVEL_CLASSES = [
  "lvl-green", "lvl-blue", "lvl-yellow", "lvl-orange", "lvl-red", "lvl-neutral",
];

/* Fixed card height (px on the 1920x1080 canvas). Cards always render at this
   size — never squished. If a panel has more than fit, the extra (least urgent)
   ones are held back and shown as a "+N more waiting" chip; they appear as the
   urgent ones at the top get handled and drop off. */
const CARD_ROW_PX = 116;

/* Fallbacks — overridden at runtime by /board/config. */
const CONFIG = {
  pollSeconds: 15, // re-poll the feed (also set via BOARD_POLL_SECONDS)
  staleSeconds: 90, // no successful poll within this => "connection lost"
  feedUrl: "/board/feed",
  configUrl: "/board/config",
  storeName: "Lead & Appointment Board",
};

/* Reset the inquiry "waiting" clock to 0 at store-open each day, so leads that
   arrived after hours (handled by the AI overnight) don't show a huge wait when
   the team walks in. Every lead in the panel counts from the later of its
   received time and today's open time. Set RESET_AT_OPEN = false to count from
   the true received time instead. Hours are local; tune freely (0 = Sunday). */
const RESET_AT_OPEN = true;
const OPEN_HOUR_BY_DAY = { 0: 13, 1: 11, 2: 11, 3: 11, 4: 11, 5: 11, 6: 11 };

/** Today's store-open time (ms), by local weekday. */
function openTimeMs() {
  const d = new Date();
  const hour = OPEN_HOUR_BY_DAY[d.getDay()] ?? 11;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), hour, 0, 0, 0).getTime();
}

/* --------------------------------------------------------------- utilities */

const $ = (sel) => document.querySelector(sel);
const now = () => Date.now();

function levelFor(ageSeconds, table) {
  for (const band of table) if (ageSeconds < band.maxSeconds) return band.level;
  return table[table.length - 1].level;
}

/** Countdown -> {level, rank} for an appointment, `remaining` in seconds. */
function appointmentLevel(remaining) {
  const T = APPOINTMENT_THRESHOLDS;
  if (remaining > T.neutralBeyondSec) return { level: "neutral", rank: 4 };
  if (remaining > T.prepWithinSec) return { level: "blue", rank: 3 };     // prep
  if (-remaining < T.lateAfterSec) return { level: "green", rank: 2 };    // arriving
  if (-remaining < T.noShowAfterSec) return { level: "orange", rank: 1 }; // late
  return { level: "red", rank: 0 };                                       // no-show
}

/** MM:SS under an hour, then H:MM. */
function fmtTimer(ageSeconds) {
  const s = Math.max(0, Math.floor(ageSeconds));
  const h = Math.floor(s / 3600);
  if (h > 0) return `${h}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Countdown body like "45:00" or "2:40" (no "in"/"late" prefix). */
function fmtCountBody(sec) {
  const s = Math.abs(Math.floor(sec));
  if (s >= 3600) return `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function fmtClock(ms) {
  return new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function dayKey(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function parseMs(iso) {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? now() : t;
}

/* ------------------------------------------------------------------- chime */
const Chime = {
  on: false, ctx: null,
  enable() {
    this.on = true;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (this.ctx.state === "suspended") this.ctx.resume();
    } catch (_) { /* silent if unavailable */ }
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
      osc.start(start); osc.stop(start + 0.18);
    });
  },
};

/* -------------------------------------------------------------- feed/state */

/* Per-panel registry: id -> { el, sortMs, level }. */
const panels = {
  leads: { root: $("#leads"), items: new Map(), levels: INQUIRY_LEVELS, kind: "lead" },
  appts: { root: $("#appts"), items: new Map(), levels: null, kind: "appt" },
};

let lastOkMs = now();
let hasLoaded = false;

/* -------------------------------------------------------------- rendering */

function leadCardHTML(d) {
  return `
    <div class="card-line1">
      <span class="card-name">${esc(d.name)}</span>
      <span class="badge">${esc(d.source || "—")}</span>
      <span class="card-timer">--:--</span>
    </div>
    <div class="card-line2">
      <span class="meta rep"></span>
      <span class="sep sep-int" hidden>·</span>
      <span class="meta interest"></span>
    </div>`;
}

function apptCardHTML(d, appointmentMs) {
  return `
    <div class="card-line1">
      <span class="card-name">${esc(d.name)}</span>
      <span class="card-timer appt-time">${esc(fmtClock(appointmentMs))}</span>
    </div>
    <div class="card-line2">
      <span class="meta countdown"></span>
      <span class="sep sep-int" hidden>·</span>
      <span class="meta interest"></span>
      <span class="sep sep-assoc" hidden>·</span>
      <span class="meta assoc"></span>
    </div>`;
}

/** Set an assignee <span>, applying the red "alert" style when empty. */
function setAssignee(el, sel, value, emptyLabel) {
  const a = el.querySelector(sel);
  if (value) { a.textContent = value; a.classList.remove("alert"); }
  else { a.textContent = emptyLabel; a.classList.add("alert"); }
}

function refreshCardFields(entry, d, kind) {
  const el = entry.el;
  if (kind === "lead") {
    el.querySelector(".card-name").textContent = d.name ?? "";
    el.querySelector(".badge").textContent = d.source || "—";
    setAssignee(el, ".rep", d.assignedTo, "UNASSIGNED");
    // Show the puppy/breed interest only when the feed provides one.
    const interest = (d.interest || "").trim();
    el.querySelector(".interest").textContent = interest;
    el.querySelector(".interest").style.display = interest ? "" : "none";
    el.querySelector(".sep-int").hidden = !interest;
  } else {
    el.querySelector(".card-name").textContent = d.name ?? "";
    el.querySelector(".appt-time").textContent = fmtClock(entry.sortMs);
    // Show interest and associate only when present — no "—", no "NO ASSOCIATE".
    const interest = (d.interest || "").trim();
    el.querySelector(".interest").textContent = interest;
    el.querySelector(".interest").style.display = interest ? "" : "none";
    el.querySelector(".sep-int").hidden = !interest;
    const assoc = (d.assignedTo || "").trim();
    el.querySelector(".assoc").textContent = assoc;
    el.querySelector(".assoc").style.display = assoc ? "" : "none";
    el.querySelector(".sep-assoc").hidden = !assoc;
    el.classList.toggle("unconfirmed", !d.confirmed);
  }
}

function refMs(d, kind) {
  return parseMs(kind === "appt" ? d.appointmentAt : d.receivedAt);
}

function syncPanel(panel, list) {
  const incoming = new Map((list || []).map((d) => [String(d.id), d]));

  for (const [id, entry] of panel.items) {
    if (!incoming.has(id)) {
      const el = entry.el;
      el.classList.add("leaving");
      panel.items.delete(id);
      setTimeout(() => el.remove(), 520);
    }
  }

  for (const [id, d] of incoming) {
    const sortMs = refMs(d, panel.kind);
    let entry = panel.items.get(id);
    if (!entry) {
      const el = document.createElement("div");
      el.className = "card flash";
      if (panel.kind === "appt" && !d.confirmed) el.classList.add("unconfirmed");
      el.innerHTML = panel.kind === "lead" ? leadCardHTML(d) : apptCardHTML(d, sortMs);
      setTimeout(() => el.classList.remove("flash"), 1300);
      entry = { el, sortMs };
      panel.items.set(id, entry);
      panel.root.appendChild(el);
      refreshCardFields(entry, d, panel.kind);
    } else {
      entry.sortMs = sortMs;
      refreshCardFields(entry, d, panel.kind);
    }
  }

  updatePanelTimers(panel); // paint colors/text before we sort by color
  reorder(panel);
  layoutRows(panel);
}

/** Sort by urgency color, not time alone.
    Inquiries: longest wait first (oldest receivedAt).
    Appointments: no-show → late → arriving → prep → later, then by time. */
function reorder(panel) {
  const t = now();
  const entries = [...panel.items.values()];
  if (panel.kind === "lead") {
    entries.sort((a, b) => a.sortMs - b.sortMs);
  } else {
    const rank = (e) => appointmentLevel((e.sortMs - t) / 1000).rank;
    entries.sort((a, b) => rank(a) - rank(b) || a.sortMs - b.sortMs);
  }
  // Only touch the DOM when the order actually changed — re-appending every
  // tick is what caused the flicker.
  const current = [...panel.root.querySelectorAll(".card:not(.leaving)")];
  const desired = entries.map((e) => e.el);
  let same = current.length === desired.length;
  for (let i = 0; same && i < desired.length; i++) {
    if (current[i] !== desired[i]) same = false;
  }
  if (same) return;
  desired.forEach((e) => panel.root.appendChild(e));
  const chip = panel.root.querySelector(".overflow-chip");
  if (chip) panel.root.appendChild(chip); // keep the "+N" chip last
}

/** Rows = card count, so cards share the panel height evenly (never overflow). */
function layoutRows(panel) {
  const root = panel.root;
  root.querySelectorAll(".overflow-chip, .empty").forEach((n) => n.remove());
  const cards = [...root.querySelectorAll(".card:not(.leaving)")];

  if (cards.length === 0) {
    root.style.gridTemplateRows = "1fr";
    root.style.gridAutoRows = "";
    root.appendChild(emptyState(panel.kind));
    return;
  }

  // Fixed-height rows: cards never squish.
  root.style.gridTemplateRows = "none";
  root.style.gridAutoRows = CARD_ROW_PX + "px";
  cards.forEach((c) => (c.style.display = ""));

  // How many fit at full size? Hide the rest (least urgent, at the bottom).
  const GAP = 14;
  const fit = Math.max(1, Math.floor((root.clientHeight + GAP) / (CARD_ROW_PX + GAP)));
  if (cards.length > fit) {
    const showN = Math.max(1, fit - 1); // reserve a row for the chip
    cards.forEach((c, i) => (c.style.display = i < showN ? "" : "none"));
    const chip = document.createElement("div");
    chip.className = "overflow-chip";
    chip.textContent = `+${cards.length - showN} more waiting`;
    root.appendChild(chip);
  }
}

function applyLevel(entry, level) {
  if (level === entry.level) return;
  const prev = entry.level;
  entry.el.classList.remove(...ALL_LEVEL_CLASSES);
  entry.el.classList.add("lvl-" + level);
  entry.level = level;
  if (level === "red" && prev && prev !== "red") Chime.play();
}

function updatePanelTimers(panel) {
  const t = now();
  for (const entry of panel.items.values()) {
    if (entry.el.classList.contains("leaving")) continue;
    if (panel.kind === "appt") {
      const remaining = (entry.sortMs - t) / 1000;
      const cd = entry.el.querySelector(".countdown");
      if (remaining >= 0) {
        cd.textContent = `in ${fmtCountBody(remaining)}`;
        cd.classList.remove("alert");
      } else {
        cd.textContent = `${fmtCountBody(remaining)} late`;
        cd.classList.add("alert");
      }
      applyLevel(entry, appointmentLevel(remaining).level);
    } else {
      // Count from the later of received time and today's store-open time,
      // so overnight/after-hours leads reset to 0 when the day starts.
      const startMs = RESET_AT_OPEN ? Math.max(entry.sortMs, openTimeMs()) : entry.sortMs;
      const ageSec = Math.max(0, (t - startMs) / 1000);
      entry.el.querySelector(".card-timer").textContent = fmtTimer(ageSec);
      applyLevel(entry, levelFor(ageSec, panel.levels));
    }
  }
}

function emptyState(kind) {
  const el = document.createElement("div");
  el.className = "empty";
  if (!hasLoaded) {
    el.innerHTML = `<div class="em-ic">📡</div>
      <div class="em-title" style="color:var(--ink-soft)">Connecting…</div>
      <div class="em-sub">Waiting for the first update</div>`;
    return el;
  }
  const copy = kind === "lead"
    ? ["✅", "All caught up", "No leads awaiting a callback"]
    : ["📅", "Nothing booked", "No more appointments today"];
  el.innerHTML = `<div class="em-ic">${copy[0]}</div>
    <div class="em-title">${copy[1]}</div>
    <div class="em-sub">${copy[2]}</div>`;
  return el;
}

/* ------------------------------------------------------------- header/stats */

function updateHeaderCounts(data, apptsTodayCount) {
  const awaiting = (data.inquiries || []).length;
  const total = data.stats && Number.isFinite(data.stats.inquiriesToday)
    ? data.stats.inquiriesToday : awaiting;
  $("#count-awaiting").textContent = awaiting;
  $("#count-appts").textContent = apptsTodayCount;
  $("#count-total").textContent = total;
  $("#panel-leads-count").textContent = awaiting;
  $("#panel-appts-count").textContent = apptsTodayCount;
}

function updateTomorrowChip(n) {
  const chip = $("#appts-tomorrow");
  chip.hidden = n <= 0;
  chip.textContent = `Tomorrow: ${n}`;
}

function updateClock() {
  $("#clock").textContent = new Date().toLocaleTimeString([], {
    hour: "numeric", minute: "2-digit",
  });
}

function updateStale() {
  $("#stale").hidden = now() - lastOkMs <= CONFIG.staleSeconds * 1000;
}

/* --------------------------------------------------------------- lifecycle */

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
    updateHeaderCounts(data, today.length);
    updateTomorrowChip(tomorrow);
    updateStale();
  } catch (err) {
    console.warn("Feed poll failed:", err.message);
    updateStale();
  }
}

/** One-second heartbeat: timers, countdowns, re-sort by color, clock, stale. */
function tick() {
  updatePanelTimers(panels.leads);
  updatePanelTimers(panels.appts);
  reorder(panels.appts); // appointment urgency order shifts as the clock moves
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
  } catch (_) { /* defaults */ }
  $("#store-name").textContent = CONFIG.storeName;
  document.title = CONFIG.storeName + " — Board";
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

/** Scale the fixed 1920x1080 canvas to fit the display, centered. */
function fitStage() {
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  document.getElementById("stage").style.setProperty("--scale", s);
}

async function main() {
  fitStage();
  window.addEventListener("resize", fitStage);
  wireChimeToggle();
  updateClock();
  layoutRows(panels.leads);
  layoutRows(panels.appts);

  await loadConfig();
  await poll();

  setInterval(poll, CONFIG.pollSeconds * 1000);
  setInterval(tick, 1000);
}

main();
