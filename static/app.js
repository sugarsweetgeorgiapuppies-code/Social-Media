/* Sugar Sweet Georgia Puppies — dashboard */
"use strict";

const api = {
  async get(path) { return this._json(await fetch(path)); },
  async post(path, body) {
    return this._json(await fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }));
  },
  async patch(path, body) {
    return this._json(await fetch(path, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  },
  async put(path, body) {
    return this._json(await fetch(path, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  },
  async _json(r) {
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json();
  },
};

const $ = (sel, root = document) => root.querySelector(sel);
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const nl = (s) => esc(s).replace(/\n/g, "<br>");

let TOAST_T;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(TOAST_T); TOAST_T = setTimeout(() => (t.hidden = true), 2600);
}

const view = $("#view");
let CURRENT = "briefing";

// -------------------------------------------------------------------------
// Status bar
// -------------------------------------------------------------------------
async function loadStatus() {
  try {
    const s = await api.get("/api/status");
    const pill = $("#mode-pill");
    if (s.ai_enabled) { pill.textContent = `Live research · ${s.model}`; pill.className = "pill live"; }
    else { pill.textContent = "Inferred (offline) mode"; pill.className = "pill inferred"; }
  } catch (e) { /* ignore */ }
}

$("#run-research").addEventListener("click", async (e) => {
  const btn = e.target; btn.disabled = true; const old = btn.textContent;
  btn.textContent = "Researching…";
  try {
    await api.post("/api/research/run");
    toast("Fresh research + briefing ready");
    await loadStatus();
    if (CURRENT === "briefing") renderBriefing();
    else switchTab(CURRENT);
  } catch (e) { toast("Research failed: " + e.message); }
  finally { btn.disabled = false; btn.textContent = old; }
});

// -------------------------------------------------------------------------
// Tabs
// -------------------------------------------------------------------------
const TABS = {
  briefing: renderBriefing, ideas: renderIdeas, approvals: renderApprovals,
  calendar: renderCalendar, published: renderPublished, analytics: renderAnalytics,
  series: renderSeries, trends: renderTrends, inspiration: renderInspiration,
  rules: renderRules, logs: renderLogs,
};
$("#tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]"); if (!b) return;
  switchTab(b.dataset.tab);
});
function switchTab(tab) {
  CURRENT = tab;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  view.innerHTML = '<div class="loading">Loading…</div>';
  TABS[tab]().catch((e) => (view.innerHTML = `<div class="card">Error: ${esc(e.message)}</div>`));
}

// -------------------------------------------------------------------------
// Reusable bits
// -------------------------------------------------------------------------
function sourceBanner(source) {
  if (source === "inferred")
    return `<div class="banner">⚠️ These recommendations are <b>inferred from durable puppy best-practices</b>, not confirmed live research. Add an <kbd>ANTHROPIC_API_KEY</kbd> to enable daily live trend research.</div>`;
  return "";
}
function ideaTags(i) {
  return `<span class="tag cat">${esc(i.category)}</span>
    <span class="tag plat">${esc(i.platform)}</span>
    <span class="tag type">${esc((i.content_type || "").replace(/_/g, " "))}</span>
    ${i.breed ? `<span class="tag">${esc(i.breed)}</span>` : ""}
    <span class="tag status">${esc(i.status)}</span>`;
}
function ideaRow(i) {
  const row = el(`<div class="idea-row" data-id="${i.id}">
    <div>
      <div class="idea-title">${esc(i.title)}</div>
      <div class="idea-meta small muted">${i.hook ? esc(i.hook.slice(0, 90)) : esc((i.concept || "").slice(0, 90))}</div>
      <div class="idea-meta">${ideaTags(i)}</div>
    </div>
    <div class="prio">★ ${i.priority_score}</div>
  </div>`);
  row.addEventListener("click", () => openIdea(i.id));
  return row;
}
function scores(v, c) {
  return `<div class="scores">
    <div class="score"><b>${v}</b><span>Virality</span></div>
    <div class="score"><b>${c}</b><span>Conversion</span></div>
  </div>`;
}

