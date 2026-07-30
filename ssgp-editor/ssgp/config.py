"""Load config.yaml and merge per-job option overrides.

The full editing configuration lives in config.yaml. A render job may override
any leaf value by passing an ``options`` dict (from the API or the web UI) that
is deep-merged over the defaults. Nothing about the pipeline is hard-coded.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict

import yaml

# Project root = the folder that contains config.yaml (parent of this package)
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("SSGP_CONFIG", ROOT / "config.yaml"))


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config() -> Dict[str, Any]:
    """Read config.yaml fresh from disk (so edits apply without a restart)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_path(cfg: Dict[str, Any], key: str) -> Path:
    """Resolve a path from cfg['paths'] relative to the project root."""
    rel = cfg.get("paths", {}).get(key, key)
    p = Path(rel)
    return p if p.is_absolute() else (ROOT / p)


def merge_options(cfg: Dict[str, Any], options: Dict[str, Any] | None) -> Dict[str, Any]:
    """Merge a job's ``options`` over the base config.

    Accepts both the nested shape (``{"cuts": {"enabled": false}}``) and a set
    of flat convenience keys that the web UI / n8n can send without knowing the
    full tree. Flat keys are normalised into the nested config first.
    """
    options = dict(options or {})
    flat = _normalise_flat_options(options)
    return _deep_merge(cfg, flat)


# Flat convenience keys -> where they live in the nested config.
# Lets callers send e.g. {"music_volume": 0.3, "captions": false} instead of
# the full nested structure.
_FLAT_MAP = {
    "cuts": ("cuts", "enabled"),
    "smart_cut": ("cuts", "smart_cut"),
    "dog_cut": ("cuts", "dog_cut"),
    "replace_voice": ("music", "replace_voice"),
    "max_duration": ("output", "max_duration"),
    "captions": ("captions", "enabled"),
    "zoom": ("zoom", "enabled"),
    "music": ("music", "enabled"),
    "watermark": ("watermark", "enabled"),
    "cta": ("cta", "enabled"),
    "graphics": ("graphics", "enabled"),
    "music_volume": ("music", "volume"),
    "music_track": ("music", "track"),
    "zoom_intensity": ("zoom", "intensity"),
    "silence_threshold_db": ("cuts", "silence_threshold_db"),
    "min_gap": ("cuts", "min_gap"),
    "caption_model": ("captions", "model"),
    "language": ("captions", "language"),
    "watermark_text": ("watermark", "text"),
    "cta_title": ("cta", "title"),
    "cta_subtitle": ("cta", "subtitle"),
    "cta_phone": ("cta", "phone"),
}


def _normalise_flat_options(options: Dict[str, Any]) -> Dict[str, Any]:
    nested: Dict[str, Any] = {}
    for key, val in options.items():
        if key in _FLAT_MAP and not isinstance(val, dict):
            section, leaf = _FLAT_MAP[key]
            nested.setdefault(section, {})[leaf] = val
        else:
            # already-nested section (e.g. {"captions": {...}}) or unknown key
            if isinstance(val, dict):
                nested.setdefault(key, {}).update(val)
            else:
                nested[key] = val
    return nested
