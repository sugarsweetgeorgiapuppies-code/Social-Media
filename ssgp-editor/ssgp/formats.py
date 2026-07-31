"""Per-format default bundles (short vs long).

Choosing Short or Long up front isn't just a frame size — it selects a whole set
of editing defaults so the two formats behave like different editors, not one
scaled. This bundle is applied as a BASE layer (under the user's instruction and
explicit controls), so anything here can still be overridden.

- SHORT: 9:16 vertical, fill-and-crop reframe, tight cuts, dynamic captions +
  graphics, more motion, can speed up to hit a target length.
- LONG: 16:9 widescreen, blur-fill reframe (never crops the subject out),
  gentler cuts that keep natural pauses, clean/optional captions, minimal
  motion, no global speed-up.
"""

from __future__ import annotations

from typing import Dict


_SHORT: Dict = {
    "format": "short",
    "output": {
        "width": 1080, "height": 1920, "fps": 30,
        "reframe": "cover_center", "layout_profile": "vertical",
        "max_speed": 1.35,
    },
    "cuts": {"enabled": True, "min_gap": 0.5, "keep_pad": 0.12},
    "captions": {"enabled": True, "mode": "dynamic"},
    "graphics": {"enabled": True},
    "zoom": {"enabled": True, "intensity": 0.06, "punch_on_cuts": False},
    "music": {"enabled": True, "volume": 0.18, "voice_lufs": -16},
}

_LONG: Dict = {
    "format": "long",
    "output": {
        "width": 1920, "height": 1080, "fps": 30,
        "reframe": "blur_fill", "layout_profile": "horizontal",
        "max_speed": 1.0,
    },
    "cuts": {"enabled": True, "min_gap": 0.9, "keep_pad": 0.18},
    "captions": {"enabled": False, "mode": "clean"},
    "graphics": {"enabled": False},
    "zoom": {"enabled": True, "intensity": 0.03, "punch_on_cuts": False},
    "music": {"enabled": True, "volume": 0.12, "voice_lufs": -14},
}


def normalize_format(fmt: str | None) -> str:
    f = (fmt or "").strip().lower()
    return f if f in ("short", "long") else "short"


def bundle(fmt: str | None) -> Dict:
    """Return a deep-copyable overrides dict of defaults for the given format."""
    import copy
    return copy.deepcopy(_LONG if normalize_format(fmt) == "long" else _SHORT)
