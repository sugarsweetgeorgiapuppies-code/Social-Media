/* Sugar Sweet Georgia Puppies — Phil's filming hub (today + this week) */
"use strict";

/* ------------------------------------------------------------------ API */
const api = {
  get: (p) => fetch(p).then(j),
  post: (p, b) => fetch(p, { method: "POST", headers: H, body: b ? JSON.stringify(b) : undefined }).then(j),
  patch: (p, b) => fetch(p, { method: "PATCH", headers: H, body: JSON.stringify(b) }).then(j),
  put: (p, b) => fetch(p, { method: "PUT", headers: H, body: JSON.stringify(b) }).then(j),
};
const H = { "Content-Type": "application/json" };
async function j(r) { if (!r.ok) throw new Error((await r.text()) || r.statusText); return r.json(); }

/* --------------------------------------------------------------- helpers */
const $ = (s, r = document) => r.querySelector(s);
const el = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstElementChild; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const nl = (s) => esc(s).replace(/\n/g, "<br>");
const view = $("#view");
let CURRENT = "today", BRIEFING_EXISTS = false;

let TT;
function toast(m) { const t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(TT); TT = setTimeout(() => (t.hidden = true), 2600); }

/* Small inline line-icons (no emoji). */
function ico(paths, w = 2) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}
const ICONS = {
  record: ico('<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>', 1.8),
  publish: ico('<path d="M22 2 11 13M22 2l-7 20-4-9-9-4Z"/>', 1.8),
  chevron: ico('<path d="M9 6l6 6-6 6"/>'),
};

const FORMAT_LABEL = {
  puppy_focus: "Puppy on screen", voiceover: "Voiceover", talking_head: "Talking to camera",
  skit: "Mini skit", text_only: "Text only",
};
const FORMATS = Object.keys(FORMAT_LABEL);
const fmtLabel = (f) => FORMAT_LABEL[f] || f;

/* ---------------------------------------------------------- status bar */
async function loadStatus() {
  try {
    const s = await api.get("/api/status");
    const pill = $("#mode-pill");
    if (s.ai_enabled) { pill.textContent = "Live research"; pill.className = "pill live dot"; pill.title = "Using live web research (" + s.model + ")"; }
    else { pill.textContent = "Starter ideas"; pill.className = "pill inferred dot"; pill.title = "Add an API key for live daily trend research"; }
  } catch {}
}

const runBtn = $("#run-research");
runBtn.addEventListener("click", runResearch);
async function runResearch() {
  runBtn.disabled = true;
  const lbl = runBtn.querySelector(".lbl"), old = lbl.textContent;
  lbl.innerHTML = '<span class="spinner"></span> Working…';
  try {
    await api.post("/api/research/run");
    toast("Today's films are ready");
    await loadStatus();
    switchTab("today");
  } catch (e) { toast("Couldn't build the plan: " + e.message); }
  finally { runBtn.disabled = false; lbl.textContent = old; }
}
function setRunLabel() { $("#run-research .lbl").textContent = BRIEFING_EXISTS ? "New plan" : "Get today's films"; }

/* ----------------------------------------------------------------- nav */
const TABS = { today: renderToday, week: renderWeek };
$("#nav").addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) switchTab(b.dataset.tab); });
function switchTab(tab) {
  CURRENT = tab;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  view.innerHTML = skeleton();
  window.scrollTo(0, 0);
  (TABS[tab] || renderToday)().catch((e) => (view.innerHTML = `<div class="card">Something went wrong: ${esc(e.message)}</div>`));
}
function skeleton() { return `<div class="card"><div class="skeleton sk-line" style="width:40%"></div><div class="skeleton sk-line"></div><div class="skeleton sk-line" style="width:80%"></div></div>`; }

/* ------------------------------------------------------- shared pieces */
function chips(i) {
  return `<div class="chips">
    <span class="chip plat">${esc(i.platform)}</span>
    ${i.format ? `<span class="chip fmt">${esc(fmtLabel(i.format))}</span>` : ""}
    ${i.breed ? `<span class="chip breed">${esc(i.breed)}</span>` : ""}
  </div>`;
}
function filmRow(i, tag) {
  const r = el(`<div class="row" data-id="${i.id}">
    <div class="body">
      ${tag ? `<div class="row-tag">${esc(tag)}</div>` : ""}
      <div class="r-title">${esc(i.title)}</div>
      <div class="r-sub">${esc((i.hook || i.concept || "").slice(0, 90))}</div>
      <div class="r-chips">${chips(i)}</div>
    </div>
    <span class="go">${ICONS.chevron}</span>
  </div>`);
  r.querySelector(".go svg").classList.add("ico");
  r.addEventListener("click", () => openIdea(i.id));
  return r;
}

