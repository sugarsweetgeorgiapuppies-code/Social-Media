/* Sugar Sweet Georgia Puppies — dashboard (friendly redesign) */
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

const PLAT_ICON = { Instagram: "📸", TikTok: "🎵", "YouTube Shorts": "▶️", Facebook: "👍", "Cross-platform": "🌐" };
const CAT_ICON = { "Viral Entertainment": "🤣", Emotional: "🥹", Educational: "🎓", Local: "📍", "Behind-the-Scenes": "🎬", Conversion: "🛎️" };
const TYPE_LABEL = {
  current_trend: "Trending now", evergreen: "Always works", conversion: "Brings people in",
  experimental: "Worth a test", recurring_series: "Series", community_engagement: "Get comments",
};
const FORMAT_LABEL = {
  puppy_focus: "🐶 Puppy on screen", voiceover: "🎙️ Voiceover", talking_head: "🗣️ Talking to camera",
  skit: "🎭 Mini skit", text_only: "🔠 Text only",
};
const FORMATS = Object.keys(FORMAT_LABEL);
const catIcon = (c) => CAT_ICON[c] || "🐶";
const platIcon = (p) => PLAT_ICON[p] || "🌐";
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
  const lbl = runBtn.querySelector(".lbl"), ic = runBtn.querySelector(".ic");
  const old = lbl.textContent; lbl.textContent = "Working…"; ic.innerHTML = '<span class="spinner"></span>';
  try {
    await api.post("/api/research/run");
    toast("✨ Today's plan is ready");
    await loadStatus();
    switchTab("today");
  } catch (e) { toast("Couldn't build the plan: " + e.message); }
  finally { runBtn.disabled = false; lbl.textContent = old; ic.textContent = "✨"; }
}
function setRunLabel() { $("#run-research .lbl").textContent = BRIEFING_EXISTS ? "Refresh plan" : "Get today's plan"; }

/* ----------------------------------------------------------------- nav */
const TABS = { today: renderToday, chat: renderChat, ideas: renderIdeas, calendar: renderCalendar, results: renderResults, more: renderMore };
$("#nav").addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) switchTab(b.dataset.tab); });
function switchTab(tab) {
  CURRENT = tab;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  view.innerHTML = skeleton();
  window.scrollTo(0, 0);
  TABS[tab]().catch((e) => (view.innerHTML = `<div class="card">Something went wrong: ${esc(e.message)}</div>`));
}
function skeleton() { return `<div class="card"><div class="skeleton sk-line" style="width:40%"></div><div class="skeleton sk-line"></div><div class="skeleton sk-line" style="width:80%"></div></div>`; }

/* ------------------------------------------------------- shared pieces */
function chips(i) {
  return `<div class="chips">
    <span class="chip plat">${platIcon(i.platform)} ${esc(i.platform)}</span>
    <span class="chip cat">${esc(i.category)}</span>
    ${i.format ? `<span class="chip fmt">${esc(fmtLabel(i.format))}</span>` : ""}
    ${i.breed ? `<span class="chip breed">${esc(i.breed)}</span>` : ""}
    ${i.content_type ? `<span class="chip">${esc(TYPE_LABEL[i.content_type] || i.content_type)}</span>` : ""}
  </div>`;
}
function ideaRow(i) {
  const r = el(`<div class="row" data-id="${i.id}">
    <div class="avatar">${catIcon(i.category)}</div>
    <div class="body">
      <div class="r-title">${esc(i.title)}</div>
      <div class="r-sub">${esc((i.hook || i.concept || "").slice(0, 80))}</div>
      <div class="r-chips">${chips(i)}</div>
    </div>
    <span class="go">›</span>
  </div>`);
  r.addEventListener("click", () => openIdea(i.id));
  return r;
}

/* =====================================================================
   TODAY
   ===================================================================== */
