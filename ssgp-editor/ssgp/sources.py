"""Fetch source videos (incl. Google Drive links) and stitch multiple clips.

- ``download_source`` pulls a clip from any direct-download URL. Google Drive
  ``uc?export=download`` links that return an interstitial "confirm" page for
  large files are handled transparently.
- ``stitch_clips`` normalises several clips to a common vertical canvas and
  concatenates them into a single source, so "here are 4 clips, make one Reel"
  just works. The main pipeline then treats the result as one source video.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from .ffmpeg_utils import probe, run
from .reframe import reframe_fc

_CHUNK = 1 << 20  # 1 MiB


def _gdrive_file_id(url: str) -> Optional[str]:
    """Extract a Google Drive file id from the common URL shapes."""
    u = urlparse(url)
    if "drive.google.com" not in u.netloc:
        return None
    qs = parse_qs(u.query)
    if "id" in qs:
        return qs["id"][0]
    m = re.search(r"/file/d/([^/]+)", u.path)  # /file/d/<id>/view
    if m:
        return m.group(1)
    return None


def download_source(url: str, dest: str, timeout: int = 120) -> str:
    """Download ``url`` to ``dest``. Returns the local path."""
    dest_p = Path(dest)
    dest_p.parent.mkdir(parents=True, exist_ok=True)

    file_id = _gdrive_file_id(url)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (SSGP-Editor)"})

    if file_id:
        base = "https://drive.google.com/uc?export=download"
        resp = session.get(base, params={"id": file_id}, stream=True, timeout=timeout)
        # Large files: Drive serves a confirm page; grab the token and retry.
        token = None
        for k, v in resp.cookies.items():
            if k.startswith("download_warning"):
                token = v
        if token is None and "text/html" in resp.headers.get("Content-Type", ""):
            m = re.search(r"confirm=([0-9A-Za-z_-]+)", resp.text)
            if m:
                token = m.group(1)
        if token:
            resp = session.get(
                base, params={"id": file_id, "confirm": token}, stream=True, timeout=timeout
            )
    else:
        resp = session.get(url, stream=True, timeout=timeout)

    resp.raise_for_status()
    with open(dest_p, "wb") as fh:
        for chunk in resp.iter_content(_CHUNK):
            if chunk:
                fh.write(chunk)

    if dest_p.stat().st_size == 0:
        raise RuntimeError(f"Downloaded 0 bytes from {url}")
    return str(dest_p)


def _normalise_clip(src: str, dst: str, w: int, h: int, fps: int, log_path=None,
                    mode: str = "cover_center", crop_x: float = 0.5, crop_y: float = 0.5) -> None:
    """Reframe one clip to the output canvas so all clips share codec params.

    ``mode`` picks the reframe strategy (center-crop for 9:16, blur-fill/pad for
    16:9 so a vertical clip isn't cropped to a sliver)."""
    info = probe(src)
    fc = reframe_fc("[0:v]", "[rf]", mode, w, h, crop_x, crop_y) + f";[rf]fps={fps},format=yuv420p[vout]"
    cmd = ["ffmpeg", "-y", "-i", src]
    maps = ["-map", "[vout]"]
    tail: List[str] = []
    if not info.has_audio:
        # synthesise silent audio so every clip has a matching audio stream
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        maps += ["-map", "1:a"]
        tail = ["-shortest"]
    else:
        maps += ["-map", "0:a?"]
    cmd += [
        "-filter_complex", fc, *maps,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        *tail, dst,
    ]
    run(cmd, log_path)


def stitch_clips(
    paths: List[str], dest: str, w: int, h: int, fps: int, work_dir: str,
    log_path=None, xfade: float = 0.35, mode: str = "cover_center",
    crop_x: float = 0.5, crop_y: float = 0.5,
) -> str:
    """Stitch multiple clips into one vertical source, blended with a short
    crossfade (video xfade + audio acrossfade) so joins look smooth instead of
    hard-cut. Set ``xfade`` to 0 for a straight cut.
    """
    if len(paths) == 1:
        return paths[0]

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    norm: List[str] = []
    durs: List[float] = []
    for i, p in enumerate(paths):
        out = str(work / f"part{i:03d}.mp4")
        _normalise_clip(p, out, w, h, fps, log_path, mode, crop_x, crop_y)
        norm.append(out)
        durs.append(probe(out).duration)

    # a straight concat (no blend) — robust fallback
    if xfade <= 0:
        list_file = work / "concat.txt"
        list_file.write_text("".join(f"file '{p}'\n" for p in norm), encoding="utf-8")
        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-movflags", "+faststart", dest,
        ], log_path)
        return dest

    # crossfade chain. Clamp the transition so it fits the shortest clip.
    t = min(xfade, min(durs) * 0.4)
    inputs: List[str] = []
    for p in norm:
        inputs += ["-i", p]

    v_prev, a_prev = "[0:v]", "[0:a]"
    fc_parts: List[str] = []
    acc = durs[0]
    for i in range(1, len(norm)):
        vlbl, albl = f"[vx{i}]", f"[ax{i}]"
        offset = max(0.0, acc - t)
        fc_parts.append(
            f"{v_prev}[{i}:v]xfade=transition=fade:duration={t:.3f}:offset={offset:.3f}{vlbl}"
        )
        fc_parts.append(f"{a_prev}[{i}:a]acrossfade=d={t:.3f}{albl}")
        v_prev, a_prev = vlbl, albl
        acc = acc + durs[i] - t

    fc = ";".join(fc_parts)
    run([
        "ffmpeg", "-y", *inputs, "-filter_complex", fc,
        "-map", v_prev, "-map", a_prev,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart", dest,
    ], log_path)
    return dest