/* =====================================================================
   TODAY — the day's films, front and center
   ===================================================================== */
async function renderToday() {
  const b = await api.get("/api/briefing/today");
  BRIEFING_EXISTS = b.exists; setRunLabel();

  if (!b.exists) {
    view.innerHTML = "";
    view.appendChild(el(`<div class="card pad-lg empty">
      <div class="big">🐶</div>
      <h2>No films lined up yet</h2>
      <p>Tap below and your employee will research what's working and hand you today's shots — ready to film.</p>
      <button class="btn primary block" id="go-plan">Get today's films</button>
    </div>`));
    $("#go-plan").addEventListener("click", runResearch);
    return;
  }

  const brf = b.briefing, d = brf.data, p = b.primary_idea;
  const frag = document.createDocumentFragment();

  frag.appendChild(el(`<div style="margin-bottom:16px">
    <div class="eyebrow">Today's films · ${esc(fmtDate(brf.date))}</div>
    <h1 class="view-title" style="margin-top:6px">${esc(brf.headline || "Here's what to film today")}</h1>
  </div>`));

  if (brf.source === "inferred")
    frag.appendChild(el(`<div class="banner info"><div>These are dependable <b>starter ideas</b>, not today's live trends. Add an API key to switch on live daily research.</div></div>`));

  // MAIN film
  if (p) {
    const hero = el(`<div class="hero">
      <div class="eyebrow">Film this first</div>
      <h2>${esc(p.title)}</h2>
      ${p.hook ? `<div class="quote">${esc(p.hook)}</div>` : ""}
      ${chips(p)}
      <div class="stat-row">
        <div class="stat"><b>${p.virality_score}/10</b><span>Reach</span></div>
        <div class="stat"><b>${p.conversion_value}/10</b><span>Brings buyers</span></div>
        <div class="stat"><b>${esc(p.suggested_length || p.est_filming_time || "~20s")}</b><span>Length</span></div>
      </div>
      ${d.why_film_this_today ? `<p class="small soft"><b>Why this one:</b> ${esc(d.why_film_this_today)}</p>` : ""}
      <div class="btn-row" style="margin-top:16px">
        <button class="btn primary" data-open="${p.id}">Open script &amp; steps</button>
        <button class="btn accent" data-quick-approve="${p.id}">Approve</button>
      </div>
    </div>`);
    hero.querySelector("[data-open]").addEventListener("click", () => openIdea(p.id));
    hero.querySelector("[data-quick-approve]").addEventListener("click", async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      await api.post(`/api/ideas/${p.id}/action`, { action: "approve" });
      toast("Approved — open it to film"); renderToday();
    });
    frag.appendChild(hero);
  }

  // The rest of today's shots
  if ((b.additional_ideas || []).length) {
    const c = el(`<div class="card list-card"><div class="sec-head" style="padding-top:12px"><h3>Also film today</h3></div></div>`);
    b.additional_ideas.forEach((i) => c.appendChild(filmRow(i)));
    frag.appendChild(c);
  }

  view.innerHTML = "";
  view.appendChild(frag);
}

/* =====================================================================
   THIS WEEK — plan and see a week of films at a time
   ===================================================================== */