async function renderToday() {
  const [b, tasks] = await Promise.all([api.get("/api/briefing/today"), api.get("/api/tasks").catch(() => null)]);
  BRIEFING_EXISTS = b.exists; setRunLabel();

  if (!b.exists) {
    view.innerHTML = "";
    if (tasks) view.appendChild(standupCard(tasks));
    view.appendChild(el(`<div class="card pad-lg empty">
      <div class="big">🐶</div>
      <h2>Good morning!</h2>
      <p>Tap the button and your social media employee will research today's trends and hand you a ready-to-film video plan.</p>
      <button class="btn primary block" id="go-plan"><span class="ic">✨</span> Get today's plan</button>
      <p class="tiny" style="margin-top:14px">Or open <b>Ask</b> and just tell me what you need.</p>
    </div>`));
    $("#go-plan").addEventListener("click", runResearch);
    return;
  }

  const brf = b.briefing, d = brf.data, p = b.primary_idea;
  const frag = document.createDocumentFragment();

  if (tasks) frag.appendChild(standupCard(tasks));

  frag.appendChild(el(`<div class="stack" style="margin-bottom:14px">
    <div class="eyebrow">Your briefing · ${esc(brf.date)}</div>
    <h1 class="view-title">${esc(brf.headline || "Here's today's plan")}</h1>
  </div>`));

  if (brf.source === "inferred")
    frag.appendChild(el(`<div class="banner info"><span class="bic">💡</span><div>These are dependable <b>starter ideas</b>, not today's live trends. Add an API key (Settings → How this works) to switch on live daily research.</div></div>`));

  // Hero — best video to film today
  if (p) {
    const hero = el(`<div class="hero">
      <div class="eyebrow">🎬 Film this today</div>
      <h2>${esc(p.title)}</h2>
      ${p.hook ? `<div class="quote">“${esc(p.hook)}”</div>` : ""}
      ${chips(p)}
      <div class="stat-row">
        <div class="stat"><b>${p.virality_score}/10</b><span>Reach</span></div>
        <div class="stat"><b>${p.conversion_value}/10</b><span>Brings buyers</span></div>
        <div class="stat"><b>${esc(p.suggested_length || p.est_filming_time || "~20s")}</b><span>Length</span></div>
      </div>
      ${d.why_film_this_today ? `<p class="small soft">✅ <b>Why this one:</b> ${esc(d.why_film_this_today)}</p>` : ""}
      <div class="btn-row" style="margin-top:16px">
        <button class="btn primary" data-open="${p.id}"><span class="ic">📋</span> Open script & steps</button>
        <button class="btn accent" data-quick-approve="${p.id}"><span class="ic">👍</span> Approve</button>
      </div>
    </div>`);
    hero.querySelector("[data-open]").addEventListener("click", () => openIdea(p.id));
    hero.querySelector("[data-quick-approve]").addEventListener("click", async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      await api.post(`/api/ideas/${p.id}/action`, { action: "approve" });
      toast("👍 Approved — open it to film"); renderToday();
    });
    frag.appendChild(hero);
  }

  // More ideas today
  if ((b.additional_ideas || []).length) {
    const c = el(`<div class="card list-card"><h3 style="padding:12px 0 4px">💡 More ideas for today</h3></div>`);
    b.additional_ideas.forEach((i) => c.appendChild(ideaRow(i)));
    frag.appendChild(c);
  }

  // Trends
  const trends = d.trends_worth_using || [];
  if (trends.length) {
    const c = el(`<details class="acc" open><summary>📈 Trends worth using today<span class="caret">›</span></summary><div class="acc-body"></div></details>`);
    const body = c.querySelector(".acc-body");
    trends.forEach((t) => body.appendChild(el(`<div style="padding:10px 0;border-top:1px solid var(--line)">
      <div style="font-weight:700">${esc(t.name)} <span class="chip plat">${platIcon(t.platform)} ${esc(t.platform)}</span></div>
      <p class="small soft" style="margin-top:4px">${esc(t.description || "")}</p>
      <p class="small"><b>Our version:</b> ${esc(t.adaptation || "")}</p>
      <p class="tiny muted">Best while: ${esc(t.expected_lifespan || "—")} · ${esc(t.difficulty || "—")} to film · ~${esc(t.est_filming_time || "—")}</p>
    </div>`)));
    frag.appendChild(c);
  }

  // Community + repurpose
  frag.appendChild(bulletCard("🤝 Quick wins today", "Small actions that grow your audience", b.community_engagement, "🐾"));
  frag.appendChild(bulletCard("♻️ Reuse what you already have", "Turn old clips into new posts", b.repurpose_ideas, "✂️"));

  view.innerHTML = "";
  view.appendChild(frag);
}
function bulletCard(title, sub, items, icon) {
  const c = el(`<div class="card"><h3>${title}</h3><p class="tiny muted" style="margin:2px 0 10px">${sub}</p><ul class="clean"></ul></div>`);
  const ul = c.querySelector("ul");
  (items || []).forEach((x) => ul.appendChild(el(`<li>${icon} ${esc(x)}</li>`)));
  if (!items || !items.length) ul.appendChild(el(`<li class="muted">Nothing here yet.</li>`));
  return c;
}

/* A short "from your employee" standup with what needs the owner. */
function standupCard(t) {
  const c = el(`<div class="card" style="border-color:var(--line-2)">
    <div style="display:flex;gap:10px;align-items:flex-start">
      <div class="avatar" style="background:var(--brand-tint)">🐶</div>
      <div style="flex:1">
        <div class="eyebrow">From your employee</div>
        <p class="small soft" style="margin-top:4px">${esc(t.message || "")}</p>
      </div>
    </div>
    <div class="btn-row" id="task-row" style="margin-top:12px"></div>
  </div>`);
  const row = c.querySelector("#task-row");
  (t.tasks || []).forEach((task) => {
    const btn = el(`<button class="btn subtle sm">${esc(task.label)} ›</button>`);
    btn.addEventListener("click", () => {
      if (task.key === "plan") return runResearch();
      switchTab(task.tab || "ideas");
    });
    row.appendChild(btn);
  });
  const ask = el(`<button class="btn ghost sm">💬 Ask me anything</button>`);
  ask.addEventListener("click", () => switchTab("chat"));
  row.appendChild(ask);
  return c;
}

