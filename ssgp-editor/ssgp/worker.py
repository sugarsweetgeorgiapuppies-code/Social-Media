"""Background render worker.

A pool of daemon threads pulls jobs off an in-process queue so several renders
can be submitted at once and the HTTP request returns immediately. No Redis /
Celery / external broker — everything lives in this process.
"""

from __future__ import annotations

import queue
import shutil
import threading
import traceback
from pathlib import Path
from typing import Callable, List, Optional

from . import formats
from . import instructions as instr_mod
from .config import load_config, merge_options, resolve_path
from .jobs import Job, JobStore
from .pipeline import render_video
from .sources import download_source, stitch_clips


class RenderWorker:
    def __init__(self, store: JobStore, workers: int = 2) -> None:
        self.store = store
        self.queue: "queue.Queue[str]" = queue.Queue()
        # per-job locally-staged upload files, keyed by job id
        self.local_inputs: dict[str, List[str]] = {}
        self._threads: List[threading.Thread] = []
        for i in range(max(1, workers)):
            t = threading.Thread(target=self._loop, name=f"ssgp-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def submit(self, job: Job, local_inputs: Optional[List[str]] = None) -> None:
        if local_inputs:
            self.local_inputs[job.id] = local_inputs
        self.queue.put(job.id)

    def _loop(self) -> None:
        while True:
            job_id = self.queue.get()
            try:
                self._run(job_id)
            except Exception:  # noqa: BLE001 — never let the worker thread die
                self.store.update(
                    job_id, status="failed", stage="error",
                    error=traceback.format_exc(limit=3),
                )
            finally:
                self.queue.task_done()

    def _run(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if not job:
            return

        cfg = load_config()

        # 1) format bundle (short vs long) as the BASE layer — sets aspect,
        #    reframe, pacing, caption/graphics/music defaults for the chosen mode
        overrides = dict(job.options or {})
        fmt = formats.normalize_format(str(overrides.pop("format", "") or "short"))
        cfg = merge_options(cfg, formats.bundle(fmt))
        cfg["format"] = fmt

        # 2) free-text instructions, then explicit options win over them
        notes: List[str] = []
        if job.instructions:
            interp, notes = instr_mod.interpret(job.instructions, cfg)
            # a typed instruction is an explicit intent — it wins over the
            # baseline toggles for whatever it mentions (interp only contains
            # what was actually requested, so untouched toggles are preserved).
            overrides = _deep_merge(overrides, interp)
        cfg = merge_options(cfg, overrides)
        cfg["format"] = fmt  # keep after merges (format is not an output leaf)

        self.store.update(job_id, status="processing", stage="preparing", progress=1, notes=notes)

        work_root = resolve_path(cfg, "work_dir")
        out_dir = resolve_path(cfg, "output_dir")
        job_work = Path(work_root) / job_id
        job_work.mkdir(parents=True, exist_ok=True)
        log_path = str(job_work / "ffmpeg.log")

        out = cfg["output"]
        W, H, FPS = int(out["width"]), int(out["height"]), int(out["fps"])

        # 1) gather sources (downloads + uploads), in submission order
        local_paths: List[str] = []
        uploads = self.local_inputs.pop(job_id, [])
        upload_iter = iter(uploads)
        idx = 0
        for src in job.sources:
            if src.startswith("upload:"):
                local_paths.append(next(upload_iter))
            else:
                dest = str(job_work / f"src{idx:03d}")
                self.store.update(job_id, stage=f"downloading ({idx + 1})")
                local_paths.append(download_source(src, dest))
            idx += 1
        # any pure-upload jobs where sources list was empty
        for up in upload_iter:
            local_paths.append(up)

        if not local_paths:
            raise RuntimeError("no source video provided")

        # 2) stitch multiple clips into one vertical source
        if len(local_paths) > 1:
            self.store.update(job_id, stage="stitching clips", progress=3)
            source = stitch_clips(
                local_paths, str(job_work / "stitched.mp4"), W, H, FPS, str(job_work), log_path,
                mode=cfg["output"].get("reframe", "cover_center"),
                crop_x=float(cfg["output"].get("crop_x", 0.5)),
                crop_y=float(cfg["output"].get("crop_y", 0.5)),
            )
        else:
            source = local_paths[0]

        # 3) render
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(Path(out_dir) / f"{job_id}.mp4")

        def progress(pct: int, stage: str) -> None:
            self.store.update(job_id, progress=pct, stage=stage)

        applied = render_video(
            source, out_path, cfg, str(job_work),
            progress=progress, log_path=log_path, job_id=job_id,
            user_instruction=job.instructions or "",
        )

        self.store.update(
            job_id, status="succeeded", progress=100, stage="done",
            url=f"/files/{job_id}.mp4", applied=applied, error=None,
        )

        # 4) cleanup work dir on success
        if cfg.get("server", {}).get("cleanup_work", True):
            shutil.rmtree(job_work, ignore_errors=True)


def _deep_merge(base: dict, override: dict) -> dict:
    import copy

    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