async function renderWeek() {
  const events = await api.get("/api/calendar");
  view.innerHTML = "";
  view.appendChild(el(`<h1 class="view-title">This week</h1><p class="view-sub">Your week of films at a glance. Let me lay out a whole week for you.</p>`));

  const planCard = el(`<div class="card" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
    <div style="flex:1;min-width:170px"><b>Plan my week</b><div class="tiny muted">I'll pick the best ideas, write the scripts, and lay out the days.</div></div>
    <select id="pw-count" class="sm"><option value="3">3 films</option><option value="5" selected>5 films</option><option value="7">7 films</option></select>
    <button class="btn primary sm" id="pw-go">Plan it</button>
  </div>`);
  view.appendChild(planCard);
  $("#pw-go").addEventListener("click", async () => {
    const btn = $("#pw-go"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Planning…';
    try { const r = await api.post("/api/plan/week", { posts: +$("#pw-count").value }); toast(`Planned ${r.count} films`); renderWeek(); }
    catch (e) { toast("Couldn't plan: " + e.message); btn.disabled = false; btn.textContent = "Plan it"; }
  });

  // Build the next 7 days (today → +6) so it always reads as "this week".
  const days = weekDays();
  const byDate = {};
  events.forEach((e) => (byDate[e.date] = byDate[e.date] || []).push(e));
  const hasAny = days.some((d) => byDate[d.iso]);

  if (!hasAny) {
    view.appendChild(el(`<div class="card empty"><h2>Nothing planned yet</h2>
      <p>Tap <b>Plan it</b> above and I'll fill your week with films — each with its full script ready to shoot.</p></div>`));
    return;
  }

  const wrap = el(`<div class="stack" style="margin-top:4px"></div>`);
  days.forEach((d) => {
    const evs = byDate[d.iso] || [];
    const day = el(`<div class="cal-day"><div class="d">${esc(d.label)}${d.isToday ? ' · <span style="color:var(--teal-strong)">Today</span>' : ""}</div></div>`);
    if (!evs.length) {
      day.appendChild(el(`<div class="cal-empty">—</div>`));
    } else {
      evs.forEach((e) => {
        const label = e.type === "record" ? "Film" : "Post";
        const svg = e.type === "record" ? ICONS.record : ICONS.publish;
        const ev = el(`<div class="cal-ev ${e.type}">${svg} ${label}: ${esc(e.title)}</div>`);
        ev.addEventListener("click", () => openIdea(e.idea_id)); day.appendChild(ev);
      });
    }
    wrap.appendChild(day);
  });
  view.appendChild(wrap);
}
function weekDays() {
  const out = [];
  const base = new Date(); base.setHours(0, 0, 0, 0);
  for (let n = 0; n < 7; n++) {
    const dt = new Date(base); dt.setDate(base.getDate() + n);
    const iso = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
    out.push({ iso, isToday: n === 0, label: dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) });
  }
  return out;
}
function fmtDate(s) { try { return new Date(s + "T00:00").toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" }); } catch { return s; } }

/* =====================================================================
   FILM DRAWER — the full plan + all controls (tap any film)
   ===================================================================== */
const BREEDS = ["Maltipoo","Yorkie","Pomeranian","Poodle","Cavapoo","Chorkie","Miniature Schnauzer","Chihuahua","Shih Tzu","Bichon"];

async function openIdea(id) {
  const i = await api.get(`/api/ideas/${id}`);
  const has = !!i.script;
  const reload = () => openIdea(id);

  const comp = i.compliance && i.compliance.summary && (i.compliance.issues || []).length
    ? `<div class="banner warn"><div><b>Quick check:</b> ${esc(i.compliance.summary)}
        <ul class="clean tiny" style="margin-top:5px">${i.compliance.issues.map((x, n) => `<li>${esc(x)}${i.compliance.fixes && i.compliance.fixes[n] ? " — <i>" + esc(i.compliance.fixes[n]) + "</i>" : ""}</li>`).join("")}</ul></div></div>`
    : (i.compliance && i.compliance.passed ? `<div class="banner good"><div>Passed the brand safety check.</div></div>` : "");

  const packageBlock = has ? `
    ${acc("The video — what to film", `
      ${field("First thing on screen", i.first_second_visual)}
      ${i.hook ? `<div class="quote">${esc(i.hook)}</div>` : ""}
      ${copyField("Full script", i.script)}
      ${field("How to film it (step by step)", i.filming_instructions)}
      ${field("Text on screen", i.on_screen_text)}
      ${i.suggested_length ? `<div class="chips" style="margin-top:8px"><span class="chip">${esc(i.suggested_length)}</span></div>` : ""}
      ${field("How to edit", i.editing_instructions)}
      ${field("Music / sound", i.audio_direction)}
    `, true)}
    ${acc("Caption &amp; hashtags — copy &amp; paste", `
      ${copyField("Caption", i.caption)}
      ${copyField("Hashtags", i.hashtags)}
      ${copyField("Post title", i.platform_title)}
      ${copyField("YouTube Shorts title", i.youtube_title)}
      ${copyField("Cover / thumbnail text", i.cover_text)}
      ${copyField("Pinned comment", i.pinned_comment)}
      ${field("Call to action", i.call_to_action)}
    `)}
    ${acc("Backups &amp; no-talking version", `
      ${field("Backup hook", i.backup_hook)}
      ${copyField("Backup caption", i.backup_caption)}
      ${field("Film it without talking", i.no_speak_version)}
    `)}
  ` : `<div class="card center" style="margin:0 0 12px">
      <p class="muted small" style="margin-bottom:12px">No script yet for this film.</p>
      <button class="btn primary block" id="build-pkg">Write the full script &amp; filming plan</button>
    </div>`;

  openDrawer(`
    <div style="min-width:0"><h2 style="font-size:1.25rem">${esc(i.title)}</h2>
      <div style="margin-top:8px">${chips(i)}</div>
    </div>
    <div class="chips" style="margin-top:10px">
      <span class="chip status">${esc(friendlyStatus(i.status))}</span>
      <span class="chip">${i.virality_score}/10 reach</span>
      <span class="chip">${i.conversion_value}/10 buyers</span>
      <span class="chip">${esc(i.difficulty)} to film</span>
    </div>
    ${i.concept ? `<p class="small soft" style="margin-top:12px">${nl(i.concept)}</p>` : ""}
    ${comp}

    <div class="btn-row" style="margin:14px 0">
      <button class="btn accent" data-act="approve">Approve</button>
      <button class="btn" data-act="mark_filmed">Filmed it</button>
      <button class="btn" data-act="mark_published">Posted it</button>
      <button class="btn danger" data-act="reject">Skip</button>
    </div>

    ${has ? `<div class="card" style="margin:0 0 12px;padding:14px">
      <div class="tiny muted" style="margin-bottom:8px;font-weight:600;text-transform:uppercase;letter-spacing:.04em">Want it different?</div>
      <div class="btn-row">
        <button class="btn subtle sm" data-act="shorter">Shorter</button>
        <button class="btn subtle sm" data-act="funnier">Funnier</button>
        <button class="btn subtle sm" data-act="more_educational">More helpful</button>
        <button class="btn subtle sm" data-act="regenerate">Fresh version</button>
        <select id="chg-breed" class="sm"><option value="">Different breed…</option>${BREEDS.map((b) => `<option>${b}</option>`).join("")}</select>
        <select id="chg-fmt" class="sm"><option value="">Switch format…</option>${FORMATS.map((f) => `<option value="${f}">${esc(fmtLabel(f))}</option>`).join("")}</select>
      </div></div>` : ""}

    ${packageBlock}

    ${acc("Schedule &amp; who films it", `
      <div class="form-grid">
        <div class="fld"><label>Assigned to</label><input id="a-emp" value="${esc(i.assigned_employee || "")}" placeholder="Name"></div>
        <div class="fld"><label>Film on</label><input id="a-rec" type="date" value="${i.recording_date || ""}"></div>
        <div class="fld"><label>Post on</label><input id="a-pub" type="date" value="${i.publishing_date || ""}"></div>
        <div class="fld"><label>Reuse after</label><input id="a-reuse" type="date" value="${i.suggested_reuse_date || ""}"></div>
      </div>
      <button class="btn block sm" id="save-sched" style="margin-top:10px">Save schedule</button>
    `)}

    ${acc("Add the numbers (after you post)", `
      <p class="tiny muted" style="margin-bottom:10px">Fill in what you can — shares, saves, comments and store calls matter most. The more you log, the smarter tomorrow's films get.</p>
      ${perfForm(i)}
      <button class="btn accent block" id="save-perf" style="margin-top:10px">Save the numbers</button>
    `)}

    ${acc("Notes", `
      <div class="val" style="margin-bottom:10px">${i.notes ? nl(i.notes) : '<span class="muted">No notes yet.</span>'}</div>
      <textarea id="fb-note" placeholder="Add a note for your team…"></textarea>
      <button class="btn block sm" id="save-note" style="margin-top:8px">Save note</button>
    `)}
  `);

  // upgrade carets to icons
  $("#drawer-body").querySelectorAll(".acc > summary .caret").forEach((c) => { c.innerHTML = ICONS.chevron; c.querySelector("svg").classList.add("ico"); });

  wireCopy();
  const bp = $("#build-pkg");
  if (bp) bp.addEventListener("click", async () => { bp.disabled = true; bp.innerHTML = '<span class="spinner"></span> Writing…'; await api.post(`/api/ideas/${id}/package`); toast("Script ready"); reload(); });

  document.querySelectorAll("[data-act]").forEach((btn) => btn.addEventListener("click", async () => {
    const act = btn.dataset.act; let value = "";
    if (act === "reject" && !confirm("Skip this film? It moves to the archive.")) return;
    btn.disabled = true;
    await api.post(`/api/ideas/${id}/action`, { action: act, value });
    toast(ACT_MSG[act] || "Done"); reload(); loadStatus();
  }));
  const cb = $("#chg-breed");
  if (cb) cb.addEventListener("change", async (e) => { if (!e.target.value) return; toast("Rewriting…"); await api.post(`/api/ideas/${id}/action`, { action: "change_breed", value: e.target.value }); reload(); });
  const cf = $("#chg-fmt");
  if (cf) cf.addEventListener("change", async (e) => {
    if (!e.target.value) return;
    toast("Switching format & rewriting…");
    await api.patch(`/api/ideas/${id}`, { format: e.target.value });
    await api.post(`/api/ideas/${id}/action`, { action: "regenerate", value: `film this as a ${e.target.value.replace(/_/g, " ")} video` });
    reload();
  });

  $("#save-sched")?.addEventListener("click", async () => {
    await api.patch(`/api/ideas/${id}`, { assigned_employee: $("#a-emp").value, recording_date: $("#a-rec").value || null, publishing_date: $("#a-pub").value || null, suggested_reuse_date: $("#a-reuse").value || null });
    toast("Saved to your week");
  });
  $("#save-note")?.addEventListener("click", async () => { const n = $("#fb-note").value.trim(); if (!n) return; await api.post(`/api/ideas/${id}/feedback`, { note: n }); toast("Note saved"); reload(); });
  $("#save-perf")?.addEventListener("click", async () => {
    const body = {};
    document.querySelectorAll("[data-perf]").forEach((n) => { if (n.value !== "") body[n.dataset.perf] = n.type === "number" ? +n.value : n.value; });
    if (!Object.keys(body).length) return toast("Enter at least one number");
    await api.post(`/api/ideas/${id}/performance`, body); toast("Numbers saved — thank you"); reload(); loadStatus();
  });
}
const ACT_MSG = { approve: "Approved", mark_filmed: "Marked as filmed", mark_published: "Marked as posted", reject: "Skipped", shorter: "Made it shorter", funnier: "Made it funnier", more_educational: "Made it more helpful", regenerate: "Fresh version ready" };
function friendlyStatus(s) { return ({ New: "Needs your OK", "Ready to Film": "Ready to film", Published: "Posted" }[s]) || s; }

function acc(title, body, open) {
  return `<details class="acc" ${open ? "open" : ""}><summary>${title}<span class="caret"></span></summary><div class="acc-body">${body}</div></details>`;
}
function field(label, val) { return val ? `<div class="fld"><label>${label}</label><div class="val">${nl(val)}</div></div>` : ""; }
function copyField(label, val) {
  if (!val) return "";
  return `<div class="fld copyfield"><label>${label}</label><div class="val">${nl(val)}</div>
    <button class="btn subtle sm copybtn" data-copy="${esc(val)}">Copy</button></div>`;
}
function wireCopy() {
  $("#drawer-body").querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => {
    navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; toast("Copied to clipboard");
    setTimeout(() => (b.textContent = "Copy"), 1200);
  }));
}
function perfForm(i) {
  const f = (label, key) => `<div class="fld"><label>${label}</label><input data-perf="${key}" type="number" inputmode="numeric"></div>`;
  return `<div class="form-grid">
    ${f("Views", "views")}${f("Shares", "shares")}${f("Saves", "saves")}${f("Comments", "comments")}
    ${f("Likes", "likes")}${f("Reach", "reach")}${f("Watch % done", "completion_rate")}${f("New followers", "follower_growth")}
    ${f("Profile visits", "profile_visits")}${f("Website clicks", "website_clicks")}${f("Store calls", "calls")}${f("Messages", "messages")}
    ${f("Visits/appointments", "appointments")}${f("Video length (sec)", "video_length_seconds")}
  </div>`;
}

/* ----------------------------------------------------------- drawer */
function openDrawer(html) {
  $("#drawer-body").innerHTML = html;
  $("#drawer").hidden = false; $("#drawer-backdrop").hidden = false;
  document.body.style.overflow = "hidden";
}
function closeDrawer() { $("#drawer").hidden = true; $("#drawer-backdrop").hidden = true; document.body.style.overflow = ""; }
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

/* ----------------------------------------------------------- boot */
loadStatus();
switchTab("today");
setInterval(loadStatus, 60000);