/* =====================================================================
   CHAT — talk to your employee
   ===================================================================== */
const CHAT_SUGGESTIONS = [
  "Plan my week", "What should I post today?", "Write a caption about Maltipoos",
  "Draft 3 friendly replies to comments", "A customer asked if Yorkies are good for apartments",
];
async function renderChat() {
  view.innerHTML = "";
  const data = await api.get("/api/chat");
  view.appendChild(el(`<h1 class="view-title">Ask your employee</h1>
    <p class="view-sub">Tell me what you need — I can plan, write scripts and captions, draft comment replies, answer customer questions, and more.</p>`));
  if (!data.ai_enabled)
    view.appendChild(el(`<div class="banner info"><span class="bic">💡</span><div>Basic commands like <b>“Plan my week”</b> and <b>“Get today's plan”</b> work now. Add an API key for full back-and-forth conversation.</div></div>`));

  const log = el(`<div id="chat-log" class="stack" style="margin-bottom:14px"></div>`);
  view.appendChild(log);

  const chips = el(`<div class="chips" style="margin-bottom:10px" id="sugg"></div>`);
  CHAT_SUGGESTIONS.forEach((s) => { const b = el(`<button class="chip" style="cursor:pointer;border:none">${esc(s)}</button>`); b.addEventListener("click", () => send(s)); chips.appendChild(b); });
  view.appendChild(chips);

  const bar = el(`<div class="search" style="align-items:flex-end;gap:8px">
    <textarea id="chat-input" rows="1" placeholder="Type a message…" style="border:none;background:transparent;color:var(--ink);width:100%;outline:none;resize:none;font-size:0.95rem;max-height:120px"></textarea>
    <button class="btn primary sm" id="chat-send">Send</button>
  </div>`);
  view.appendChild(bar);
  view.appendChild(el(`<button class="btn ghost sm" id="chat-clear" style="margin-top:8px">Clear conversation</button>`));

  const input = $("#chat-input");
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(120, input.scrollHeight) + "px"; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); } });
  $("#chat-send").addEventListener("click", () => send(input.value));
  $("#chat-clear").addEventListener("click", async () => { await fetch("/api/chat", { method: "DELETE" }); renderChat(); });

  function paint(messages) {
    log.innerHTML = "";
    if (!messages.length)
      log.appendChild(el(`<div class="card center" style="padding:22px"><div style="font-size:1.8rem">🐶</div><p class="small muted" style="margin-top:8px">Hi! What can I help you with today? Try a suggestion below.</p></div>`));
    messages.forEach((mm) => log.appendChild(bubble(mm)));
    window.scrollTo(0, document.body.scrollHeight);
  }
  paint(data.messages);

  let busy = false;
  async function send(text) {
    text = (text || "").trim(); if (!text || busy) return;
    busy = true; input.value = ""; input.style.height = "auto";
    log.appendChild(bubble({ role: "user", content: text }));
    const thinking = el(`<div class="bubble bot"><span class="spinner" style="border-color:rgba(0,0,0,.2);border-top-color:var(--brand)"></span> thinking…</div>`);
    log.appendChild(thinking); window.scrollTo(0, document.body.scrollHeight);
    try {
      const r = await api.post("/api/chat", { message: text });
      thinking.remove();
      log.appendChild(bubble({ role: "assistant", content: r.reply, actions: r.actions }));
      window.scrollTo(0, document.body.scrollHeight);
      loadStatus();
    } catch (e) { thinking.remove(); log.appendChild(bubble({ role: "assistant", content: "Sorry, that didn't go through: " + e.message })); }
    finally { busy = false; }
  }
}
function bubble(m) {
  const isUser = m.role === "user";
  const actions = (m.actions && m.actions.length)
    ? `<div class="chips" style="margin-top:8px">${m.actions.map((a) => `<span class="chip ok">✅ ${esc(a)}</span>`).join("")}</div>` : "";
  return el(`<div class="bubble ${isUser ? "me" : "bot"}">${nl(m.content)}${actions}</div>`);
}

/* =====================================================================
   IDEAS
   ===================================================================== */