// -------------------------------------------------------------------------
// Today's briefing
// -------------------------------------------------------------------------
async function renderBriefing() {
  const b = await api.get("/api/briefing/today");
  if (!b.exists) {
    view.innerHTML = `<div class="card"><h2>No briefing yet for ${esc(b.date)}</h2>
      <p class="muted">Click <b>Run research now</b> in the top bar to have your social media employee research today's trends and build a filming plan.</p></div>`;
    return;
  }
  const brf = b.briefing, d = brf.data;
  const wrap = document.createDocumentFragment();

  const head = el(`<div class="card">
    ${sourceBanner(brf.source)}
    <h2>${esc(brf.headline || "Today's briefing")}</h2>
    <p>${nl(brf.summary)}</p>
    ${d.why_film_this_today ? `<p class="small"><b>Why film this today:</b> ${nl(d.why_film_this_today)}</p>` : ""}
  </div>`);
  wrap.appendChild(head);

  // Best video to film today
  if (b.primary_idea) {
    const p = b.primary_idea;
    const card = el(`<div class="card">
      <h2>🎬 Best video to film today</h2>
      <h3>${esc(p.title)}</h3>
      <div>${ideaTags(p)}</div>
      ${scores(p.virality_score, p.conversion_value)}
      <div class="hook-box">${esc(p.hook || p.first_second_visual || "")}</div>
      <button class="btn primary" data-open="${p.id}">Open full filming package</button>
    </div>`);
    card.querySelector("[data-open]").addEventListener("click", () => openIdea(p.id));
    wrap.appendChild(card);
  }

  // Trends worth using
  const trends = d.trends_worth_using || [];
  if (trends.length) {
    const c = el(`<div class="card"><h2>📈 Trends worth using today</h2><div class="grid"></div></div>`);
    const g = c.querySelector(".grid");
    trends.forEach((t) => g.appendChild(el(`<div class="card" style="margin:0">
      <h3>${esc(t.name)} <span class="tag plat">${esc(t.platform)}</span></h3>
      <p class="small">${esc(t.description || "")}</p>
      <p class="small"><b>Why it's working:</b> ${esc(t.why_working || "")}</p>
      <p class="small"><b>Our version:</b> ${esc(t.adaptation || "")}</p>
      <p class="small muted">Lifespan: ${esc(t.expected_lifespan || "—")} · Difficulty: ${esc(t.difficulty || "—")} · ~${esc(t.est_filming_time || "—")}</p>
      ${scores(t.virality_score, t.conversion_value)}
    </div>`)));
    wrap.appendChild(c);
  }

  // Additional ideas
  if ((b.additional_ideas || []).length) {
    const c = el(`<div class="card"><h2>💡 More ideas today</h2></div>`);
    b.additional_ideas.forEach((i) => c.appendChild(ideaRow(i)));
    wrap.appendChild(c);
  }

  // Community engagement + repurpose
  const lists = el(`<div class="grid"></div>`);
  lists.appendChild(listCard("🤝 Community engagement", b.community_engagement));
  lists.appendChild(listCard("♻️ Content to repurpose", b.repurpose_ideas));
  wrap.appendChild(lists);

  view.innerHTML = "";
  view.appendChild(wrap);
}
function listCard(title, items) {
  const c = el(`<div class="card" style="margin:0"><h2>${title}</h2><ul></ul></div>`);
  const ul = c.querySelector("ul");
  (items || []).forEach((x) => ul.appendChild(el(`<li class="small">${esc(x)}</li>`)));
  if (!items || !items.length) ul.appendChild(el(`<li class="small muted">Nothing yet.</li>`));
  return c;
}

// -------------------------------------------------------------------------
// Idea database
// -------------------------------------------------------------------------
const STATUSES = ["New","Approved","Needs Revision","Ready to Film","Filmed","Editing","Scheduled","Published","Repurpose","Retest","Archived"];
const CATEGORIES = ["Viral Entertainment","Emotional","Educational","Local","Behind-the-Scenes","Conversion"];
const PLATFORMS = ["Instagram","TikTok","YouTube Shorts","Facebook","Cross-platform"];

