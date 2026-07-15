# Architecture & Implementation Plan

This is the plan the build followed (spec: *Development Process*). It records the
architecture decision, the services/jobs involved, and the MVP-vs-later split.

## 1. Requirements in one line
Build a proactive, research-driven AI "social media employee" for Sugar Sweet
Georgia Puppies that researches current short-form trends daily, turns them into
brand-safe, filmable ideas + complete filming packages, runs an approval and
scheduling workflow, records performance, and learns from results — all
maintainable by one owner/manager.

## 2. Chosen architecture
A single Python process is the whole product, so one person can run it:

- **FastAPI** — API + serves the dashboard. Async, self-documenting, tiny.
- **SQLite + SQLAlchemy** — zero-config persistent memory (trends, ideas,
  briefings, performance, series, brand rules, logs). This *is* the content
  database and the agent's memory that prevents repetition.
- **Anthropic Claude (`claude-opus-4-8`)** — the single AI brain. Seven
  specialist "hats" (trend researcher, strategist, scriptwriter, caption/hashtag
  writer, compliance reviewer, performance analyst, briefing generator) each
  load their own **editable prompt file** and are orchestrated into one employee.
- **Web Search server tool** (`web_search_20260209`) — platform-approved, no
  scraping. Used by the trend researcher to find what is current.
- **APScheduler** — runs the daily research + briefing job at a configured time.
- **Vanilla HTML/CSS/JS dashboard** — mobile-friendly, no build step.

### Why not heavier options
No React build pipeline, no Postgres, no message queue, no separate worker — all
of that adds ops burden a single owner shouldn't carry. Everything scales to the
real workload (a few dozen posts a week) comfortably on SQLite.

### Multi-agent, one employee
The seven agents are plain functions sharing one Claude client and a shared brand
context. The owner experiences one coordinated employee (the daily briefing); the
agents are an implementation detail. Prompts live in `prompts/*.md` so behaviour
is tuned without code changes.

### Graceful degradation (honesty)
Without an API key the app still runs the full end-to-end workflow using a
clearly-labelled **offline heuristic** (`app/ai/offline.py`). Every offline
output is marked `source="inferred"` and surfaced in the UI as *inferred, not
confirmed live research*. It is never presented as a real platform-wide trend —
this satisfies the spec's "label inferred recommendations" and "don't fake a
demo" requirements while keeping the product usable before a key is added.

## 3. APIs / services / jobs
- **Anthropic Messages API** (adaptive thinking, effort, web search server tool,
  streaming) — the only external service required.
- **Scheduled job:** daily research + briefing (`app/scheduler.py`).
- **Manual job:** "Run research now" button / `python run.py --research`.
- No third-party platform scraping — deliberately avoided per the spec.

## 4. Database schema (see `app/models.py`)
`trends`, `ideas` (the content database + full filming package + status +
reuse/dedup fields), `briefings`, `performance`, `series`, `brand_rules`
(editable key→JSON config), `research_log`, `competitors`.

## 5. Workflows
- **Trend research** → save (with discovery date + source label + auto-expiry).
- **Content generation** → dedup-checked ideas from trends + series + past
  performance.
- **Approval** → approve / reject / revise / regenerate / shorten / funnier /
  educational / change breed / change platform / mark filmed / mark published.
- **Analytics** → analyst weights watch-time, shares, saves, comments, and store
  inquiries over likes; feeds the next day's strategist.
- **Duplicate detection** → concept fingerprint blocks repeats unless retesting.

## 6. MVP vs. later
**MVP (built here) — a real end-to-end loop:**
1. research/receive trends → 2. save relevant trends → 3. generate brand ideas →
4. select the strongest daily recommendation → 5. produce a complete filming
package → 6. approve/reject → 7. save to calendar + database → 8. record
publishing + performance → 9. use results to improve future recommendations.

**Later improvements (not required for MVP):**
- Direct platform API integrations to auto-import metrics (Instagram/TikTok/
  YouTube) once the business authorizes them.
- Multi-user auth + roles for a team.
- Automated A/B hook testing and richer time-series analytics/charts.
- Auto-scheduling/publishing via platform schedulers.
- Vector search over the idea database for smarter similarity/dedup.
- Image/thumbnail generation for covers.