const STATUS_SEGS = [
  { k: "", label: "All" },
  { k: "New", label: "Needs your OK" },
  { k: "Approved", label: "Approved" },
  { k: "Ready to Film", label: "To film" },
  { k: "Published", label: "Posted" },
];
async function renderIdeas() {
  view.innerHTML = "";
  const state = { q: "", status: "" };
  view.appendChild(el(`<h1 class="view-title">Idea library</h1><p class="view-sub">Everything your employee has come up with. Tap any idea to see the full plan.</p>`));

  const bar = el(`<div class="filters">
    <div class="search">🔎<input id="f-q" placeholder="Search ideas…"></div>
    <button class="btn sm" id="f-new"><span class="ic">＋</span> New</button>
  </div>`);
  const seg = el(`<div class="seg">${STATUS_SEGS.map((s, i) => `<button data-k="${s.k}" class="${i === 0 ? "active" : ""}">${s.label}</button>`).join("")}</div>`);
  const list = el(`<div class="card list-card" id="idea-list" style="margin-top:12px"></div>`);
  view.append(bar, seg, list);

  async function load() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.status) params.set("status", state.status);
    list.innerHTML = "";
    const ideas = await api.get("/api/ideas?" + params);
    if (!ideas.length) { list.innerHTML = `<p class="muted center" style="padding:24px">No ideas here yet.</p>`; return; }
    ideas.forEach((i) => list.appendChild(ideaRow(i)));
  }
  let d; $("#f-q").addEventListener("input", (e) => { state.q = e.target.value; clearTimeout(d); d = setTimeout(load, 250); });
  seg.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return;
    seg.querySelectorAll("button").forEach((x) => x.classList.remove("active")); b.classList.add("active");
    state.status = b.dataset.k; load(); });
  $("#f-new").addEventListener("click", newIdeaForm);
  load();
}

function newIdeaForm() {
  const cats = Object.keys(CAT_ICON), plats = Object.keys(PLAT_ICON);
  openDrawer(`<h2>New idea</h2><p class="tiny muted" style="margin-bottom:12px">Jot a rough idea — you can generate the full script after.</p>
    <div class="form-grid">
      <div class="fld full"><label>Title</label><input id="n-title" placeholder="e.g. Yorkie meets a giant toy"></div>
      <div class="fld"><label>Platform</label><select id="n-plat">${plats.map((p) => `<option>${p}</option>`).join("")}</select></div>
      <div class="fld"><label>Category</label><select id="n-cat">${cats.map((c) => `<option>${c}</option>`).join("")}</select></div>
      <div class="fld"><label>Video format</label><select id="n-fmt">${FORMATS.map((f) => `<option value="${f}">${esc(fmtLabel(f))}</option>`).join("")}</select></div>
      <div class="fld"><label>Breed (optional)</label><input id="n-breed" placeholder="Yorkie"></div>
      <div class="fld"><label>Difficulty</label><select id="n-diff"><option>Easy</option><option selected>Medium</option><option>Hard</option></select></div>
      <div class="fld full"><label>What happens in the video?</label><textarea id="n-concept"></textarea></div>
      <div class="fld full"><label>Opening line / hook (optional)</label><input id="n-hook"></div>
    </div>
    <button class="btn primary block" id="n-save" style="margin-top:14px">Create idea</button>`);
  $("#n-save").addEventListener("click", async () => {
    const title = $("#n-title").value.trim(); if (!title) return toast("Give it a title first");
    const idea = await api.post("/api/ideas", {
      title, platform: $("#n-plat").value, category: $("#n-cat").value, format: $("#n-fmt").value,
      breed: $("#n-breed").value, difficulty: $("#n-diff").value, concept: $("#n-concept").value,
      hook: $("#n-hook").value,
    });
    toast("Idea created"); openIdea(idea.id);
  });
}

/* =====================================================================
   IDEA DRAWER (the full plan + all controls)
   ===================================================================== */
const BREEDS = ["Maltipoo","Yorkie","Pomeranian","Poodle","Cavapoo","Chorkie","Miniature Schnauzer","Chihuahua","Shih Tzu","Bichon"];

