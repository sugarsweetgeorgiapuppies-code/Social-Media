"""AI "smart cut": remove spoken mistakes the silence-cutter can't catch.

Silence detection only removes quiet gaps. It cannot remove a *spoken* flub like
"oh wait, I forgot the script" or a repeated take. This module sends the
transcript (with timestamps) to Claude and asks which time ranges to drop —
false starts, retakes, filler tangents, off-topic rambling — then returns those
ranges so the pipeline can cut them along with the silences.

Requires an Anthropic API key (env ANTHROPIC_API_KEY, or cuts.anthropic_api_key
in config.yaml). If no key or anything fails, it returns [] and the render just
proceeds with normal silence cuts.
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Sequence, Tuple

from .transcribe import Word

Range = Tuple[float, float]

_DEFAULT_INSTRUCTIONS = (
    "Remove false starts, restarts and repeated takes, moments where the speaker "
    "breaks character or says things like 'wait', 'let me start over', 'I forgot "
    "the script', long awkward filler, and clearly off-topic tangents. Keep the "
    "clean, on-message delivery. Be conservative: only cut clear mistakes, never "
    "cut mid-sentence in a way that would sound abrupt."
)


def _api_key(cfg_cuts: dict) -> str:
    return os.environ.get("ANTHROPIC_API_KEY") or cfg_cuts.get("anthropic_api_key") or ""


def _transcript_lines(words: Sequence[Word]) -> str:
    """Compact, timestamped transcript for the model to reason over."""
    lines = []
    for w in words:
        lines.append(f"[{w.start:.2f}-{w.end:.2f}] {w.text}")
    return "\n".join(lines)


def plan_removals(words: Sequence[Word], cfg_cuts: dict) -> dict:
    """Ask Claude which ranges to cut.

    Returns a dict so the caller can SHOW what happened (no more silent
    no-ops):
      {"removals": [(s,e),...], "status": "ok"|"skipped"|"error",
       "reasons": [...], "detail": str}
    """
    if not words:
        return {"removals": [], "status": "skipped", "detail": "no transcript", "reasons": []}
    key = _api_key(cfg_cuts)
    if not key:
        return {"removals": [], "status": "skipped",
                "detail": "no Anthropic API key (set ANTHROPIC_API_KEY)", "reasons": []}

    try:
        import anthropic
    except Exception:
        return {"removals": [], "status": "error",
                "detail": "anthropic package not installed", "reasons": []}

    instructions = cfg_cuts.get("smart_cut_instructions") or _DEFAULT_INSTRUCTIONS
    model = cfg_cuts.get("smart_cut_model") or "claude-sonnet-5"
    transcript = _transcript_lines(words)

    system = (
        "You are a short-form video editor. You are given a word-level transcript "
        "with [start-end] timestamps in seconds. Decide which time ranges to CUT so "
        "the final clip is tight and clean. " + instructions + "\n\n"
        "Respond with ONLY a JSON array of objects {\"start\": number, \"end\": "
        "number, \"reason\": string}, timestamps in seconds, no prose. Empty array "
        "if nothing should be cut."
    )

    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model, max_tokens=1500, system=system,
            messages=[{"role": "user", "content": transcript}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\[.*\]", raw, re.S)
        data = json.loads(m.group(0)) if m else []
    except Exception as exc:
        return {"removals": [], "status": "error", "detail": f"{type(exc).__name__}: {exc}", "reasons": []}

    ranges: List[Range] = []
    reasons: List[str] = []
    for item in data:
        try:
            s, e = float(item["start"]), float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e > s:
            ranges.append((s, e))
            reasons.append(str(item.get("reason", "")))
    return {"removals": _merge(ranges), "status": "ok", "reasons": reasons,
            "detail": f"cut {len(ranges)} range(s) via {model}"}


def _merge(ranges: List[Range]) -> List[Range]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    out = [ranges[0]]
    for s, e in ranges[1:]:
        if s <= out[-1][1] + 0.05:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