async function renderIdeas() {
  view.innerHTML = "";
  const bar = el(`<div class="filters">
    <input id="f-q" placeholder="Search…" />
    <select id="f-status"><option value="">All statuses</option>${STATUSES.map(s=>`<option>${s}</option>`).join("")}</select>
    <select id="f-cat"><option value="">All categories</option>${CATEGORIES.map(s=>`<option>${s}</option>`).join("")}</select>
    <select id="f-plat"><option value="">All platforms</option>${PLATFORMS.map(s=>`<option>${s}</option>`).join("")}</select>
    <button class="btn" id="f-new">+ New idea</button>
  </div>`);
  view.appendChild(bar);
  const listWrap = el(`<div class="card" id="idea-list"></div>`);
  view.appendChild(listWrap);

  async function load() {
    const params = new URLSearchParams();
    if ($("#f-q").value) params.set("q", $("#f-q").value);
    if ($("#f-status").value) params.set("status", $("#f-status").value);
    if ($("#f-cat").value) params.set("category", $("#f-cat").value);
    if ($("#f-plat").value) params.set("platform", $("#f-plat").value);
    const ideas = await api.get("/api/ideas?" + params.toString());
    listWrap.innerHTML = ideas.length ? "" : `<p class="muted">No ideas yet. Run research or add one.</p>`;
    ideas.forEach((i) => listWrap.appendChild(ideaRow(i)));
  }
  ["f-q","f-status","f-cat","f-plat"].forEach((id) => {
    const node = $("#" + id);
    node.addEventListener(id === "f-q" ? "input" : "change", debounce(load, 250));
  });
  $("#f-new").addEventListener("click", newIdeaForm);
  load();
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function newIdeaForm() {
  openDrawer(`<h2>New idea</h2>
    <div class="form-grid">
      <div class="full"><label>Title</label><input id="n-title"></div>
      <div><label>Category</label><select id="n-cat">${CATEGORIES.map(s=>`<option>${s}</option>`).join("")}</select></div>
      <div><label>Platform</label><select id="n-plat">${PLATFORMS.map(s=>`<option>${s}</option>`).join("")}</select></div>
      <div><label>Breed</label><input id="n-breed"></div>
      <div><label>Content type</label><select id="n-type">
        <option value="evergreen">Evergreen</option><option value="current_trend">Current trend</option>
        <option value="conversion">Conversion</option><option value="experimental">Experimental</option>
        <option value="recurring_series">Recurring series</option><option value="community_engagement">Community engagement</option>
      </select></div>
      <div class="full"><label>Concept</label><textarea id="n-concept"></textarea></div>
      <div class="full"><label>Hook idea</label><input id="n-hook"></div>
      <div><label>Virality (1-10)</label><input id="n-vir" type="number" min="1" max="10" value="6"></div>
      <div><label>Conversion (1-10)</label><input id="n-con" type="number" min="1" max="10" value="5"></div>
      <div><label>Difficulty</label><select id="n-diff"><option>Easy</option><option selected>Medium</option><option>Hard</option></select></div>
    </div>
    <div class="btn-row"><button class="btn primary" id="n-save">Create idea</button></div>`);
  $("#n-save").addEventListener("click", async () => {
    const body = {
      title: $("#n-title").value.trim(), category: $("#n-cat").value, platform: $("#n-plat").value,
      breed: $("#n-breed").value, content_type: $("#n-type").value, concept: $("#n-concept").value,
      hook: $("#n-hook").value, virality_score: +$("#n-vir").value, conversion_value: +$("#n-con").value,
      difficulty: $("#n-diff").value,
    };
    if (!body.title) { toast("Title required"); return; }
    const idea = await api.post("/api/ideas", body);
    toast("Idea created"); openIdea(idea.id);
    if (CURRENT === "ideas") renderIdeas();
  });
}

// -------------------------------------------------------------------------
// Idea drawer (full package + all controls)
// -------------------------------------------------------------------------
async function openIdea(id) {
  const i = await api.get(`/api/ideas/${id}`);
  const pkg = i.script ? packageHtml(i) : `<p class="muted">No filming package yet.</p>
    <button class="btn primary" id="build-pkg">Generate full filming package</button>`;
  const comp = i.compliance && i.compliance.summary ? complianceHtml(i.compliance) : "";

  openDrawer(`
    <h2>${esc(i.title)}</h2>
    <div>${ideaTags(i)}</div>
    ${scores(i.virality_score, i.conversion_value)}
    <p class="small muted">Difficulty ${esc(i.difficulty)} · ~${esc(i.est_filming_time || "?")} · Priority ★${i.priority_score} · Created ${esc(i.date_created)}</p>
    ${i.concept ? `<div class="pkg-field"><label>Concept</label><div class="val">${nl(i.concept)}</div></div>` : ""}
    ${comp}

    <div class="section"><h3>Workflow</h3>
      <div class="btn-row">
        <button class="btn primary" data-act="approve">Approve</button>
        <button class="btn" data-act="ready">Ready to film</button>
        <button class="btn" data-act="mark_filmed">Mark filmed</button>
        <button class="btn" data-act="mark_published">Mark published</button>
        <button class="btn danger" data-act="reject">Reject</button>
      </div>
      <div class="btn-row">
        <button class="btn ghost" data-act="revise">Request revision</button>
        <button class="btn ghost" data-act="regenerate">Generate another version</button>
        <button class="btn ghost" data-act="shorter">Shorten</button>
        <button class="btn ghost" data-act="funnier">Funnier</button>
        <button class="btn ghost" data-act="more_educational">More educational</button>
        <button class="btn ghost" data-act="retest">Retest</button>
      </div>
      <div class="btn-row">
        <select id="chg-breed"><option value="">Change breed…</option>${["Maltipoo","Yorkie","Pomeranian","Poodle","Cavapoo","Chorkie","Miniature Schnauzer","Chihuahua","Shih Tzu","Bichon"].map(b=>`<option>${b}</option>`).join("")}</select>
        <select id="chg-plat"><option value="">Change platform…</option>${PLATFORMS.map(p=>`<option>${p}</option>`).join("")}</select>
        <select id="chg-status"><option value="">Set status…</option>${STATUSES.map(s=>`<option ${s===i.status?"selected":""}>${s}</option>`).join("")}</select>
      </div>
    </div>

    <div class="section"><h3>Filming package</h3><div id="pkg-holder">${pkg}</div></div>

    <div class="section"><h3>Schedule & assignment</h3>
      <div class="form-grid">
        <div><label>Assigned employee</label><input id="a-emp" value="${esc(i.assigned_employee||"")}"></div>
        <div><label>Record date</label><input id="a-rec" type="date" value="${i.recording_date||""}"></div>
        <div><label>Publish date</label><input id="a-pub" type="date" value="${i.publishing_date||""}"></div>
        <div><label>Reuse after</label><input id="a-reuse" type="date" value="${i.suggested_reuse_date||""}"></div>
      </div>
      <div class="btn-row"><button class="btn" id="save-sched">Save schedule</button></div>
    </div>

    <div class="section"><h3>Log performance</h3>${perfFormHtml(i)}</div>
    <div class="section"><h3>Team feedback / notes</h3>
      <div class="pkg-field"><div class="val">${i.notes ? nl(i.notes) : '<span class="muted">No notes yet.</span>'}</div></div>
      <div class="form-grid"><div class="full"><textarea id="fb-note" placeholder="Add a note or employee feedback…"></textarea></div></div>
      <div class="btn-row"><button class="btn" id="save-note">Save note</button></div>
    </div>
  `);

  const reload = () => openIdea(id);

  const buildBtn = $("#build-pkg");
  if (buildBtn) buildBtn.addEventListener("click", async () => {
    buildBtn.disabled = true; buildBtn.textContent = "Generating…";
    await api.post(`/api/ideas/${id}/package`); toast("Filming package ready"); reload();
  });

  document.querySelectorAll("[data-act]").forEach((btn) => btn.addEventListener("click", async () => {
    const act = btn.dataset.act;
    let value = "";
    if (act === "revise") value = prompt("What should change?") || "";
    if (act === "reject") value = prompt("Reason (optional)") || "";
    btn.disabled = true;
    await api.post(`/api/ideas/${id}/action`, { action: act, value });
    toast("Done"); reload(); loadStatus();
  }));

  const bindChange = (sel, action) => $(sel).addEventListener("change", async (e) => {
    if (!e.target.value) return;
    if (action === "status") { await api.patch(`/api/ideas/${id}`, { status: e.target.value }); }
    else { await api.post(`/api/ideas/${id}/action`, { action, value: e.target.value }); }
    toast("Updated"); reload();
  });
  bindChange("#chg-breed", "change_breed");
  bindChange("#chg-plat", "change_platform");
  bindChange("#chg-status", "status");

  $("#save-sched").addEventListener("click", async () => {
    await api.patch(`/api/ideas/${id}`, {
      assigned_employee: $("#a-emp").value,
      recording_date: $("#a-rec").value || null,
      publishing_date: $("#a-pub").value || null,
      suggested_reuse_date: $("#a-reuse").value || null,
    });
    toast("Schedule saved"); reload();
  });
  $("#save-note").addEventListener("click", async () => {
    const note = $("#fb-note").value.trim(); if (!note) return;
    await api.post(`/api/ideas/${id}/feedback`, { note }); toast("Note saved"); reload();
  });
  $("#save-perf").addEventListener("click", async () => {
    const body = {};
    document.querySelectorAll("[data-perf]").forEach((n) => {
      const v = n.value; if (v === "") return;
      body[n.dataset.perf] = n.type === "number" ? +v : v;
    });
    await api.post(`/api/ideas/${id}/performance`, body);
    toast("Performance logged"); reload(); loadStatus();
  });
}

function packageHtml(i) {
  const f = (label, val) => val ? `<div class="pkg-field copyable"><label>${label}</label><div class="val">${nl(val)}</div><button class="btn sm copy" data-copy="${esc(val)}">copy</button></div>` : "";
  const html = [
    f("First-second visual", i.first_second_visual),
    `<div class="hook-box">${esc(i.hook)}</div>`,
    f("Full script", i.script),
    f("Shot-by-shot filming", i.filming_instructions),
    f("On-screen text", i.on_screen_text),
    f("Suggested length", i.suggested_length),
    f("Editing", i.editing_instructions),
    f("Audio / music", i.audio_direction),
    f("Caption", i.caption),
    f("Platform title", i.platform_title),
    f("YouTube Shorts title", i.youtube_title),
    f("Hashtags", i.hashtags),
    f("Cover text", i.cover_text),
    f("Pinned comment", i.pinned_comment),
    f("Call to action", i.call_to_action),
    f("Backup hook", i.backup_hook),
    f("Backup caption", i.backup_caption),
    f("No-talking version", i.no_speak_version),
  ].join("");
  return html;
}
function complianceHtml(c) {
  const cls = { none: "live", low: "live", medium: "inferred", high: "inferred" }[c.risk_level] || "";
  return `<div class="banner"><b>Brand check:</b> ${esc(c.summary)} <span class="pill ${cls}">risk: ${esc(c.risk_level||"n/a")}</span>
    ${(c.issues||[]).length ? "<ul class='small'>" + c.issues.map((x,idx)=>`<li>${esc(x)}${c.fixes&&c.fixes[idx]?` — <i>${esc(c.fixes[idx])}</i>`:""}</li>`).join("") + "</ul>" : ""}</div>`;
}
function perfFormHtml(i) {
  const F = (label, key, type = "number") => `<div><label>${label}</label><input data-perf="${key}" type="${type}"></div>`;
  return `<div class="form-grid">
    ${F("Views","views")}${F("Reach","reach")}${F("Likes","likes")}${F("Comments","comments")}
    ${F("Shares","shares")}${F("Saves","saves")}${F("Avg watch (s)","avg_watch_time_seconds")}${F("Completion %","completion_rate")}
    ${F("Follower growth","follower_growth")}${F("Profile visits","profile_visits")}${F("Website clicks","website_clicks")}${F("Video length (s)","video_length_seconds")}
    ${F("Calls","calls")}${F("Messages","messages")}${F("Appointments/visits","appointments")}
    <div><label>Platform</label><input data-perf="platform" value="${esc(i.platform)}"></div>
    <div class="full"><label>Notes</label><input data-perf="notes" type="text"></div>
  </div>
  <div class="btn-row"><button class="btn primary" id="save-perf">Log performance</button></div>`;
}

// -------------------------------------------------------------------------
// Approvals (scripts waiting) + Published + Calendar
// -------------------------------------------------------------------------
async function renderApprovals() {
  const ideas = await api.get("/api/ideas?status=New");
  const rev = await api.get("/api/ideas?status=Needs Revision");
  const all = [...ideas, ...rev];
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Scripts waiting for approval</h2></div>`);
  if (!all.length) c.appendChild(el(`<p class="muted">Nothing waiting. Everything's reviewed! 🎉</p>`));
  all.forEach((i) => c.appendChild(ideaRow(i)));
  view.appendChild(c);
}
async function renderPublished() {
  const ideas = await api.get("/api/ideas?status=Published");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Published content</h2></div>`);
  if (!ideas.length) c.appendChild(el(`<p class="muted">Nothing published yet.</p>`));
  ideas.forEach((i) => c.appendChild(ideaRow(i)));
  view.appendChild(c);
}
async function renderCalendar() {
  const events = await api.get("/api/calendar");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Content calendar</h2></div>`);
  if (!events.length) c.appendChild(el(`<p class="muted">No scheduled recordings or publishes yet. Set record/publish dates on an idea.</p>`));
  const byDate = {};
  events.forEach((e) => (byDate[e.date] = byDate[e.date] || []).push(e));
  const g = el(`<div class="grid"></div>`);
  Object.keys(byDate).sort().forEach((date) => {
    const day = el(`<div class="cal-day"><div class="d">${esc(date)}</div></div>`);
    byDate[date].forEach((e) => {
      const ev = el(`<div class="cal-ev ${e.type}">${e.type === "record" ? "🎥" : "🚀"} ${esc(e.title)}</div>`);
      ev.addEventListener("click", () => openIdea(e.idea_id));
      day.appendChild(ev);
    });
    g.appendChild(day);
  });
  c.appendChild(g);
  view.appendChild(c);
}

