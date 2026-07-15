# 🐶 Sugar Sweet Georgia Puppies — AI Social Media Employee

A proactive, research-driven AI social media employee for **Sugar Sweet Georgia
Puppies**, a small-breed puppy boutique in Lawrenceville, Georgia.

It behaves like an experienced full-time social media strategist, trend
researcher, short-form video producer, scriptwriter, copywriter, and performance
analyst. Every morning it researches what's working right now, turns that into
specific videos the store can actually film, writes the complete filming package
(hook, script, shot list, captions, hashtags, titles, CTA, and a no-talking
version), runs an approval + scheduling workflow, records performance, and learns
from results to improve tomorrow's recommendations.

> It is designed to be run and maintained by **one business owner or manager** —
> a single Python process, a single SQLite file, a single AI model.

---

## What it does

- **Talks with you like a coworker (Ask tab).** Tell it what you need in plain
  English — "plan my week," "write a caption about Maltipoos," "draft three
  friendly replies to comments," "a customer asked if Yorkies are good for
  apartments" — and it either answers on the spot or *does the work* (it can
  research, plan, create ideas, and write full scripts through the chat).
- **Plans your whole week.** One tap lays out a real day-by-day posting schedule
  — picking your best ideas, writing their scripts, and filling your calendar.
- **Gives you a morning standup.** The Today screen opens with a short note from
  your employee — what's ready and what needs you (approvals, videos to film,
  numbers to log) — with buttons that take you straight there.
- **Researches trends daily** across TikTok, Instagram Reels, YouTube Shorts,
  puppy/small-dog content, viral small- and local-business content, hooks,
  trending questions, seasonal + Georgia-local moments — using Claude's
  platform-approved web search (no scraping). Each trend records its discovery
  date and is auto-expired so old trends aren't treated as current.
- **Generates brand-specific ideas** — a balanced mix of Viral Entertainment,
  Emotional, Educational, Local, Behind-the-Scenes, and Conversion content, only
  featuring breeds the store carries, prioritised by reach, effort, business
  value, and likelihood of success.
- **Produces a complete daily briefing** — trends worth using, the single best
  video to film today (with the full filming package), backup ideas, community
  engagement tasks, and content to repurpose.
- **Writes natural, non-corporate scripts** — hooks that create instant
  curiosity/emotion/surprise, never using banned openers, with a filmable
  shot-by-shot plan and a no-talking alternative.
- **Runs the workflow** — approve, reject, request a revision, generate another
  version, shorten, make funnier / more educational, change the featured breed
  or platform, mark filmed/published, and log performance.
- **Analyzes performance** the right way — weighting watch time, completion,
  shares, saves, meaningful comments, profile actions, and store inquiries over
  likes — and personalizes future recommendations as data accumulates.
- **Remembers everything** — a searchable content database with statuses and a
  duplicate detector so it doesn't recommend the same concept twice.
- **Maintains recurring series** the audience can recognise and follow.

Puppy safety and wellbeing always come before content performance. The agent
never fabricates stories or testimonials, gives medical advice, claims a breed is
completely hypoallergenic, posts prices without approval, or guarantees virality.

---

## Quick start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
#   Open .env and paste your Anthropic API key (see below). This enables live
#   daily trend research. Without it the app still runs, using a clearly-labeled
#   offline heuristic instead of live research.

# 3. Run
python run.py
#   Open http://localhost:8000
```

Then click **“Run research now”** in the top bar to have your social media
employee research today's trends and build a filming plan. (With the scheduler
on, it also does this automatically each morning.)

Run one research cycle from the command line (e.g. for cron), no web server:

```bash
python run.py --research
```

Verify the full pipeline end-to-end at any time:

```bash
python tests/test_e2e.py        # or: python -m pytest -q
```

---

## Getting an Anthropic API key

1. Create an account at <https://console.anthropic.com/>.
2. Create an API key and paste it into `.env` as `ANTHROPIC_API_KEY=...`.
3. Restart the app. The status pill in the top bar will switch from
   **“Inferred (offline) mode”** to **“Live research”**.

The app uses `claude-opus-4-8` by default (configurable). Costs are usage-based;
a daily research + generation run is a handful of model calls.

---

## Environment variables

All settings live in `.env` (see `.env.example` for the annotated list):

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(empty)_ | Enables live research + generation. Empty ⇒ labeled offline mode. |
| `CLAUDE_MODEL` | `claude-opus-4-8` | Model ID. `claude-sonnet-5` (cheaper) / `claude-haiku-4-5` (fastest) also work. |
| `CLAUDE_EFFORT` | `high` | Reasoning effort: `low`/`medium`/`high`/`xhigh`/`max`. |
| `TREND_SEARCH_MAX_USES` | `6` | Max web searches per research pass. |
| `DATABASE_URL` | `sqlite:///data/sugarsweet.db` | Database location. |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Web server bind. |
| `DAILY_RUN_ENABLED` | `true` | Turn the daily scheduler on/off. |
| `DAILY_RUN_TIME` | `07:00` | Local time for the daily research job. |
| `TIMEZONE` | `America/New_York` | Timezone for the scheduler. |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |

