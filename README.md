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
#   Dashboard:          http://localhost:8000
#   Lead & Floor Board: http://localhost:8000/board   (wall-TV display; mock feed by default)
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
| `BOARD_FEED_URL` | _(empty)_ | JSON feed for the Lead & Floor Board (an n8n webhook). Empty ⇒ dev/mock mode. |
| `BOARD_DEV_MODE` | auto | Force mock feed on/off. Auto = on when `BOARD_FEED_URL` is empty. |
| `BOARD_STORE_NAME` | business name | Store name in the board header. |
| `BOARD_POLL_SECONDS` | `15` | How often the board re-polls the feed. |
| `BOARD_STALE_SECONDS` | `90` | No successful poll within this ⇒ "connection lost". |
| `BOARD_FEED_TIMEOUT` | `10` | Upstream feed timeout (seconds). |

---

## The Lead & Floor Board (wall-display at `/board`)

A separate full-screen board for a wall-mounted TV in the showroom, built so
staff can tell from 10–15 ft away who needs a callback, which appointments are
about to arrive (or have gone no-show), and how long walk-ins have been waiting.
Open it at **`http://localhost:8000/board`**. Designed for 1920×1080 landscape,
no touch, no glare-heavy dark screen — light background with vivid color-coded
cards.

**Three panels, following the customer lifecycle:**

1. **New Inquiries** — leads awaiting first contact. Count-up timer since the
   inquiry arrived; longer = worse.
2. **Appointments Today** — booked appointments, soonest first, with a live
   **countdown** to the appointment time and a confirmed/unconfirmed indicator.
   Tomorrow's bookings show as a small "Tomorrow: N" chip in the header.
3. **On the Floor** — customers in the store now. Count-up timer since check-in.

**Urgency colors** shift a card's background + border by time. Every threshold
is a named constant at the top of [`static/board.js`](static/board.js) so you
can tune the bands without hunting through code:

| Panel | Bands |
|---|---|
| New Inquiries (count-up) | 0–5 calm green · 5–15 amber · 15–30 orange · 30+ **red, pulsing** |
| Appointments (countdown) | >60 min out dim/neutral · ≤60 min blue "prep" · ≤15 min green "arriving" · 10 min late amber · 20 min late **red, "NO SHOW — CALL"** |
| On the Floor (count-up) | 0–10 neutral · 10–20 amber "check in" · 20+ orange "needs attention" · 40+ **red, pulsing** |

Unconfirmed appointments also carry a persistent dashed outline all day.
A muted-by-default chime (small corner toggle) sounds when a card crosses into
red. If the feed goes stale (no successful poll within `BOARD_STALE_SECONDS`), a
small amber "connection lost" indicator appears in the corner — the screen is
never blanked and timers keep ticking.

### Dev mode vs. live feed

- **Dev mode (default):** leave `BOARD_FEED_URL` empty. The board runs off a
  seeded, self-aging mock feed (`app/board_mock.py`) that walks cards through
  every color state — including an appointment sliding from prep → arriving →
  late → **no-show** — so you can watch the whole system before connecting n8n.
- **Live:** set `BOARD_FEED_URL` to your n8n webhook. The board fetches it
  **server-side** (proxied via `/board/feed`), so the browser never sees the URL
  and there are no CORS issues. The board holds **no** GoHighLevel credentials —
  n8n is the only thing that talks to GHL, and it decides which panel each record
  belongs to from the pipeline stage. The display just renders what it receives.

### Feed shape (what n8n should return)

```json
{
  "inquiries": [
    { "id": "abc123", "name": "Sarah M.", "source": "Web Form",
      "receivedAt": "2026-08-06T14:22:00Z", "assignedTo": "Jenna",
      "attempts": 1 }
  ],
  "appointments": [
    { "id": "ghi789", "name": "Chen Family", "appointmentAt": "2026-08-06T18:30:00Z",
      "interest": "Cavapoo - Pepper", "assignedTo": "Marcus",
      "confirmed": true, "arrived": false }
  ],
  "floor": [
    { "id": "def456", "party": "Rodriguez", "headcount": 4,
      "checkedInAt": "2026-08-06T15:01:00Z", "interest": "Goldendoodle - Biscuit",
      "assignedTo": null }
  ],
  "generatedAt": "2026-08-06T15:30:00Z"
}
```

`source` is one of Web Form / Facebook / Google / Phone / Walk-in. `assignedTo`
of `null` renders as **UNASSIGNED** (inquiries) or **NEEDS GREETER** (floor).
An optional `"stats": { "inquiriesToday": N }` feeds the header's "Inquiries
Today" counter (falls back to the current inquiry count if omitted). An
appointment with `"arrived": true` drops off panel 2 (it's on the floor now).

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
  main.py                  # FastAPI app (API + dashboard + board)
  board_mock.py            # seeded, self-aging mock feed for the Lead & Floor Board
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
    board.py               # board page, runtime config, and feed proxy (/board/*)
    serializers.py         # ORM -> JSON
prompts/                   # 7 editable agent prompts + shared brand context
static/                    # dashboard (index.html, style.css, app.js)
                           #   + Lead & Floor Board (board.html, board.css, board.js)
tests/test_e2e.py          # end-to-end smoke test of the real workflow
tests/test_board.py        # board feed shape, color coverage, endpoint checks
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
