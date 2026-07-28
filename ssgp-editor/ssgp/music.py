"""Pick a background-music track from the local /music folder."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional

_AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus"}


def list_tracks(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in _AUDIO_EXT)


def pick_track(folder: Path, track: Optional[str], selection: str, seed: str = "") -> Optional[Path]:
    """Choose a music file.

    - ``track`` set -> that exact filename (if present).
    - else ``selection`` = first | alphabetical | random.
      "random" is seeded by the job id so a given job is reproducible but
      different jobs vary.
    """
    tracks = list_tracks(folder)
    if not tracks:
        return None
    if track:
        for p in tracks:
            if p.name == track or p.stem == track:
                return p
        # named track missing — fall through to selection rather than failing
    if selection == "first":
        return tracks[0]
    if selection == "alphabetical":
        return sorted(tracks, key=lambda p: p.name.lower())[0]
    # random (deterministic per seed)
    h = int(hashlib.sha256((seed or "ssgp").encode()).hexdigest(), 16)
    return tracks[h % len(tracks)]
