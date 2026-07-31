"""FastAPI app: the n8n-facing HTTP API, the local web UI, and file serving.

Endpoints
    POST /render            submit a job (JSON for n8n, or multipart upload)
    GET  /render/{id}       poll status -> { status, url, ... }
    GET  /files/{id}.mp4    the finished video (also where `url` points)
    GET  /                  the local web UI
    GET  /api/config        default settings (UI populates controls from this)
    GET  /api/music         available music tracks
    GET  /api/jobs          recent jobs (UI)
    GET  /healthz           ffmpeg presence + status
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import music as music_mod
from .config import ROOT, load_config, resolve_path
from .ffmpeg_utils import ffmpeg_available, install_hint
from .jobs import JobStore
from .worker import RenderWorker

app = FastAPI(title="SSGP Editor", version="1.0.0")

STORE = JobStore()
_cfg0 = load_config()
_worker_count = int(_cfg0.get("server", {}).get("workers", 2))
WORKER = RenderWorker(STORE, workers=_worker_count)

OUTPUT_DIR = resolve_path(_cfg0, "output_dir")
WORK_DIR = resolve_path(_cfg0, "work_dir")
STATIC_DIR = ROOT / "ssgp" / "static"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

# finished renders are served here; this is what GET /render/{id}.url points to
app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")


def _sources_from_payload(payload: Dict[str, Any]) -> List[str]:
    """Accept video_url (str), video_urls (list), or source/sources aliases."""
    srcs: List[str] = []
    for key in ("video_urls", "sources", "clips"):
        val = payload.get(key)
        if isinstance(val, list):
            srcs.extend([str(v) for v in val if v])
    for key in ("video_url", "source", "url"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            srcs.append(val)
    # de-dup while preserving order
    seen, out = set(), []
    for s in srcs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


@app.post("/render")
async def render(request: Request):
    """Submit a render job. Returns { id, status: "queued" } immediately."""
    if not ffmpeg_available():
        raise HTTPException(status_code=500, detail=install_hint())

    ctype = request.headers.get("content-type", "")
    sources: List[str] = []
    options: Dict[str, Any] = {}
    instructions: str = ""
    local_inputs: List[str] = []
    separate = False

    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        separate = str(form.get("separate", "")).lower() in ("1", "true", "yes", "on")
        # options / instructions may come as JSON strings or plain fields
        if form.get("options"):
            try:
                options = json.loads(str(form["options"]))
            except (ValueError, TypeError):
                options = {}
        instructions = str(form.get("instructions") or "")
        for key in ("video_url", "url"):
            if form.get(key):
                sources.append(str(form[key]))
        # uploaded files (single "file" or multiple "files")
        upload_dir = WORK_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        files = form.getlist("files") + form.getlist("file")
        for f in files:
            if hasattr(f, "filename") and f.filename:
                dest = upload_dir / f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
                with open(dest, "wb") as fh:
                    fh.write(await f.read())
                local_inputs.append(str(dest))
                sources.append(f"upload:{f.filename}")
    else:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Body must be JSON or multipart/form-data")
        sources = _sources_from_payload(payload)
        options = payload.get("options") or {}
        instructions = str(payload.get("instructions") or payload.get("prompt") or "")
        separate = bool(payload.get("separate"))

    if not sources and not local_inputs:
        raise HTTPException(status_code=400, detail="Provide video_url, video_urls, or an uploaded file")

    # pair each source with its uploaded file (if any), preserving order
    upload_iter = iter(local_inputs)
    items = [(s, next(upload_iter) if s.startswith("upload:") else None) for s in sources]

    # Batch mode: one finished Reel per clip (10 in -> 10 out).
    if separate and len(items) > 1:
        ids = []
        for src, path in items:
            job = STORE.create(sources=[src], options=options, instructions=instructions)
            WORKER.submit(job, local_inputs=[path] if path else None)
            ids.append(job.id)
        return JSONResponse({"ids": ids, "count": len(ids), "status": "queued"})

    # Default: a single Reel (multiple clips are stitched together).
    job = STORE.create(sources=[s for s, _ in items], options=options, instructions=instructions)
    WORKER.submit(job, local_inputs=[p for _, p in items if p])
    return JSONResponse({"id": job.id, "status": "queued"})


@app.get("/render/{job_id}")
async def render_status(job_id: str):
    job = STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job id")
    return JSONResponse(job.public())


@app.get("/api/config")
async def api_config():
    """Expose the current defaults so the UI can populate its controls."""
    cfg = load_config()
    from . import smartcut
    cfg["ai_editing_available"] = smartcut.available(cfg.get("cuts", {}))
    return cfg


@app.get("/api/ai-check")
async def ai_check():
    """Actually call Claude with a tiny prompt so the UI can tell the user whether
    the AI editor truly works (key valid + model accessible), not just 'key set'."""
    cfg = load_config()
    from . import smartcut
    key = smartcut._api_key(cfg.get("cuts", {}))
    if not key:
        return {"ok": False, "reason": "no_key"}
    model = os.environ.get("SSGP_MODEL") or cfg.get("cuts", {}).get("smart_cut_model") or "claude-sonnet-5"
    try:
        import anthropic
        anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=5, messages=[{"role": "user", "content": "ok"}])
        return {"ok": True, "model": model}
    except Exception as exc:
        return {"ok": False, "reason": "error", "model": model, "detail": f"{type(exc).__name__}: {exc}"}


@app.get("/api/music")
async def api_music():
    cfg = load_config()
    folder = ROOT / cfg["music"].get("folder", "music")
    return {"tracks": [p.name for p in music_mod.list_tracks(folder)]}


@app.get("/api/jobs")
async def api_jobs():
    return {"jobs": [j.public() for j in STORE.all()[:50]]}


@app.get("/healthz")
async def healthz():
    ok = ffmpeg_available()
    return {"status": "ok" if ok else "missing-ffmpeg", "ffmpeg": ok, "hint": None if ok else install_hint()}


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# serve the rest of the static assets (favicon, etc.) if present
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
