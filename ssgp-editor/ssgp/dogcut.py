"""Dog-only cutting: keep only the parts of the video where a dog/puppy is
actually on screen, cut the rest.

Uses on-device object detection (Ultralytics YOLO, COCO 'dog' class). It's an
optional, heavier capability:  pip install ultralytics  (first run downloads a
small model). If it isn't installed we return a clear status instead of failing
the render. Safety: if NO dogs are detected we keep everything rather than
cutting the whole clip.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

Range = Tuple[float, float]
_COCO_DOG = 16  # 'dog' in the COCO classes YOLO is trained on


def _merge_keep(times: List[float], pad: float, join_gap: float) -> List[Range]:
    """Turn dog-sighting timestamps into padded, merged keep intervals."""
    if not times:
        return []
    times.sort()
    keep: List[Range] = [(max(0.0, times[0] - pad), times[0] + pad)]
    for t in times[1:]:
        s, e = t - pad, t + pad
        if s <= keep[-1][1] + join_gap:
            keep[-1] = (keep[-1][0], max(keep[-1][1], e))
        else:
            keep.append((max(0.0, s), e))
    return keep


def _complement(keep: List[Range], duration: float, min_gap: float) -> List[Range]:
    """No-dog stretches (longer than min_gap) between the keep intervals."""
    removals: List[Range] = []
    cursor = 0.0
    for a, b in keep:
        if a - cursor >= min_gap:
            removals.append((cursor, a))
        cursor = max(cursor, b)
    if duration - cursor >= min_gap:
        removals.append((cursor, duration))
    return removals


def plan_removals(video_path: str, duration: float, cfg_cuts: Dict, work: Path) -> Dict:
    """Return {removals, status, detail} of no-dog ranges to cut."""
    try:
        from ultralytics import YOLO
    except Exception:
        return {"removals": [], "status": "error",
                "detail": "install with: pip install ultralytics"}

    sample_fps = float(cfg_cuts.get("dog_cut_sample_fps", 2))
    conf = float(cfg_cuts.get("dog_cut_confidence", 0.35))
    pad = float(cfg_cuts.get("dog_cut_pad", 0.4))
    min_gap = float(cfg_cuts.get("dog_cut_min_gap", 0.6))

    frames_dir = Path(work) / "dogframes"
    frames_dir.mkdir(parents=True, exist_ok=True)
    # sample small frames for speed
    proc = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", video_path,
        "-vf", f"fps={sample_fps},scale=640:-2", str(frames_dir / "f_%05d.jpg"),
    ], capture_output=True, text=True)
    if proc.returncode != 0:
        return {"removals": [], "status": "error", "detail": "frame sampling failed"}

    frames = sorted(frames_dir.glob("f_*.jpg"))
    if not frames:
        return {"removals": [], "status": "error", "detail": "no frames sampled"}

    try:
        model = YOLO("yolov8n.pt")
    except Exception as exc:
        return {"removals": [], "status": "error", "detail": f"model load failed: {exc}"}

    dog_times: List[float] = []
    # batch inference in chunks to bound memory
    paths = [str(f) for f in frames]
    for start in range(0, len(paths), 32):
        chunk = paths[start:start + 32]
        try:
            results = model(chunk, conf=conf, verbose=False)
        except Exception as exc:
            return {"removals": [], "status": "error", "detail": f"detection failed: {exc}"}
        for j, res in enumerate(results):
            idx = start + j  # frame index (0-based)
            t = idx / sample_fps
            classes = getattr(res.boxes, "cls", []) or []
            if any(int(c) == _COCO_DOG for c in classes):
                dog_times.append(t)

    if not dog_times:
        return {"removals": [], "status": "ok", "detail": "no dogs detected — kept everything"}

    keep = _merge_keep(dog_times, pad, join_gap=max(min_gap, 1.0 / sample_fps + pad))
    removals = _complement(keep, duration, min_gap)
    return {"removals": removals, "status": "ok",
            "detail": f"kept {len(keep)} dog segment(s), cut {len(removals)} no-dog stretch(es)"}
