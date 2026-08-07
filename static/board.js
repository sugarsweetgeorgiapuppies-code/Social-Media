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
const CARD_ROW_PX = 100;

/* Friendly avatar colors, picked per name for a bit of life. */
const AVATAR_COLORS = [
  "#6C8EF5", "#F2789F", "#3FB6A8", "#F5A65B", "#9B8CFF", "#5BC0EB", "#EC6A88",
];
/* Little icons for the inquiry source. Unknown sources get a neutral dot. */
const SOURCE_ICON = {
  "web form": "📝", "facebook": "📘", "google": "🔎", "phone": "📞",
  "walk-in": "🚶", "walk in": "🚶", "instagram": "📸", "missed call": "📵",
  "sms": "💬", "email": "✉️", "referral": "🤝", "website": "🌐",
};

function initials(name) {
  const p = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  return (p[0][0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
}
function avatarColor(name) {
  let h = 0;
  for (const c of String(name || "")) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
function sourceLabel(src) {
  const s = String(src || "").trim();
  if (!s) return "";
  return `${SOURCE_ICON[s.toLowerCase()] || "•"} ${s}`;
}

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
  _tone(freqs, gain = 0.25, step = 0.18, dur = 0.16) {
    if (!this.on || !this.ctx) return;
    const t0 = this.ctx.currentTime;
    freqs.forEach((freq, i) => {
      const osc = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = t0 + i * step;
      g.gain.setValueAtTime(0.0001, start);
      g.gain.exponentialRampToValueAtTime(gain, start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
      osc.connect(g).connect(this.ctx.destination);
      osc.start(start); osc.stop(start + dur + 0.02);
    });
  },
  // Descending alert when a card crosses into red.
  play() { this._tone([880, 660]); },
  // Bright rising ding when a new inquiry arrives.
  newInquiry() { this._tone([660, 990], 0.3, 0.14, 0.22); },
  // Playful little pop for the puppy's kick.
  boing() { this._tone([300, 560, 380], 0.26, 0.07, 0.12); },
};

/* --------------------------------------------------------------------- dog */
/* A hand-drawn side-view puppy (SVG) whose legs gallop, ears flop, and tail
   wags — a real little character, not an emoji. It trots along the bottom and,
   when an inquiry is handled, dashes over and punts the card off the screen.
   Disabled automatically when the viewer prefers reduced motion. */
const DOG_SVG = `
<svg class="dogsvg" viewBox="0 0 140 100" width="76" height="54" xmlns="http://www.w3.org/2000/svg">
  <path class="tail" d="M24 50 Q8 44 6 24 Q18 40 30 44 Z" fill="#a86a38"/>
  <rect class="leg leg-bf" x="40" y="60" width="10" height="30" rx="5" fill="#9c6636"/>
  <rect class="leg leg-ff" x="86" y="60" width="10" height="30" rx="5" fill="#9c6636"/>
  <ellipse cx="60" cy="54" rx="42" ry="22" fill="#c88a52"/>
  <ellipse cx="62" cy="62" rx="32" ry="12" fill="#ddb083"/>
  <rect class="leg leg-bn" x="47" y="62" width="11" height="30" rx="5.5" fill="#b8794c"/>
  <rect class="leg leg-fn" x="92" y="62" width="11" height="30" rx="5.5" fill="#b8794c"/>
  <circle cx="104" cy="46" r="21" fill="#c88a52"/>
  <rect x="118" y="47" width="21" height="15" rx="7.5" fill="#eccea6"/>
  <circle cx="137" cy="54" r="3.6" fill="#33261f"/>
  <ellipse class="ear" cx="92" cy="36" rx="9" ry="16" fill="#a86a38"/>
  <circle cx="109" cy="43" r="3" fill="#2a201c"/>
</svg>`;

const Dog = {
  enabled: true,
  el: null, face: null, emo: null,
  x: 150, y: 992, tx: 150, ty: 992, facing: 1,
  speed: 1100, busy: false, queue: [], arrive: null, lastT: 0, nextRoam: 0,

  // Idle tricks the pup performs at random. Each is a CSS class + duration.
  TRICKS: [
    { cls: "t-hop", ms: 620 },      // happy hop
    { cls: "t-flip", ms: 820 },     // backflip
    { cls: "t-roll", ms: 900 },     // roll over
    { cls: "t-shake", ms: 720 },    // shake it off
    { cls: "t-stretch", ms: 1000 }, // play-bow stretch
    { cls: "t-sniff", ms: 1200 },   // sniff the ground
    { cls: "bark", ms: 820, bark: true }, // "Woof!" bubble
  ],

  init() {
    try {
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) { this.enabled = false; return; }
    } catch (_) { /* keep enabled */ }
    const stage = document.getElementById("stage");
    this.el = document.createElement("div");
    this.el.className = "dog";
    this.face = document.createElement("div");
    this.face.className = "dog-face";
    this.emo = document.createElement("div");
    this.emo.className = "dog-emo";
    this.emo.innerHTML = DOG_SVG;
    this.face.appendChild(this.emo);
    this.el.appendChild(this.face);
    stage.appendChild(this.el);
    this.place();
    const loop = (t) => { this.step(t); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  },

  place() { this.el.style.transform = `translate(${this.x}px, ${this.y}px)`; },

  /** Queue a card to be punted; `done` removes it once the pup connects. */
  kick(cardEl, done) {
    if (!this.enabled) { done(); return; }
    this.queue.push({ cardEl, done });
  },

  step(t) {
    const dt = this.lastT ? Math.min(0.05, (t - this.lastT) / 1000) : 0;
    this.lastT = t;
    const dx = this.tx - this.x, dy = this.ty - this.y;
    const dist = Math.hypot(dx, dy);

    if (dist <= 2 && !this.arrive && !this.busy) {
      if (this.queue.length) {
        this.beginKick(this.queue.shift());
      } else if (t > this.nextRoam) {
        // When settled, either wander to a fresh clear spot or do a trick.
        if (Math.random() < 0.5) {
          this.doTrick();
        } else {
          const sp = this.safeSpot();
          this.tx = sp.x; this.ty = sp.y;
        }
        this.nextRoam = t + 4500 + Math.random() * 7000;
      }
    }

    if (dist > 2) {
      this.facing = dx < 0 ? -1 : 1;
      this.face.style.transform = `scaleX(${this.facing})`;
      const step = Math.min(dist, this.speed * dt);
      this.x += (dx / dist) * step;
      this.y += (dy / dist) * step;
      this.emo.classList.add("running");
    } else {
      this.emo.classList.remove("running");
      if (this.arrive) { const cb = this.arrive; this.arrive = null; cb(); }
    }
    this.place();
  },

  beginKick(job) {
    this.busy = true;
    const stage = document.getElementById("stage");
    const s = parseFloat(getComputedStyle(stage).getPropertyValue("--scale")) || 1;
    const cr = job.cardEl.getBoundingClientRect();
    const sr = stage.getBoundingClientRect();
    const cx = (cr.left - sr.left) / s;
    const cy = (cr.top - sr.top) / s;
    const ch = cr.height / s;
    this.tx = cx - 56;
    this.ty = cy + ch - 54;
    this.arrive = () => {
      this.emo.classList.add("kicking");
      job.cardEl.classList.add("kicked");
      if (Chime.on) Chime.boing();
      // little puff of dust where the kick lands
      const puff = document.createElement("div");
      puff.className = "puff";
      puff.textContent = "💨";
      puff.style.left = (cx + 20) + "px";
      puff.style.top = (cy + ch / 2 - 20) + "px";
      stage.appendChild(puff);
      setTimeout(() => puff.remove(), 750);
      setTimeout(() => this.emo.classList.remove("kicking"), 360);
      setTimeout(() => {
        job.done();
        this.busy = false;
        this.nextRoam = this.lastT + 4000;
      }, 680);
    };
  },

  /** Convert an element's rect into stage-space coordinates. */
  _toStage(rect, sr, s) {
    return {
      x: (rect.left - sr.left) / s, y: (rect.top - sr.top) / s,
      w: rect.width / s, h: rect.height / s,
      right: (rect.right - sr.left) / s, bottom: (rect.bottom - sr.top) / s,
    };
  },

  /** A resting spot in the empty area BELOW the cards — never on top of one. */
  safeSpot() {
    const stage = document.getElementById("stage");
    const s = parseFloat(getComputedStyle(stage).getPropertyValue("--scale")) || 1;
    const sr = stage.getBoundingClientRect();
    const spots = [];
    for (const sel of [".panel-leads", ".panel-appts"]) {
      const pl = document.querySelector(sel);
      if (!pl) continue;
      const pr = this._toStage(pl.getBoundingClientRect(), sr, s);
      const cards = [...pl.querySelectorAll(".cards .card:not(.leaving):not(.kicked)")];
      let topFree = pr.y + 96; // below the panel title
      if (cards.length) {
        topFree = this._toStage(cards[cards.length - 1].getBoundingClientRect(), sr, s).bottom + 22;
      }
      const bottomLimit = pr.bottom - 66;
      if (bottomLimit - topFree > 60) {
        spots.push({
          x: pr.x + 44 + Math.random() * Math.max(40, pr.w - 170),
          y: topFree + Math.random() * (bottomLimit - topFree - 8),
          room: bottomLimit - topFree,
        });
      }
    }
    if (spots.length) return spots[Math.floor(Math.random() * spots.length)];
    return { x: 150 + Math.random() * 1500, y: 1024 }; // both panels full: bottom strip
  },

  /** If the pup is sitting on top of a card, scamper to a clear spot. */
  avoid() {
    if (!this.enabled || this.busy) return;
    const stage = document.getElementById("stage");
    const s = parseFloat(getComputedStyle(stage).getPropertyValue("--scale")) || 1;
    const sr = stage.getBoundingClientRect();
    const d = { left: this.x, top: this.y, right: this.x + 76, bottom: this.y + 54 };
    for (const c of document.querySelectorAll(".cards .card:not(.leaving):not(.kicked)")) {
      const r = this._toStage(c.getBoundingClientRect(), sr, s);
      if (d.left < r.right && d.right < r.right + r.w && d.right > r.x &&
          d.top < r.bottom && d.bottom > r.y) {
        const sp = this.safeSpot();
        this.tx = sp.x; this.ty = sp.y;
        this.nextRoam = this.lastT + 3000;
        return;
      }
    }
  },

  /** Perform a random trick in place. */
  doTrick() {
    const tr = this.TRICKS[Math.floor(Math.random() * this.TRICKS.length)];
    this.busy = true;
    this.emo.classList.add(tr.cls);
    if (tr.bark) this.bark();
    setTimeout(() => {
      this.emo.classList.remove(tr.cls);
      this.busy = false;
      this.nextRoam = this.lastT + 3500 + Math.random() * 6000;
    }, tr.ms);
  },

  /** A little "Woof!" speech bubble above the pup (no sound). */
  bark() {
    const bub = document.createElement("div");
    bub.className = "woof";
    bub.textContent = "Woof!";
    bub.style.left = (this.x + 40) + "px";
    bub.style.top = (this.y - 22) + "px";
    document.getElementById("stage").appendChild(bub);
    setTimeout(() => bub.remove(), 900);
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
let seededOnce = false; // true after the first poll, so we don't ding on load
let tomorrowCount = 0; // shown in the appointments empty state / header chip

/* -------------------------------------------------------------- rendering */

function leadCardHTML() {
  return `
    <div class="avatar"></div>
    <div class="cmain">
      <div class="card-name"></div>
      <div class="card-sub"><span class="meta src"></span></div>
    </div>
    <div class="card-timer">--:--</div>`;
}

function apptCardHTML() {
  return `
    <div class="avatar"></div>
    <div class="cmain">
      <div class="card-name"></div>
      <div class="card-sub">
        <span class="meta countdown"></span>
        <span class="sep sep-int" hidden>·</span>
        <span class="meta interest"></span>
      </div>
    </div>
    <div class="card-timer appt-time"></div>`;
}

/** Toggle a metadata span + its leading separator based on whether it has text. */
function setMeta(el, sel, sepSel, value) {
  const m = el.querySelector(sel);
  m.textContent = value || "";
  m.style.display = value ? "" : "none";
  if (sepSel) el.querySelector(sepSel).hidden = !value;
}

function refreshCardFields(entry, d, kind) {
  const el = entry.el;
  const name = d.name ?? "";
  el.querySelector(".card-name").textContent = name;
  const av = el.querySelector(".avatar");
  av.textContent = initials(name);
  av.style.background = avatarColor(name);

  if (kind === "lead") {
    setMeta(el, ".src", null, sourceLabel(d.source));
  } else {
    el.querySelector(".appt-time").textContent = fmtClock(entry.sortMs);
    setMeta(el, ".interest", ".sep-int", (d.interest || "").trim());
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
      panel.items.delete(id);
      // A handled inquiry gets punted off by the pup; everything else fades.
      if (panel.kind === "lead" && seededOnce && Dog.enabled) {
        el.classList.add("awaiting-kick");
        Dog.kick(el, () => { el.remove(); reorder(panel); layoutRows(panel); });
      } else {
        el.classList.add("leaving");
        setTimeout(() => el.remove(), 520);
      }
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
      // Ding when a genuinely new inquiry arrives (not on the first load).
      if (seededOnce && panel.kind === "lead") Chime.newInquiry();
    } else {
      entry.sortMs = sortMs;
      refreshCardFields(entry, d, panel.kind);
    }
  }

  updatePanelTimers(panel); // paint colors/text before we sort by color
  reorder(panel);
  layoutRows(panel);
  Dog.avoid(); // if a new card landed on the pup, it scampers clear
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
    el.innerHTML = `<div class="em-ic">⏳</div>
      <div class="em-title">Just a moment</div>
      <div class="em-sub">Loading the latest…</div>`;
    return el;
  }
  let ic, title, sub;
  if (kind === "lead") {
    ic = "✓"; title = "All caught up";
    sub = "No new inquiries need a call right now.";
  } else {
    ic = "📅"; title = "Nothing else today";
    sub = tomorrowCount > 0
      ? `Tomorrow has ${tomorrowCount} appointment${tomorrowCount === 1 ? "" : "s"} scheduled.`
      : "No more appointments on the calendar today.";
  }
  el.innerHTML = `<div class="em-ic">${ic}</div>
    <div class="em-title">${title}</div>
    <div class="em-sub">${sub}</div>`;
  return el;
}

/* ------------------------------------------------------------- header/stats */

/** Set a header counter value + a status dot (calm green → busy red). */
function setCounter(id, chipId, value, bands) {
  $(id).textContent = value;
  const chip = $(chipId);
  chip.classList.remove("good", "warn", "busy");
  chip.classList.add(value >= bands[1] ? "busy" : value >= bands[0] ? "warn" : "good");
}

function updateHeaderCounts(data, apptsTodayCount) {
  const awaiting = (data.inquiries || []).length;
  const total = data.stats && Number.isFinite(data.stats.inquiriesToday)
    ? data.stats.inquiriesToday : awaiting;
  // Only "Awaiting Call" escalates (calm → amber → red); the others stay calm.
  setCounter("#count-awaiting", "#c-awaiting", awaiting, [1, 4]);
  setCounter("#count-appts", "#c-appts", apptsTodayCount, [Infinity, Infinity]);
  setCounter("#count-total", "#c-total", total, [Infinity, Infinity]);
  $("#panel-leads-count").textContent = awaiting;
  $("#panel-appts-count").textContent = apptsTodayCount;
}

function updateTomorrowChip(n) {
  tomorrowCount = n;
  const chip = $("#appts-tomorrow");
  chip.hidden = n <= 0;
  chip.innerHTML = `Tomorrow <b>${n}</b>`;
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
    updateTomorrowChip(tomorrow); // sets tomorrowCount before panels render their empty state
    syncPanel(panels.leads, data.inquiries);
    syncPanel(panels.appts, today);
    updateHeaderCounts(data, today.length);
    updateStale();
    seededOnce = true; // subsequent new inquiries may ding
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
      btn.querySelector(".chime-ic").textContent = "🔇";
    } else {
      Chime.enable();
      btn.setAttribute("aria-pressed", "true");
      btn.querySelector(".chime-ic").textContent = "🔊";
      Chime.newInquiry(); // confirmation ding — also unlocks browser audio
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
  Dog.init();
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
