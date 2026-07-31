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


def available(cfg_cuts: dict) -> bool:
    """True when the AI editor can actually run (key present + package installed)."""
    if not _api_key(cfg_cuts):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _transcript_lines(words: Sequence[Word]) -> str:
    """Compact, timestamped transcript for the model to reason over."""
    lines = []
    for w in words:
        lines.append(f"[{w.start:.2f}-{w.end:.2f}] {w.text}")
    return "\n".join(lines)


def plan_removals(words: Sequence[Word], cfg_cuts: dict,
                  user_instruction: str = "", fmt: str = "short") -> dict:
    """Ask Claude which ranges to cut, guided by good-editing principles AND the
    user's own plain-English request.

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

    # format-aware editing philosophy
    if str(fmt).lower() == "long":
        philosophy = ("This is a LONG-FORM video. Preserve the natural flow and the full "
                      "story. Remove ONLY clear mistakes, false starts, repeated takes and "
                      "genuinely dead/off-topic stretches. Do NOT tighten aggressively and "
                      "do not remove normal pauses.")
    else:
        philosophy = ("This is a SHORT-FORM video for social media. Be decisive: keep only "
                      "the strongest, most engaging, on-message content. Cut weak intros, "
                      "rambling, repetition, filler and anything that isn't pulling its "
                      "weight, so the result is punchy and hooks fast.")

    user_block = ""
    if user_instruction.strip():
        user_block = ("\n\nThe user's specific request for THIS video (follow it closely "
                      "when deciding what to keep and cut):\n\"" + user_instruction.strip() + "\"")

    system = (
        "You are an expert video editor. You are given a word-level transcript with "
        "[start-end] timestamps in seconds. Decide which time ranges to CUT so the "
        "final video is exactly what it should be. " + philosophy + " " + instructions +
        user_block + "\n\n"
        "Return ONLY a JSON array of objects {\"start\": number, \"end\": number, "
        "\"reason\": short string}, timestamps in seconds, no prose. Never cut in a way "
        "that clips a word mid-sentence. Empty array if nothing should be cut."
    )

    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model, max_tokens=3000, system=system,
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
