# 🐶 SSGP Editor

**Self-hosted short-form video editor for Sugar Sweet Georgia Puppies.**

Feed it a raw phone clip of a puppy (or several clips) and it returns a finished,
ready-to-post vertical Reel — reframed to 9:16, dead air auto-cut, animated
word-by-word captions burned in, a subtle Ken Burns / punch-in zoom, background
music ducked under the voice, a watermark, and an optional call-to-action end
card.

It runs **entirely on your own machine** (Python + FFmpeg + faster-whisper — no
paid API keys for the core), and it exposes the **same submit-a-job / poll-for-a-URL
HTTP contract as Creatomate/Opus**, so it drops straight into your existing n8n
workflow. There's also a clean local **web UI** for running one clip by hand.

---

## What it does to every clip

| # | Feature | Details |
|---|---------|---------|
| 1 | **Reframe to vertical** | Exactly **1080×1920, 30fps, H.264 (yuv420p, +faststart)**. Center-crop/cover any landscape or square footage. Also re-encodes iPhone HEVC. |
| 2 | **Auto cuts** | Detects dead air / long silences and trims them. Silence threshold & minimum gap are configurable; padding on each side means a word is **never clipped**. |
| 3 | **Auto captions** | Transcribes locally with **faster-whisper**, then burns in animated word-by-word captions — Montserrat 800, white (#ffffff) with dark stroke (#1a1a1a), lower third (~74%), ~84% width, active-word highlight, ~22 chars/line. |
| 4 | **Auto zoom** | Slow Ken Burns push-in + gentle punch-in on cuts. Tasteful by default, intensity configurable. |
| 5 | **Background music** | Mixes a bed from `/music`, ducked ~-18 dB under the voice. Volume configurable; pick a track or randomize. |
| 6 | **Watermark** | Persistent top text “Sugar Sweet Georgia Puppies · Lawrenceville, GA”, Montserrat 700, white + thin dark stroke, ~88% opacity. |
| 7 | **CTA end card** *(optional, off by default)* | 1.5–2s outro with configurable title, subtitle & phone. |
| ➕ | **Stitch multiple clips** | Send several clips → they're normalized and joined into one Reel, in order. |
| ➕ | **Plain-English instructions** | Optional free-text like *“stitch these, tight cuts, no music, all-caps captions, add the end card.”* |

---

## 1. Install

### a) FFmpeg (required)

The app checks for FFmpeg on startup and prints the right command if it's missing.

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get update && sudo apt-get install -y ffmpeg

# Fedora
sudo dnf install -y ffmpeg

# Windows
winget install Gyan.FFmpeg      # or:  choco install ffmpeg
```

Verify: `ffmpeg -version`

### b) Python deps

Python 3.9+ recommended.

```bash
cd ssgp-editor
python3 -m venv .venv && source .venv/bin/activate      # optional but recommended
pip install -r requirements.txt
```

> The first render that needs captions downloads the Whisper model once
> (`base` ≈ 150 MB) to your HuggingFace cache, then reuses it offline. Fonts
> (Montserrat 700/800) are bundled in `fonts/`.
>
> **Any FFmpeg build works.** All text (captions, watermark, CTA) is drawn with
> Pillow and composited via FFmpeg's `overlay` filter, so you do **not** need an
> FFmpeg compiled with `libass`/`freetype` (the default Homebrew build omits
> them). Nothing extra to install.

### c) Add music (optional)

Drop `.mp3` / `.m4a` / `.wav` beds into the `music/` folder. Pick one per job or
let it randomize.

---

## 2. Start the server

```bash
python run.py                 # http://localhost:8080  (API + web UI)
python run.py --port 9000     # different port
```

Open **http://localhost:8080** for the web UI, or point n8n at the same base URL.

Health check: `curl http://localhost:8080/healthz`

---

## 3. HTTP API (for n8n)

Mirrors the Creatomate pattern: **submit → poll → get URL**.

### `POST /render` — submit a job (returns immediately)

Body (JSON):

```json
{
  "video_url": "https://drive.google.com/uc?export=download&id=FILEID",
  "options": {
    "captions": true,
    "cuts": true,
    "zoom": { "enabled": true, "intensity": 0.06 },
    "music": { "enabled": true, "volume": 0.18, "track": null },
    "watermark": true,
    "cta": false
  }
}
```

Response:

```json
{ "id": "6f1696850d40", "status": "queued" }
```

**Example:**

```bash
curl -X POST http://localhost:8080/render \
  -H "Content-Type: application/json" \
  -d '{"video_url":"https://drive.google.com/uc?export=download&id=FILEID"}'
```

Notes:
- `video_url` accepts any **direct-download URL**, including Google Drive
  `uc?export=download&id=...` links (the large-file “confirm” page is handled
  for you). `/file/d/<id>/view` links work too.
- To **stitch multiple clips**, send `"video_urls": ["url1","url2",...]` (they're
  joined in order into one Reel, with smooth crossfades).
- To make **one Reel per clip** (batch: 10 in → 10 out), add `"separate": true`.
  The response is `{ "ids": ["id1","id2",...], "count": N, "status": "queued" }`
  — poll each id with `GET /render/{id}` exactly as usual.
- **Smart cut (AI)**: add `"smart_cut": true` to have Claude read the transcript
  and remove spoken flubs / false starts / "I forgot the script" / off-topic
  tangents (things silence-cutting can't catch). Requires an Anthropic API key —
  set `ANTHROPIC_API_KEY` in your environment (or `cuts.anthropic_api_key` in
  config.yaml). Without a key it's simply skipped.
- To **upload a file** instead of a URL, POST `multipart/form-data` with a
  `files` field (repeat `files` for multiple clips) and an optional `options`
  JSON string and `instructions` text.
- `options` can use the **short keys** shown above *or* the full nested config
  tree (any key from `config.yaml`). Anything you omit uses the `config.yaml`
  default.
- Optional `"instructions": "tight cuts, no music, all caps"` — plain English,
  interpreted into options.

### `GET /render/{id}` — poll status

```bash
curl http://localhost:8080/render/6f1696850d40
```

While rendering:

```json
{ "id": "6f1696850d40", "status": "processing", "url": null, "error": null, "progress": 60, "stage": "video" }
```

When done:

```json
{
  "id": "6f1696850d40",
  "status": "succeeded",
  "url": "/files/6f1696850d40.mp4",
  "error": null,
  "progress": 100,
  "applied": { "output_duration": 9.8, "captions": true, "music": "bed_calm.mp3", "cta": false }
}
```

`status` is one of `queued | processing | succeeded | failed`. When `succeeded`,
`url` points at the finished MP4 served by this app.

### `GET /files/{id}.mp4` — the finished video

The `url` from the status response. E.g. `http://localhost:8080/files/6f1696850d40.mp4`.

Jobs run in an in-process background worker queue, so several can be submitted at
once and each `POST /render` returns instantly — poll-friendly for an n8n Wait
loop.

---

## 4. Swapping this in for Creatomate/Opus in n8n

Your existing flow is: **HTTP Request (create render)** → **Wait / poll** →
**HTTP Request (get render)** → use the finished video URL. Keep that exact
shape; just change three things.

**Step 1 — the “create render” HTTP Request node**
- **Method:** `POST`
- **URL:** `http://<this-machine>:8080/render`
  *(if n8n runs in Docker, use `http://host.docker.internal:8080/render`)*
- **Body (JSON):**
  ```json
  {
    "video_url": "={{ $json.driveDownloadUrl }}",
    "options": { "cta": false }
  }
  ```
  Point `video_url` at whatever field currently holds your Google Drive
  direct-download link (the `uc?export=download&id=...` URL).
- **Response → save the job id:** `{{ $json.id }}`.

**Step 2 — the Wait / poll loop**
- Keep your **Wait** node.
- **“get render” HTTP Request node:**
  - **Method:** `GET`
  - **URL:** `http://<this-machine>:8080/render/{{ $json.id }}`
- **IF / loop condition:** continue waiting while
  `{{ $json.status }}` is **not** `succeeded` (and branch to an error path on
  `failed`). This is the same polling logic you used for Creatomate.

**Step 3 — read the finished video URL**
- When `status == "succeeded"`, the finished MP4 is at
  `{{ $json.url }}` → e.g. `/files/<id>.mp4`.
- Build the absolute URL for the next node (upload / post):
  `http://<this-machine>:8080{{ $json.url }}`.
- Feed that into your existing “download video” / “post to social” nodes exactly
  where the Creatomate output URL used to go.

That's the whole swap — same submit/poll/collect contract, no other node changes.

> **Field mapping cheat-sheet (Creatomate → SSGP Editor):**
> `POST /v1/renders` → `POST /render` · `id` → `id` · poll `GET /v1/renders/{id}`
> → `GET /render/{id}` · `status: "succeeded"` → `status: "succeeded"` ·
> output `url` → `url` (prefix with the server base).

---

## 5. Web UI

Open **http://localhost:8080**. From one page you can:

- paste one or more **URLs** (one per line) and/or **upload** file(s),
- optionally type **plain-English instructions**,
- toggle each feature (cuts / captions / zoom / music / watermark / CTA),
- adjust the main sliders (music volume, zoom intensity, silence threshold),
- pick a caption model and music track,
- hit **Render**, watch progress, **preview inline**, and **download** the MP4.

---

## 6. Configuration

Every editing setting lives in **`config.yaml`**, fully commented. Tune caption
style, music volume/ducking, zoom, silence threshold, watermark text, CTA text,
and output format there — no code changes. Each value can also be overridden
per-job via the API `options` or the UI controls.

Key sections: `output`, `cuts`, `captions`, `zoom`, `music`, `watermark`, `cta`,
`paths`, `server`.

### Knowledge base (breed names)

`knowledge.yaml` teaches the caption transcriber your store's vocabulary so it
stops mishearing breeds (e.g. "dachshund" → "docks", "maltipoo" → "multi poo"):

- `breeds` / `terms` — handed to the transcriber up front so it *expects* these
  words (it's a puppy store, so a dachshund is heard as "dachshund").
- `corrections` — exact auto-replacements for known mishears (`docks:
  Dachshund`, `"multi poo": Maltipoo`, …). Left side is case-insensitive and can
  be several words; the right side is the fix.

Add your own breeds and mishears anytime — just edit the file and re-render. The
result panel lists any breed-name fixes it applied.

---

## 7. Folders

| Folder | Purpose |
|--------|---------|
| `output/` | Finished renders (`{id}.mp4`), served at `/files/{id}.mp4`. |
| `work/`   | Per-job source downloads & temp files. Cleaned up after a successful render (`server.cleanup_work`). |
| `music/`  | Your background-music beds. |
| `fonts/`  | Bundled Montserrat 700/800. |
| `samples/`| A generated test clip + `e2e_test.py` you can run to confirm the whole pipeline. |

---

## 8. Quick self-test

With FFmpeg + deps installed:

```bash
python samples/e2e_test.py
```

It renders the bundled sample clip through the full pipeline (cuts, captions,
zoom, music, watermark, CTA) using a supplied transcript (so it runs without
downloading the Whisper model) and asserts the output is vertical 1080×1920
H.264 with audio. Result: `samples/e2e_output.mp4`.

---

## Troubleshooting

- **“FFmpeg not found.”** Install it (section 1a); the error message shows the
  exact command for your OS.
- **Captions didn't appear / `captions_error` in the status.** The Whisper model
  needs to download once from HuggingFace on first use — make sure the machine
  has internet for that first run (it's cached afterward). Everything else still
  renders if transcription fails.
- **n8n can't reach the server from Docker.** Use `http://host.docker.internal:8080`
  instead of `localhost`, and make sure the port is reachable.
- **Google Drive link downloads an HTML page.** Use the `uc?export=download&id=...`
  form (or a `/file/d/<id>/view` link) and make sure the file is shared
  “anyone with the link.”
