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
const CARD_ROW_PX = 120;

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

/* Respect the viewer's reduced-motion preference for all the flourishes. */
let MOTION = true;
try { MOTION = !matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (_) {}

/* ------------------------------------------------------- celebration effects */

/** Fling a little burst of paws/confetti outward from a stage point (x,y). */
function celebrate(x, y, count = 14, big = false) {
  if (!MOTION) return;
  const stage = document.getElementById("stage");
  const chars = big ? ["🐾", "🎉", "✨", "💛", "🐶", "⭐"] : ["🐾", "✨", "💛", "🐾"];
  const n = big ? count + 10 : count;
  for (let i = 0; i < n; i++) {
    const p = document.createElement("div");
    p.className = "confetti";
    p.textContent = chars[Math.floor(Math.random() * chars.length)];
    const ang = Math.random() * Math.PI * 2;
    const dist = (big ? 130 : 70) + Math.random() * (big ? 170 : 90);
    p.style.left = x + "px";
    p.style.top = y + "px";
    p.style.setProperty("--dx", Math.cos(ang) * dist + "px");
    p.style.setProperty("--dy", (Math.sin(ang) * dist - 30) + "px");
    p.style.setProperty("--rot", (Math.random() * 720 - 360) + "deg");
    p.style.fontSize = (16 + Math.random() * (big ? 26 : 14)) + "px";
    p.style.animationDelay = (Math.random() * 0.12) + "s";
    stage.appendChild(p);
    setTimeout(() => p.remove(), 1500);
  }
}

/** Big center-screen "🎉 N inquiries today!" toast at a daily milestone. */
function celebrateMilestone(n) {
  celebrate(960, 470, 24, true);
  Dog.cheer();
  const b = document.createElement("div");
  b.className = "cel-banner";
  b.innerHTML = `🎉 <b>${n}</b> inquiries today!`;
  document.getElementById("stage").appendChild(b);
  requestAnimationFrame(() => b.classList.add("show"));
  setTimeout(() => { b.classList.remove("show"); }, 3400);
  setTimeout(() => b.remove(), 4000);
}

/* --------------------------------------------------------- seasonal ambience */
/* A thin layer of drifting particles chosen by the calendar: snow in winter,
   leaves in fall, blossoms in spring, sparkles in summer, plus a few holiday
   surprises. Deliberately sparse so it never competes with the cards. */
const Season = {
  layer: null, timer: null, cfg: null,

  pick() {
    const d = new Date();
    const m = d.getMonth(); // 0=Jan
    const day = d.getDate();
    // Holiday overrides first.
    if (m === 1 && day >= 10 && day <= 15)   // Valentine's week
      return { chars: ["💗", "💕", "🐾"], peak: 0.8 };
    if (m === 9 && day >= 24)                 // Halloween stretch
      return { chars: ["🎃", "🍂", "🦇"], peak: 0.75 };
    if ((m === 11 && day >= 20) || (m === 11 && day <= 26)) // Christmas
      return { chars: ["❄️", "🎄", "⭐"], peak: 0.85 };
    if (m === 6 && day >= 1 && day <= 5)      // 4th of July
      return { chars: ["✨", "⭐", "🎉"], peak: 0.8 };
    // Seasons.
    if (m === 11 || m === 0 || m === 1) return { chars: ["❄️", "❄", "🤍"], peak: 0.85 }; // winter
    if (m >= 2 && m <= 4) return { chars: ["🌸", "🌼", "🌿"], peak: 0.7 };               // spring
    if (m >= 5 && m <= 7) return { chars: ["✨", "🌿", "🐝"], peak: 0.55 };               // summer
    return { chars: ["🍂", "🍁", "🌰"], peak: 0.8 };                                       // fall
  },

  init() {
    if (!MOTION) return;
    this.cfg = this.pick();
    this.layer = document.createElement("div");
    this.layer.className = "season";
    this.layer.setAttribute("aria-hidden", "true");
    const stage = document.getElementById("stage");
    // Insert just after the background orbs so it sits behind the cards.
    const orbs = stage.querySelector(".bg-orbs");
    stage.insertBefore(this.layer, orbs ? orbs.nextSibling : stage.firstChild);
    // A gentle, steady sprinkle.
    this.timer = setInterval(() => this.spawn(), 1300);
    for (let i = 0; i < 4; i++) setTimeout(() => this.spawn(), i * 400);
  },

  spawn() {
    if (!this.layer || this.layer.childElementCount > 16) return;
    const f = document.createElement("div");
    f.className = "flake";
    f.textContent = this.cfg.chars[Math.floor(Math.random() * this.cfg.chars.length)];
    const dur = 10 + Math.random() * 7;
    f.style.left = Math.random() * 1920 + "px";
    f.style.fontSize = (16 + Math.random() * 20) + "px";
    f.style.setProperty("--peak", (this.cfg.peak * (0.6 + Math.random() * 0.4)).toFixed(2));
    f.style.setProperty("--sway", (Math.random() * 120 - 60) + "px");
    f.style.setProperty("--spin", (Math.random() * 260 - 130) + "deg");
    f.style.animationDuration = dur + "s";
    this.layer.appendChild(f);
    setTimeout(() => f.remove(), dur * 1000 + 200);
  },
};

/* ----------------------------------------------------- screen burn-in guard */
/* Nudge the whole canvas a few pixels every 90s. Invisible to the eye but it
   keeps the static header/panels from ghosting into an always-on TV panel. */
function antiBurnIn() {
  const offs = [[0, 0], [5, 3], [7, -3], [3, 6], [-4, 4], [-6, -3], [-3, -6], [4, -5]];
  let i = 0;
  const stage = document.getElementById("stage");
  // Enable the smooth drift only now (after the initial fit) so the board
  // never animates its scale into place on load.
  stage.style.transition = "transform 3s ease";
  setInterval(() => {
    i = (i + 1) % offs.length;
    stage.style.setProperty("--sx", offs[i][0] + "px");
    stage.style.setProperty("--sy", offs[i][1] + "px");
  }, 90000);
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
<svg class="dogsvg" viewBox="0 0 158 120" width="124" height="94" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="dgBody" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f2dab0"/><stop offset="1" stop-color="#d6b284"/>
    </linearGradient>
    <linearGradient id="dgLeg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#e6c495"/><stop offset="1" stop-color="#bd9463"/>
    </linearGradient>
    <radialGradient id="dgHead" cx="0.58" cy="0.4" r="0.9">
      <stop offset="0" stop-color="#f4deb6"/><stop offset="1" stop-color="#d6b284"/>
    </radialGradient>
  </defs>
  <!-- tail with a fluffy pom -->
  <g class="tail">
    <path d="M30 58 Q20 52 18 42" stroke="#cba774" stroke-width="6" fill="none" stroke-linecap="round"/>
    <circle cx="15" cy="34" r="11" fill="#eed9b2"/><circle cx="9" cy="40" r="7" fill="#eed9b2"/>
    <circle cx="22" cy="40" r="7" fill="#eed9b2"/><circle cx="14" cy="46" r="6" fill="#eed9b2"/>
  </g>
  <!-- far legs with pom feet -->
  <path class="leg leg-bf" d="M45 66 L51 66 L51 83 A8 8 0 1 1 45 83 Z" fill="#c39c6a"/>
  <path class="leg leg-ff" d="M88 66 L94 66 L94 83 A8 8 0 1 1 88 83 Z" fill="#c39c6a"/>
  <!-- fluffy body -->
  <ellipse cx="64" cy="58" rx="40" ry="21" fill="url(#dgBody)"/>
  <g fill="#eed9b2">
    <circle cx="34" cy="50" r="12"/><circle cx="48" cy="40" r="13"/><circle cx="66" cy="37" r="14"/>
    <circle cx="84" cy="42" r="12"/><circle cx="95" cy="52" r="11"/>
    <circle cx="40" cy="66" r="11"/><circle cx="58" cy="70" r="12"/><circle cx="78" cy="66" r="11"/>
  </g>
  <ellipse cx="64" cy="56" rx="30" ry="13" fill="url(#dgBody)"/>
  <!-- near legs with pom feet -->
  <path class="leg leg-bn" d="M53 68 L60 68 L60 85 A9 9 0 1 1 53 85 Z" fill="url(#dgLeg)"/>
  <path class="leg leg-fn" d="M96 68 L103 68 L103 85 A9 9 0 1 1 96 85 Z" fill="url(#dgLeg)"/>
  <!-- collar -->
  <path d="M92 36 Q90 52 97 64" stroke="#d98fb0" stroke-width="8" fill="none" stroke-linecap="round"/>
  <!-- fluffy topknot head -->
  <circle cx="110" cy="48" r="19" fill="url(#dgHead)"/>
  <g fill="#eed9b2">
    <circle cx="96" cy="40" r="10"/><circle cx="104" cy="31" r="11"/><circle cx="117" cy="31" r="11"/>
    <circle cx="126" cy="42" r="10"/><circle cx="123" cy="55" r="9"/><circle cx="108" cy="34" r="10"/>
  </g>
  <circle cx="110" cy="48" r="14" fill="url(#dgHead)"/>
  <!-- floppy fluffy ear -->
  <g class="ear">
    <circle cx="93" cy="46" r="9" fill="#d8b57f"/><circle cx="89" cy="58" r="8" fill="#d8b57f"/>
    <circle cx="92" cy="68" r="7" fill="#d8b57f"/>
  </g>
  <!-- slim shaved muzzle -->
  <ellipse cx="132" cy="56" rx="14" ry="10" fill="#e4c491"/>
  <path d="M125 61 Q133 67 142 60" stroke="#6b4a2e" stroke-width="1.7" fill="none" stroke-linecap="round"/>
  <ellipse cx="145" cy="52" rx="4.6" ry="3.9" fill="#2f231d"/>
  <circle cx="143.4" cy="50.5" r="1.3" fill="#7a6355"/>
  <path d="M110 38 Q115 35.5 120 38" stroke="#c9a06a" stroke-width="2" fill="none" stroke-linecap="round"/>
  <ellipse cx="116" cy="47" rx="3.4" ry="4.1" fill="#241c18"/>
  <circle cx="117.3" cy="45.4" r="1.3" fill="#ffffff"/>
  <!-- collar tag -->
  <circle cx="94" cy="64" r="5" fill="#ecc24a" stroke="#c39a22" stroke-width="1.3"/>
</svg>`;

/* Curled-up sleeping poodle (solid fills so it needs no shared <defs>). */
const DOG_SLEEP_SVG = `
<svg class="dogsvg" viewBox="0 0 150 92" width="124" height="76" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="78" cy="80" rx="58" ry="10" fill="#2b302b" opacity="0.08"/>
  <g fill="#eed9b2">
    <circle cx="74" cy="58" r="26"/><circle cx="48" cy="60" r="19"/><circle cx="100" cy="58" r="20"/>
    <circle cx="62" cy="44" r="16"/><circle cx="88" cy="44" r="16"/><circle cx="76" cy="38" r="15"/>
    <circle cx="114" cy="62" r="13"/>
  </g>
  <ellipse cx="76" cy="62" rx="44" ry="18" fill="#ddbd8f"/>
  <circle cx="46" cy="62" r="18" fill="#e6c592"/>
  <g fill="#eed9b2"><circle cx="36" cy="54" r="10"/><circle cx="48" cy="50" r="10"/><circle cx="58" cy="56" r="9"/></g>
  <circle cx="46" cy="62" r="13" fill="#e6c592"/>
  <ellipse cx="30" cy="68" rx="13" ry="8.5" fill="#e4c491"/>
  <circle cx="19" cy="68" r="3.7" fill="#2f231d"/>
  <path d="M39 63 q4.5 3.5 9 0" stroke="#3a2c22" stroke-width="1.9" fill="none" stroke-linecap="round"/>
  <path d="M52 52 q11 -5 15 7 q-7 5 -15 1 z" fill="#d3ac7a"/>
  <circle cx="58" cy="70" r="4.6" fill="#ecc24a" stroke="#c39a22" stroke-width="1.2"/>
</svg>`;

const Dog = {
  enabled: true,
  el: null, face: null, emo: null, sleeping: false, _zzz: null,
  W: 124, H: 94, // on-canvas footprint (matches the SVG size)
  homeX: 1711, homeY: 986, // nestled inside the dog house (bottom-right floor)
  x: 1711, y: 986, tx: 1711, ty: 986, facing: 1,
  speed: 1200, busy: false, queue: [], arrive: null, lastT: 0, nextRoam: 0,
  _lastConcern: 0, // throttles the "trot over to a red card" reaction

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

  /** Queue a card to be punted; `done` removes it once the pup connects.
      `meta.fast` (answered before it turned orange) => a bigger celebration. */
  kick(cardEl, done, meta = {}) {
    if (!this.enabled) { done(); return; }
    this.queue.push({ type: "kick", cardEl, done, fast: !!meta.fast });
  },

  /** Trot over and look concerned at a card that just turned red. Throttled,
      and never interrupts a punt in progress. */
  concern(cardEl) {
    if (!this.enabled || this.busy || this.queue.length || this.arrive) return;
    if (this.lastT - this._lastConcern < 25000) return;
    this._lastConcern = this.lastT;
    this.queue.push({ type: "concern", cardEl });
  },

  /** A quick happy double-hop (used on fast answers + milestones). */
  cheer() {
    if (!this.emo) return;
    this.emo.classList.remove("t-hop");
    void this.emo.offsetWidth; // restart the animation
    this.emo.classList.add("t-hop");
    setTimeout(() => this.emo.classList.remove("t-hop"), 640);
  },

  step(t) {
    const dt = this.lastT ? Math.min(0.05, (t - this.lastT) / 1000) : 0;
    this.lastT = t;
    const dx = this.tx - this.x, dy = this.ty - this.y;
    const dist = Math.hypot(dx, dy);

    if (dist <= 2 && !this.arrive && !this.busy) {
      if (this.queue.length) {
        this.wake();
        const job = this.queue.shift();
        if (job.type === "concern") this.beginConcern(job);
        else this.beginKick(job);
      } else if (!this.sleeping && t > this.nextRoam) {
        this.tx = this.homeX; this.ty = this.homeY;
        const waiting = document.querySelectorAll(
          "#leads .card:not(.leaving):not(.kicked)").length > 0;
        if (waiting) {
          // People are waiting — stay awake and alert; a trick now and then.
          if (Math.random() < 0.3) this.doTrick();
          this.nextRoam = t + 6000 + Math.random() * 7000;
        } else if (Math.random() < 0.2) {
          this.doTrick();
          this.nextRoam = t + 7000 + Math.random() * 7000;
        } else {
          this.sleep(); // all caught up — nap time
        }
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
    this.tx = cx - this.W * 0.8;
    this.ty = cy + ch - this.H * 0.86;
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
      // A handled lead is a win — celebrate (bigger if answered quickly).
      celebrate(cx + 30, cy + ch / 2, job.fast ? 16 : 8, job.fast);
      if (job.fast) setTimeout(() => this.cheer(), 360);
      setTimeout(() => {
        job.done();
        this.busy = false;
        this.tx = this.homeX; this.ty = this.homeY; // trot back to bed
        this.nextRoam = this.lastT + 4000;
      }, 680);
    };
  },

  /** Trot beside a red card, perk up with a "!" bubble, then head home. */
  beginConcern(job) {
    if (!document.contains(job.cardEl)) { this.busy = false; return; }
    this.busy = true;
    const stage = document.getElementById("stage");
    const s = parseFloat(getComputedStyle(stage).getPropertyValue("--scale")) || 1;
    const cr = job.cardEl.getBoundingClientRect();
    const sr = stage.getBoundingClientRect();
    const cx = (cr.left - sr.left) / s;
    const cy = (cr.top - sr.top) / s;
    const ch = cr.height / s;
    this.tx = cx - this.W * 0.82;
    this.ty = cy + ch - this.H * 0.92;
    this.arrive = () => {
      this.facing = 1;
      this.face.style.transform = "scaleX(1)"; // face the card
      this.alertBubble(this.x + 46, this.y - 18);
      this.emo.classList.add("perk");
      setTimeout(() => this.emo.classList.remove("perk"), 1500);
      setTimeout(() => {
        this.busy = false;
        this.tx = this.homeX; this.ty = this.homeY;
        this.nextRoam = this.lastT + 4000;
      }, 1600);
    };
  },

  /** A red "!" bubble above the pup. */
  alertBubble(x, y) {
    const b = document.createElement("div");
    b.className = "alertbub";
    b.textContent = "!";
    b.style.left = x + "px";
    b.style.top = y + "px";
    document.getElementById("stage").appendChild(b);
    setTimeout(() => b.remove(), 1500);
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
      const bottomLimit = pr.bottom - (this.H + 6);
      if (bottomLimit - topFree > 40) {
        spots.push({
          x: pr.x + 40 + Math.random() * Math.max(30, pr.w - (this.W + 50)),
          y: topFree + Math.random() * (bottomLimit - topFree),
          room: bottomLimit - topFree,
        });
      }
    }
    if (spots.length) return spots[Math.floor(Math.random() * spots.length)];
    return { x: 150 + Math.random() * 1400, y: 1080 - this.H - 26 }; // panels full: bottom strip
  },

  /** If the pup is sitting on top of a card, scamper to a clear spot. */
  avoid() {
    if (!this.enabled || this.busy) return;
    const stage = document.getElementById("stage");
    const s = parseFloat(getComputedStyle(stage).getPropertyValue("--scale")) || 1;
    const sr = stage.getBoundingClientRect();
    const d = { left: this.x, top: this.y, right: this.x + this.W, bottom: this.y + this.H };
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

  /** Curl up and sleep (with floating Zzz) — the idle state. */
  sleep() {
    if (this.sleeping) return;
    this.sleeping = true;
    this.face.style.transform = "scaleX(1)";
    this.emo.classList.remove("running", "kicking");
    this.emo.classList.add("sleeping");
    this.emo.innerHTML = DOG_SLEEP_SVG;
    const z = document.createElement("div");
    z.className = "zzz";
    z.textContent = "z Z z";
    z.style.left = (this.x + 22) + "px";
    z.style.top = (this.y - 6) + "px";
    document.getElementById("stage").appendChild(z);
    this._zzz = z;
  },

  /** Wake up and stand back on all fours. */
  wake() {
    if (!this.sleeping) return;
    this.sleeping = false;
    this.emo.classList.remove("sleeping");
    this.emo.innerHTML = DOG_SVG;
    if (this._zzz) { this._zzz.remove(); this._zzz = null; }
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
        // "Fast" = answered before it turned orange (still green/yellow).
        const fast = !entry.level || entry.level === "green" || entry.level === "yellow";
        el.classList.add("awaiting-kick");
        Dog.kick(el, () => { el.remove(); reorder(panel); layoutRows(panel); }, { fast });
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
      // A new inquiry means someone's waiting — wake the pup up.
      if (panel.kind === "lead") {
        Dog.wake();
        if (seededOnce) Chime.newInquiry();
      }
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
  if (level === "red" && prev && prev !== "red") {
    Chime.play();
    // Pup notices a lead that's now waiting too long and trots over to nudge.
    if (entry.el.closest("#leads")) Dog.concern(entry.el);
  }
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

/* Daily-total milestones worth a little party. milestoneMark tracks the
   highest one already reached; it's seeded on the first poll (so we never
   celebrate a number the board simply loaded into). */
const MILESTONES = [10, 25, 50, 75, 100, 150, 200, 300];
let milestoneMark = -1;

function checkMilestone(total) {
  const reached = MILESTONES.filter((m) => total >= m).length - 1;
  if (milestoneMark < 0) { milestoneMark = reached; return; } // seed, no party
  if (reached > milestoneMark) {
    milestoneMark = reached;
    celebrateMilestone(MILESTONES[reached]);
  }
}

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
  checkMilestone(total);
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
  Season.init();
  antiBurnIn();
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
