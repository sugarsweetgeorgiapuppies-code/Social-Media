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


def _normalise_clip(src: str, dst_ts: str, w: int, h: int, fps: int, log_path=None) -> None:
    """Reframe one clip to the vertical canvas and write an MPEG-TS segment.

    TS segments with identical codec parameters concatenate losslessly with a
    stream copy, which is fast and robust across mixed-resolution inputs.
    """
    info = probe(src)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps},setsar=1"
    )
    cmd = ["ffmpeg", "-y", "-i", src]
    if not info.has_audio:
        # synthesise silent audio so every segment has a matching audio stream
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-shortest"]
    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-f", "mpegts", dst_ts,
    ]
    run(cmd, log_path)


def stitch_clips(paths: List[str], dest: str, w: int, h: int, fps: int, work_dir: str, log_path=None) -> str:
    """Stitch multiple clips into one vertical source at ``dest`` (mp4)."""
    if len(paths) == 1:
        return paths[0]

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    ts_parts: List[str] = []
    for i, p in enumerate(paths):
        ts = str(work / f"part{i:03d}.ts")
        _normalise_clip(p, ts, w, h, fps, log_path)
        ts_parts.append(ts)

    concat = "concat:" + "|".join(ts_parts)
    run([
        "ffmpeg", "-y", "-i", concat,
        "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", dest,
    ], log_path)
    return dest