// -------------------------------------------------------------------------
// Analytics
// -------------------------------------------------------------------------
async function renderAnalytics() {
  const a = await api.get("/api/analytics");
  view.innerHTML = "";
  const list = (title, items) => (items && items.length)
    ? `<div class="section"><h3>${title}</h3><ul class="small">${items.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  view.appendChild(el(`<div class="card">
    ${sourceBanner(a.source)}
    <h2>Performance analysis <span class="pill">confidence: ${esc(a.data_confidence||"low")}</span></h2>
    <p><b>${esc(a.headline||"")}</b></p>
    ${list("Recommendations", a.recommendations)}
    ${list("Best hooks", a.best_hooks)}
    ${list("Best breeds", a.best_breeds)}
    ${list("Best lengths", a.best_lengths)}
    ${list("Winning formats", a.winning_formats)}
    ${list("Topics driving comments", a.topics_driving_comments)}
    ${list("Topics driving inquiries", a.topics_driving_inquiries)}
    ${list("Best posting times", a.best_posting_times)}
    ${list("Series to continue", a.series_to_continue)}
    ${list("Series to stop", a.series_to_stop)}
    ${list("Ideas to retest", a.ideas_to_retest)}
    ${list("Ideas to stop", a.ideas_to_stop)}
  </div>`));
}

// -------------------------------------------------------------------------
// Series / Trends / Inspiration / Rules / Logs
// -------------------------------------------------------------------------
async function renderSeries() {
  const rows = await api.get("/api/series");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Recurring series</h2><p class="muted small">Repeatable formats audiences can recognise and follow.</p><div class="grid"></div></div>`);
  const g = c.querySelector(".grid");
  rows.forEach((s) => g.appendChild(el(`<div class="card" style="margin:0">
    <h3>${esc(s.name)} ${s.active ? "" : '<span class="tag">paused</span>'}</h3>
    <p class="small"><b>Format:</b> ${esc(s.repeatable_format)}</p>
    <p class="small"><b>Opening hook:</b> ${esc(s.opening_hook)}</p>
    <p class="small"><b>How to record:</b> ${esc(s.recording_process)}</p>
    <p class="small"><b>Frequency:</b> ${esc(s.publishing_frequency)}</p>
    <p class="small"><b>Why viewers return:</b> ${esc(s.why_return)}</p>
    <p class="small"><b>How it evolves:</b> ${esc(s.evolution)}</p>
    <p class="small"><b>Business goal:</b> ${esc(s.business_goal)}</p>
  </div>`)));
  view.appendChild(c);
}
async function renderTrends() {
  const rows = await api.get("/api/trends");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Trend research log</h2><p class="muted small">Each trend records the date it was discovered so old trends aren't treated as current.</p></div>`);
  if (!rows.length) c.appendChild(el(`<p class="muted">No trends yet. Run research.</p>`));
  rows.forEach((t) => c.appendChild(el(`<div style="padding:12px 0;border-bottom:1px solid var(--line)">
    <h3>${esc(t.name)} <span class="tag plat">${esc(t.platform)}</span> <span class="tag ${t.status==='active'?'cat':''}">${esc(t.status)}</span> ${t.source==='inferred'?'<span class="tag type">inferred</span>':''}</h3>
    <p class="small muted">Found ${esc(t.date_discovered)} · Lifespan ${esc(t.expected_lifespan||"—")} · Difficulty ${esc(t.difficulty)} · ~${esc(t.est_filming_time||"—")}</p>
    <p class="small">${esc(t.description)}</p>
    <p class="small"><b>Our version:</b> ${esc(t.adaptation)}</p>
    <p class="small"><b>Risks:</b> ${esc(t.risks||"none noted")}</p>
    ${scores(t.virality_score, t.conversion_value)}
  </div>`)));
  view.appendChild(c);
}
async function renderInspiration() {
  const rows = await api.get("/api/competitors");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Competitor & format inspiration</h2><p class="muted small">Studied for why they work — never copied. We adapt the structure into original puppy content.</p><div class="grid"></div></div>`);
  const g = c.querySelector(".grid");
  rows.forEach((x) => g.appendChild(el(`<div class="card" style="margin:0">
    <h3>${esc(x.name)}</h3>
    <p class="small"><span class="tag plat">${esc(x.platform)}</span> <span class="tag type">${esc(x.format_type)}</span></p>
    <p class="small"><b>Why it works:</b> ${esc(x.what_works)}</p>
    <p class="small"><b>Our adaptation:</b> ${esc(x.adaptation_idea)}</p>
  </div>`)));
  view.appendChild(c);
}
async function renderRules() {
  const r = await api.get("/api/brand-rules");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Saved brand rules</h2><p class="muted small">The AI employee follows these. Edit any value and save; it takes effect on the next run.</p></div>`);
  Object.keys(r).forEach((key) => {
    const val = JSON.stringify(r[key], null, 2);
    const box = el(`<div class="section"><h3>${esc(key)}</h3>
      <textarea style="width:100%;min-height:${Math.min(200, 40 + val.length/3)}px">${esc(val)}</textarea>
      <div class="btn-row"><button class="btn sm">Save ${esc(key)}</button></div></div>`);
    box.querySelector("button").addEventListener("click", async () => {
      let parsed;
      try { parsed = JSON.parse(box.querySelector("textarea").value); }
      catch (e) { toast("Invalid JSON"); return; }
      await api.put("/api/brand-rules", { key, value: parsed });
      toast(`Saved ${key}`);
    });
    c.appendChild(box);
  });
  view.appendChild(c);
}
async function renderLogs() {
  const rows = await api.get("/api/logs");
  view.innerHTML = "";
  const c = el(`<div class="card"><h2>Activity log</h2></div>`);
  if (!rows.length) c.appendChild(el(`<p class="muted">No runs yet.</p>`));
  rows.forEach((l) => c.appendChild(el(`<div style="padding:8px 0;border-bottom:1px solid var(--line)">
    <span class="tag ${l.status==='ok'?'cat':''}">${esc(l.status)}</span>
    <span class="tag type">${esc(l.run_type)}</span>
    <span class="tag ${l.source==='inferred'?'type':'plat'}">${esc(l.source)}</span>
    <span class="small muted">${esc(l.created_at)}</span>
    <div class="small">${esc(l.message)} — ${l.trends_found} trends, ${l.ideas_created} ideas</div>
  </div>`)));
  view.appendChild(c);
}

// -------------------------------------------------------------------------
// Drawer
// -------------------------------------------------------------------------
function openDrawer(html) {
  $("#drawer-body").innerHTML = html;
  $("#drawer").hidden = false;
  $("#drawer-backdrop").hidden = false;
  // wire copy buttons
  $("#drawer-body").querySelectorAll("[data-copy]").forEach((b) =>
    b.addEventListener("click", () => { navigator.clipboard.writeText(b.dataset.copy); toast("Copied"); }));
}
function closeDrawer() { $("#drawer").hidden = true; $("#drawer-backdrop").hidden = true; }
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

// -------------------------------------------------------------------------
// Boot
// -------------------------------------------------------------------------
loadStatus();
switchTab("briefing");
setInterval(loadStatus, 60000);