---

## The dashboard

Mobile-friendly and theme-aware. Tabs:

- **Today's Briefing** — the morning report + the best video to film today with
  its full filming package, trends worth using, backup ideas, community tasks,
  and repurpose ideas.
- **Idea Database** — searchable/filterable content database; open any idea for
  the full package and every control; add ideas manually.
- **Approvals** — scripts waiting for approval or revision.
- **Calendar** — scheduled recordings and publishes.
- **Published** — everything live, with performance logging.
- **Analytics** — the analyst's personalized guidance.
- **Series** — recurring, recognisable series definitions.
- **Trends** — the dated research log.
- **Inspiration** — competitor/format inspiration (studied, never copied).
- **Brand Rules** — edit the AI's standing instructions (voice, avoid-list,
  breeds, priority weights…). Changes take effect on the next run.
- **Activity** — the audit log of research/generation runs.

---

## How the AI is structured

One employee, seven specialist "hats", each with its own **editable prompt file**
in `prompts/` (so you can tune behaviour without touching code):

| Prompt file | Role |
|---|---|
| `trend_researcher.md` | Finds current trends via web search; rejects weak/unsafe ones. |
| `content_strategist.md` | Turns trends + series + performance into a ranked, deduped idea slate. |
| `scriptwriter.md` | Writes the complete filming package for the chosen idea. |
| `caption_hashtag_writer.md` | Refines captions + strategic hashtags. |
| `brand_compliance_reviewer.md` | Brand-safety gate before the owner sees anything. |
| `performance_analyst.md` | Turns metrics into personalized guidance. |
| `daily_briefing_generator.md` | Assembles the human daily briefing. |
| `_brand.md` | Shared brand context injected into every agent. |

The orchestration lives in `app/services/briefing.py` (`run_daily_workflow`).

---

## Project structure

```
run.py                     # entrypoint (web server, or --research one-shot)
requirements.txt
.env.example               # copy to .env
PLAN.md                    # architecture + MVP/later plan
app/
  config.py                # all settings in one place
  database.py              # SQLite engine + session + init
  models.py                # schema: trends, ideas, briefings, performance, series, rules, logs
  seed.py                  # default brand rules, recurring series, inspiration
  schemas.py               # API request bodies
  main.py                  # FastAPI app (API + dashboard)
  scheduler.py             # daily research job (APScheduler)
  ai/
    client.py              # Claude wrapper (web search, JSON, streaming, fallback)
    prompts.py             # loads + formats editable prompt files
    agents.py              # the 7 specialist agents (with offline fallbacks)
    offline.py             # clearly-labeled inferred heuristics (no key needed)
  services/
    briefing.py            # the daily end-to-end workflow orchestrator
    trends.py              # save + expire trends
    ideas.py               # create/score ideas, build filming packages, variants
    dedup.py               # concept fingerprinting + duplicate detection
    analytics.py           # build rows + run the analyst
  routes/
    api.py                 # every API endpoint + all workflow controls
    serializers.py         # ORM -> JSON
prompts/                   # 7 editable agent prompts + shared brand context
static/                    # dashboard (index.html, style.css, app.js)
tests/test_e2e.py          # end-to-end smoke test of the real workflow
data/                      # SQLite lives here (gitignored)
```

---

## Data & privacy

- All data stays in your local SQLite file (`data/sugarsweet.db`).
- Trend research is done through Claude's approved web search — no scraping of
  platforms and nothing that violates platform terms.
- When live data isn't available, recommendations are clearly labeled as
  **inferred**, never presented as confirmed platform-wide trends.

## Deployment notes

- It's a single process — run it on any small VM, `python run.py`, behind a
  reverse proxy if you want HTTPS.
- For automatic daily runs, keep `DAILY_RUN_ENABLED=true`, or disable it and
  drive `python run.py --research` from your own cron.
- Back up `data/sugarsweet.db` to keep your idea database and history.

See **PLAN.md** for the architecture decisions and the MVP-vs-later roadmap.
