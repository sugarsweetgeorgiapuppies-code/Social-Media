"""Turn a plain-English instruction into concrete render option overrides.

This lets you say things like:
    "stitch these, no music, punchy zoom, all-caps captions, add the end card"
and have it map onto the same options the API/UI use. It works with NO API key
(keyword rules below). If ANTHROPIC_API_KEY is set, the model is used first for
more nuanced parsing and we fall back to the rules if anything goes wrong.

Returns (overrides_dict, matched_notes) — matched_notes is shown back to you so
you can see how your words were interpreted.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Tuple


def _has(text: str, *phrases: str) -> bool:
    return any(re.search(r"\b" + re.escape(p) + r"\b", text) for p in phrases)


def interpret(text: str, base_cfg: dict | None = None) -> Tuple[Dict, List[str]]:
    text = (text or "").strip()
    if not text:
        return {}, []

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _interpret_llm(text)
        except Exception:
            pass  # fall through to rules
    return _interpret_rules(text.lower())


def _interpret_rules(t: str) -> Tuple[Dict, List[str]]:
    o: Dict = {}
    notes: List[str] = []

    def set_(section, key, val, note):
        o.setdefault(section, {})[key] = val
        notes.append(note)

    # --- music ---
    if _has(t, "no music", "without music", "mute music", "no background music", "no track"):
        set_("music", "enabled", False, "music off")
    elif _has(t, "loud music", "louder music", "more music", "music up"):
        set_("music", "volume", 0.35, "music louder")
    elif _has(t, "quiet music", "soft music", "softer music", "music down", "subtle music"):
        set_("music", "volume", 0.10, "music quieter")

    # --- captions ---
    if _has(t, "no captions", "without captions", "no subtitles", "no text"):
        set_("captions", "enabled", False, "captions off")
    if _has(t, "all caps", "uppercase", "caps captions"):
        set_("captions", "uppercase", True, "uppercase captions")

    # --- watermark ---
    if _has(t, "no watermark", "without watermark", "remove watermark", "no logo"):
        set_("watermark", "enabled", False, "watermark off")

    # --- zoom / motion ---
    if _has(t, "no zoom", "static", "no motion", "no movement", "hold still"):
        set_("zoom", "enabled", False, "zoom off")
    elif _has(t, "punchy", "energetic", "more zoom", "dynamic", "lots of movement", "punch"):
        o.setdefault("zoom", {}).update({"enabled": True, "intensity": 0.11, "punch_amount": 0.07})
        notes.append("stronger zoom/punch")
    elif _has(t, "subtle", "calm", "gentle", "slow", "minimal motion"):
        o.setdefault("zoom", {}).update({"enabled": True, "intensity": 0.04})
        notes.append("subtle zoom")

    # --- cuts ---
    if _has(t, "don't cut", "do not cut", "no cuts", "keep pauses", "keep the pauses", "no trimming"):
        set_("cuts", "enabled", False, "auto-cuts off")
    elif _has(t, "tight", "cut more", "aggressive cuts", "fast paced", "snappy", "remove pauses"):
        o.setdefault("cuts", {}).update({"enabled": True, "min_gap": 0.35})
        notes.append("tighter cuts")
    elif _has(t, "relaxed", "loose cuts", "keep it natural"):
        o.setdefault("cuts", {}).update({"enabled": True, "min_gap": 0.9})
        notes.append("looser cuts")

    # --- CTA end card ---
    if _has(t, "cta", "end card", "call to action", "outro", "add the card", "closing card"):
        set_("cta", "enabled", True, "CTA end card on")

    # --- language ---
    for lang, code in {"spanish": "es", "french": "fr", "german": "de", "portuguese": "pt"}.items():
        if _has(t, lang):
            set_("captions", "language", code, f"language: {code}")

    return o, notes


def _interpret_llm(text: str) -> Tuple[Dict, List[str]]:
    """Use Claude to map free text onto option overrides (optional, needs key)."""
    import anthropic

    client = anthropic.Anthropic()
    schema_hint = (
        "Return ONLY compact JSON with a subset of these keys (omit anything not "
        "mentioned): {\"cuts\":{\"enabled\":bool,\"min_gap\":num},"
        "\"captions\":{\"enabled\":bool,\"uppercase\":bool,\"language\":str},"
        "\"zoom\":{\"enabled\":bool,\"intensity\":num,\"punch_amount\":num},"
        "\"music\":{\"enabled\":bool,\"volume\":num,\"track\":str},"
        "\"watermark\":{\"enabled\":bool},\"cta\":{\"enabled\":bool,\"title\":str,"
        "\"subtitle\":str,\"phone\":str}}"
    )
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        system=(
            "You translate a video editor's plain-English request into JSON option "
            "overrides for a vertical-Reel renderer. " + schema_hint
        ),
        messages=[{"role": "user", "content": text}],
    )
    raw = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    m = re.search(r"\{.*\}", raw, re.S)
    overrides = json.loads(m.group(0)) if m else {}
    return overrides, ["interpreted by Claude"]