async function openIdea(id) {
  const i = await api.get(`/api/ideas/${id}`);
  const has = !!i.script;
  const reload = () => openIdea(id);

  const comp = i.compliance && i.compliance.summary && (i.compliance.issues || []).length
    ? `<div class="banner warn"><span class="bic">⚠️</span><div><b>Quick check:</b> ${esc(i.compliance.summary)}
        <ul class="clean tiny" style="margin-top:5px">${i.compliance.issues.map((x, n) => `<li>${esc(x)}${i.compliance.fixes && i.compliance.fixes[n] ? " — <i>" + esc(i.compliance.fixes[n]) + "</i>" : ""}</li>`).join("")}</ul></div></div>`
    : (i.compliance && i.compliance.passed ? `<div class="banner good"><span class="bic">✅</span> Passed the brand safety check.</div>` : "");

  const packageBlock = has ? `
    ${acc("🎬 The video — what to film", `
      ${field("First thing on screen", i.first_second_visual)}
      ${i.hook ? `<div class="quote">“${esc(i.hook)}”</div>` : ""}
      ${copyField("Full script", i.script)}
      ${field("How to film it (step by step)", i.filming_instructions)}
      ${field("Text on screen", i.on_screen_text)}
      <div class="chips" style="margin-top:8px">
        ${i.suggested_length ? `<span class="chip">⏱ ${esc(i.suggested_length)}</span>` : ""}
      </div>
      ${field("How to edit", i.editing_instructions)}
      ${field("Music / sound", i.audio_direction)}
    `, true)}
    ${acc("📝 The caption & hashtags — copy & paste", `
      ${copyField("Caption", i.caption)}
      ${copyField("Hashtags", i.hashtags)}
      ${copyField("Post title", i.platform_title)}
      ${copyField("YouTube Shorts title", i.youtube_title)}
      ${copyField("Cover / thumbnail text", i.cover_text)}
      ${copyField("Pinned comment", i.pinned_comment)}
      ${field("Call to action", i.call_to_action)}
    `)}
    ${acc("🔁 Backups & no-talking version", `
      ${field("Backup hook", i.backup_hook)}
      ${copyField("Backup caption", i.backup_caption)}
      ${field("Film it without talking", i.no_speak_version)}
    `)}
  ` : `<div class="card center" style="margin:0 0 12px">
      <p class="muted small" style="margin-bottom:12px">No script yet for this idea.</p>
      <button class="btn primary block" id="build-pkg"><span class="ic">✍️</span> Write the full script & filming plan</button>
    </div>`;

  openDrawer(`
    <div style="display:flex;gap:12px;align-items:flex-start">
      <div class="avatar" style="width:46px;height:46px;font-size:1.3rem">${catIcon(i.category)}</div>
      <div style="flex:1;min-width:0"><h2 style="font-size:1.25rem">${esc(i.title)}</h2>
      <div style="margin-top:6px">${chips(i)}</div></div>
    </div>
    <div class="chips" style="margin-top:10px">
      <span class="chip status">${esc(friendlyStatus(i.status))}</span>
      <span class="chip">📈 ${i.virality_score}/10 reach</span>
      <span class="chip">🛎️ ${i.conversion_value}/10 buyers</span>
      <span class="chip">${esc(i.difficulty)} to film</span>
    </div>
    ${i.concept ? `<p class="small soft" style="margin-top:12px">${nl(i.concept)}</p>` : ""}
    ${comp}

    <div class="btn-row" style="margin:14px 0">
      <button class="btn accent" data-act="approve"><span class="ic">👍</span> Approve</button>
      <button class="btn" data-act="mark_filmed"><span class="ic">🎥</span> Filmed it</button>
      <button class="btn" data-act="mark_published"><span class="ic">🚀</span> Posted it</button>
      <button class="btn danger" data-act="reject"><span class="ic">🗑</span> Skip</button>
    </div>

    ${has ? `<div class="card" style="margin:0 0 12px;padding:14px">
      <div class="tiny muted" style="margin-bottom:8px;font-weight:700;text-transform:uppercase;letter-spacing:.04em">Want it different?</div>
      <div class="btn-row">
        <button class="btn subtle sm" data-act="shorter">Shorter</button>
        <button class="btn subtle sm" data-act="funnier">Funnier</button>
        <button class="btn subtle sm" data-act="more_educational">More helpful</button>
        <button class="btn subtle sm" data-act="regenerate">Fresh version</button>
        <select id="chg-breed" class="sm"><option value="">Different breed…</option>${BREEDS.map((b) => `<option>${b}</option>`).join("")}</select>
        <select id="chg-fmt" class="sm"><option value="">Switch format…</option>${FORMATS.map((f) => `<option value="${f}">${esc(fmtLabel(f))}</option>`).join("")}</select>
      </div></div>` : ""}

    ${packageBlock}

    ${acc("📅 Schedule & who films it", `
      <div class="form-grid">
        <div class="fld"><label>Assigned to</label><input id="a-emp" value="${esc(i.assigned_employee || "")}" placeholder="Name"></div>
        <div class="fld"><label>Film on</label><input id="a-rec" type="date" value="${i.recording_date || ""}"></div>
        <div class="fld"><label>Post on</label><input id="a-pub" type="date" value="${i.publishing_date || ""}"></div>
        <div class="fld"><label>Reuse after</label><input id="a-reuse" type="date" value="${i.suggested_reuse_date || ""}"></div>
      </div>
      <button class="btn block sm" id="save-sched" style="margin-top:10px">Save schedule</button>
    `)}

    ${acc("📊 Add the numbers (after you post)", `
      <p class="tiny muted" style="margin-bottom:10px">Fill in what you can — shares, saves, comments and store calls matter most. The more you log, the smarter tomorrow's ideas get.</p>
      ${perfForm(i)}
      <button class="btn accent block" id="save-perf" style="margin-top:10px">Save the numbers</button>
    `)}

    ${acc("🗒 Notes", `
      <div class="val" style="margin-bottom:10px">${i.notes ? nl(i.notes) : '<span class="muted">No notes yet.</span>'}</div>
      <textarea id="fb-note" placeholder="Add a note for your team…"></textarea>
      <button class="btn block sm" id="save-note" style="margin-top:8px">Save note</button>
    `)}
  `);

  wireCopy();
  const bp = $("#build-pkg");
  if (bp) bp.addEventListener("click", async () => { bp.disabled = true; bp.innerHTML = '<span class="spinner"></span> Writing…'; await api.post(`/api/ideas/${id}/package`); toast("Script ready"); reload(); });

  document.querySelectorAll("[data-act]").forEach((btn) => btn.addEventListener("click", async () => {
    const act = btn.dataset.act; let value = "";
    if (act === "reject" && !confirm("Skip this idea? It moves to the archive.")) return;
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
    toast("Saved to your calendar");
  });
  $("#save-note")?.addEventListener("click", async () => { const n = $("#fb-note").value.trim(); if (!n) return; await api.post(`/api/ideas/${id}/feedback`, { note: n }); toast("Note saved"); reload(); });
  $("#save-perf")?.addEventListener("click", async () => {
    const body = {};
    document.querySelectorAll("[data-perf]").forEach((n) => { if (n.value !== "") body[n.dataset.perf] = n.type === "number" ? +n.value : n.value; });
    if (!Object.keys(body).length) return toast("Enter at least one number");
    await api.post(`/api/ideas/${id}/performance`, body); toast("📊 Numbers saved — thank you!"); reload(); loadStatus();
  });
}
const ACT_MSG = { approve: "👍 Approved", mark_filmed: "🎥 Marked as filmed", mark_published: "🚀 Marked as posted", reject: "Skipped", shorter: "Made it shorter", funnier: "Made it funnier", more_educational: "Made it more helpful", regenerate: "Fresh version ready" };
function friendlyStatus(s) { return ({ New: "Needs your OK", "Ready to Film": "Ready to film", Published: "Posted" }[s]) || s; }

function acc(title, body, open) {
  return `<details class="acc" ${open ? "open" : ""}><summary>${title}<span class="caret">›</span></summary><div class="acc-body">${body}</div></details>`;
}
function field(label, val) { return val ? `<div class="fld"><label>${label}</label><div class="val">${nl(val)}</div></div>` : ""; }
function copyField(label, val) {
  if (!val) return "";
  return `<div class="fld copyfield"><label>${label}</label><div class="val">${nl(val)}</div>
    <button class="btn subtle sm copybtn" data-copy="${esc(val)}">Copy</button></div>`;
}
function wireCopy() {
  $("#drawer-body").querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => {
    navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied!"; toast("Copied to clipboard");
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

/* =====================================================================
   CALENDAR (Plan)
   ===================================================================== */
async function renderCalendar() {
  const events = await api.get("/api/calendar");
  view.innerHTML = "";
  view.appendChild(el(`<h1 class="view-title">Your plan</h1><p class="view-sub">Your filming and posting schedule. Let me lay out a whole week for you.</p>`));

  const planCard = el(`<div class="card" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <div style="flex:1;min-width:160px"><b>Plan my week</b><div class="tiny muted">I'll pick your best ideas, write the scripts, and schedule ${""}them.</div></div>
    <select id="pw-count" class="sm"><option value="3">3 posts</option><option value="5" selected>5 posts</option><option value="7">7 posts</option></select>
    <button class="btn primary sm" id="pw-go"><span class="ic">🗓️</span> Plan it</button>
  </div>`);
  view.appendChild(planCard);
  $("#pw-go").addEventListener("click", async () => {
    const btn = $("#pw-go"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Planning…';
    try { const r = await api.post("/api/plan/week", { posts: +$("#pw-count").value }); toast(`🗓️ Scheduled ${r.count} posts`); renderCalendar(); }
    catch (e) { toast("Couldn't plan: " + e.message); btn.disabled = false; btn.innerHTML = "🗓️ Plan it"; }
  });

  if (!events.length) {
    view.appendChild(el(`<div class="card empty"><div class="big">📅</div><h2>Nothing scheduled yet</h2>
      <p>Tap <b>Plan it</b> above and I'll fill your week — or set dates on any idea.</p></div>`));
    return;
  }
  const by = {}; events.forEach((e) => (by[e.date] = by[e.date] || []).push(e));
  const wrap = el(`<div class="stack"></div>`);
  Object.keys(by).sort().forEach((date) => {
    const day = el(`<div class="cal-day"><div class="d">${fmtDate(date)}</div></div>`);
    by[date].forEach((e) => { const ev = el(`<div class="cal-ev ${e.type}">${e.type === "record" ? "🎥 Film" : "🚀 Post"}: ${esc(e.title)}</div>`); ev.addEventListener("click", () => openIdea(e.idea_id)); day.appendChild(ev); });
    wrap.appendChild(day);
  });
  view.appendChild(wrap);
}
function fmtDate(s) { try { return new Date(s + "T00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }); } catch { return s; } }

/* =====================================================================
   RESULTS (analytics + posted)
   ===================================================================== */
async function renderResults() {
  const [a, posted] = await Promise.all([api.get("/api/analytics"), api.get("/api/ideas?status=Published")]);
  view.innerHTML = "";
  view.appendChild(el(`<h1 class="view-title">Results & what's working</h1><p class="view-sub">Log the numbers on your posts and your employee learns what to make more of.</p>`));

  if (a.source === "inferred")
    view.appendChild(el(`<div class="banner info"><span class="bic">💡</span><div>General guidance for now. Log a few posts (open any posted idea → <b>Add the numbers</b>) to unlock advice tailored to your audience.</div></div>`));

  const c = el(`<div class="card"><div class="eyebrow">What's working</div><h3 style="margin:4px 0 8px">${esc(a.headline || "Keep posting and logging")}</h3></div>`);
  const put = (title, items) => { if (items && items.length) c.appendChild(el(`<div class="fld"><label>${title}</label><ul class="clean small">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`)); };
  put("Do more of this", a.recommendations);
  put("Best hooks", a.best_hooks);
  put("Formats that win", a.winning_formats);
  put("Breeds people love", a.best_breeds);
  put("Drives comments", a.topics_driving_comments);
  put("Brings people to the store", a.topics_driving_inquiries);
  put("Series to keep", a.series_to_continue);
  put("Worth retesting", a.ideas_to_retest);
  view.appendChild(c);

  const pc = el(`<div class="card list-card"><h3 style="padding:12px 0 4px">🚀 Posted content</h3></div>`);
  if (!posted.length) pc.appendChild(el(`<p class="muted center" style="padding:20px">Nothing posted yet. When you post, open the idea and tap <b>Posted it</b>.</p>`));
  posted.forEach((i) => pc.appendChild(ideaRow(i)));
  view.appendChild(pc);
}

/* =====================================================================
   MORE  (+ sub views)
   ===================================================================== */
async function renderMore() {
  view.innerHTML = "";
  view.appendChild(el(`<h1 class="view-title">More</h1><p class="view-sub">Your library, settings, and how things work.</p>`));
  const items = [
    ["🔁", "Recurring series", "Repeat formats fans follow", () => subView("Recurring series", renderSeries)],
    ["📈", "Trend research", "What your employee found & when", () => subView("Trend research", renderTrends)],
    ["🎥", "Inspiration", "Creators & formats we adapt", () => subView("Inspiration", renderInspiration)],
    ["⚙️", "Brand rules", "The rules your employee follows", () => subView("Brand rules", renderRules)],
    ["📜", "Activity log", "Every research run", () => subView("Activity log", renderLogs)],
    ["❓", "How this works", "Setup & tips", () => subView("How this works", renderHelp)],
  ];
  const grid = el(`<div class="menu-grid"></div>`);
  items.forEach(([ic, t, d, fn]) => { const card = el(`<button class="menu-card"><div class="mic">${ic}</div><div class="mt">${t}</div><div class="md">${d}</div></button>`); card.addEventListener("click", fn); grid.appendChild(card); });
  view.appendChild(grid);
}
function subView(title, fn) {
  view.innerHTML = "";
  const back = el(`<button class="btn ghost sm" style="margin-bottom:10px">‹ More</button>`);
  back.addEventListener("click", () => switchTab("more"));
  view.appendChild(back);
  view.appendChild(el(`<h1 class="view-title" style="margin-bottom:14px">${title}</h1>`));
  const holder = el(`<div id="sub"></div>`); view.appendChild(holder);
  fn(holder);
}

async function renderSeries(root) {
  const rows = await api.get("/api/series");
  const g = el(`<div class="stack"></div>`);
  rows.forEach((s) => g.appendChild(el(`<div class="card">
    <h3>${esc(s.name)} ${s.active ? "" : '<span class="chip">paused</span>'}</h3>
    <div class="fld"><label>Format</label><div class="val">${esc(s.repeatable_format)}</div></div>
    <div class="fld"><label>Opening hook</label><div class="val">${esc(s.opening_hook)}</div></div>
    <p class="tiny muted">${esc(s.publishing_frequency)} · ${esc(s.business_goal)}</p>
  </div>`)));
  root.appendChild(g);
}
async function renderTrends(root) {
  const rows = await api.get("/api/trends");
  if (!rows.length) { root.appendChild(el(`<div class="card empty"><div class="big">📈</div><p class="muted">No research yet — tap <b>Get today's plan</b>.</p></div>`)); return; }
  rows.forEach((t) => root.appendChild(el(`<div class="card">
    <h3>${esc(t.name)} <span class="chip plat">${platIcon(t.platform)} ${esc(t.platform)}</span> ${t.source === "inferred" ? '<span class="chip">starter</span>' : ""}</h3>
    <p class="tiny muted">Found ${esc(t.date_discovered)} · best while ${esc(t.expected_lifespan || "—")} · ${esc(t.status)}</p>
    <p class="small" style="margin-top:6px">${esc(t.description)}</p>
    <div class="fld"><label>Our version</label><div class="val">${esc(t.adaptation)}</div></div>
  </div>`)));
}
async function renderInspiration(root) {
  const rows = await api.get("/api/competitors");
  root.appendChild(el(`<div class="banner info"><span class="bic">🎥</span> Studied for <b>why</b> they work — never copied. We build original puppy versions.</div>`));
  rows.forEach((x) => root.appendChild(el(`<div class="card">
    <h3>${esc(x.name)}</h3>
    <div class="chips" style="margin:6px 0"><span class="chip plat">${esc(x.platform)}</span><span class="chip">${esc(x.format_type)}</span></div>
    <div class="fld"><label>Why it works</label><div class="val">${esc(x.what_works)}</div></div>
    <div class="fld"><label>Our adaptation</label><div class="val">${esc(x.adaptation_idea)}</div></div>
  </div>`)));
}
async function renderRules(root) {
  const r = await api.get("/api/brand-rules");
  root.appendChild(el(`<p class="small muted" style="margin-bottom:12px">Your employee follows these. Edit a value and save — it applies on the next plan.</p>`));
  Object.keys(r).forEach((key) => {
    const val = JSON.stringify(r[key], null, 2);
    const box = el(`<div class="card"><div class="fld"><label>${esc(key.replace(/_/g, " "))}</label>
      <textarea style="width:100%;min-height:${Math.min(220, 60 + val.length / 3)}px;font-family:ui-monospace,monospace;font-size:0.82rem">${esc(val)}</textarea></div>
      <button class="btn sm">Save</button></div>`);
    box.querySelector("button").addEventListener("click", async () => {
      let parsed; try { parsed = JSON.parse(box.querySelector("textarea").value); } catch { return toast("That isn't valid — check quotes/commas"); }
      await api.put("/api/brand-rules", { key, value: parsed }); toast(`Saved ${key.replace(/_/g, " ")}`);
    });
    root.appendChild(box);
  });
}
async function renderLogs(root) {
  const rows = await api.get("/api/logs");
  if (!rows.length) { root.appendChild(el(`<p class="muted">No runs yet.</p>`)); return; }
  rows.forEach((l) => root.appendChild(el(`<div class="card" style="padding:12px 16px">
    <div class="chips"><span class="chip ${l.status === "ok" ? "ok" : ""}">${esc(l.status)}</span>
    <span class="chip">${esc(l.run_type)}</span><span class="chip">${esc(l.source)}</span></div>
    <p class="small" style="margin-top:6px">${esc(l.message)}</p>
    <p class="tiny muted">${esc(l.created_at)} · ${l.trends_found} trends · ${l.ideas_created} ideas</p>
  </div>`)));
}
async function renderHelp(root) {
  const s = await api.get("/api/status").catch(() => ({}));
  root.appendChild(el(`<div class="card">
    <h3>How your social media employee works</h3>
    <ol class="clean small" style="margin-top:8px">
      <li>Each morning (or when you tap <b>Get today's plan</b>) it researches what's trending.</li>
      <li>It hands you the single best video to film today, with the full script, filming steps, caption, hashtags, and titles.</li>
      <li>You film it, tap <b>Approve</b>, and post it.</li>
      <li>After a day or two, open the post and tap <b>Add the numbers</b>. It learns and gets better.</li>
    </ol>
  </div>
  <div class="card">
    <h3>Live research vs starter ideas</h3>
    <p class="small soft" style="margin-top:6px">Right now you're in <b>${s.ai_enabled ? "Live research" : "Starter ideas"}</b> mode.
    ${s.ai_enabled ? "It's using live web research." : "It's using dependable evergreen ideas. To switch on live daily trend research, add an Anthropic API key to your <kbd>.env</kbd> file and restart. See the README for step-by-step help."}</p>
  </div>
  <div class="card">
    <h3>Tips</h3>
    <ul class="clean small" style="margin-top:6px">
      <li>Keep videos short (10–45 seconds) and end with a friendly reason to visit.</li>
      <li>Log <b>shares, saves and store calls</b> — they matter more than likes.</li>
      <li>Not feeling an idea? Open it and tap <b>Shorter</b>, <b>Funnier</b>, or <b>Fresh version</b>.</li>
    </ul>
  </div>`));
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
