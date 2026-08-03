"""The edit plan — the editor's brain.

Before a single frame is rendered, this module looks at the transcript and the
chosen format and makes editorial decisions: what the opening should be, which
weak/dead parts to drop, and a plain-English list of what it did (surfaced to
the user as the "What I did" summary). It writes ONLY into settings the render
pipeline already consumes, so the plan and the render can never drift, and if
anything here fails the pipeline still falls back to its deterministic path.

Two levels:
- rule-based (always on, no network): weak-intro trim, opening strategy,
  the decisions summary.
- optional Claude pass (when ANTHROPIC_API_KEY is set): a richer opening choice
  + extra removals with reasons. Guarded; failure degrades to the rules.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .transcribe import Word

Segment = Tuple[float, float]

# Greeting / filler that a strong short-form open should skip.
_FILLER = {
    "hi", "hey", "hello", "yo", "hiya", "heya", "sup", "guys", "everyone",
    "everybody", "y'all", "yall", "folks", "um", "uh", "erm", "so", "okay",
    "ok", "alright", "alrighty", "well", "welcome", "back", "whats", "what's",
    "how", "are", "you", "doing", "today", "basically", "just", "wanna",
    "gonna", "like", "yeah",
}
# words that signal real content has started (never treat as filler)
_STRONG_HINT = re.compile(r"\d|\$|%")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9']", "", t.lower())


def find_weak_intro(words: Sequence[Word], max_seconds: float = 5.0,
                    max_words: int = 8) -> Optional[Segment]:
    """If the clip opens with greeting/filler ("hey guys, so today…"), return the
    span to drop so it starts on the first real word. Conservative: only trims a
    short leading run of clearly-filler words."""
    if not words:
        return None
    i = 0
    n = min(len(words), max_words)
    while i < n and words[i].start <= max_seconds:
        tok = _norm(words[i].text)
        if not tok or (tok in _FILLER and not _STRONG_HINT.search(words[i].text)):
            i += 1
            continue
        break
    if i == 0 or i >= len(words):
        return None
    # need real content to remain, and don't nuke more than ~4.5s
    if words[i].start > 4.5 or (len(words) - i) < 3:
        return None
    return (0.0, float(words[i].start))


def build_edit_plan(fmt: str, words: Sequence[Word], cfg: dict) -> Dict:
    """Produce the plan. Returns dict with keys: opening_strategy, removals
    (list of (start,end,kind,reason)), headline (str|None), notes (list)."""
    fmt = "long" if str(fmt).lower() == "long" else "short"
    plan: Dict = {"opening_strategy": "chronological", "removals": [],
                  "headline": None, "notes": []}

    if fmt == "short" and words and cfg.get("cuts", {}).get("enabled", True):
        plan["opening_strategy"] = "strongest_hook"
        intro = find_weak_intro(words)
        if intro:
            plan["removals"].append((intro[0], intro[1], "weak_intro",
                                     "skipped the greeting so it opens on the real content"))
            plan["notes"].append("trimmed the weak intro")

    # optional richer plan from Claude (never required)
    if os.environ.get("ANTHROPIC_API_KEY") and words:
        try:
            _llm_enrich(fmt, words, plan)
        except Exception as exc:  # keep the rule-based plan
            plan["notes"].append(f"(AI plan skipped: {type(exc).__name__})")

    return plan


def _llm_enrich(fmt: str, words: Sequence[Word], plan: Dict) -> None:
    import json

    import anthropic

    transcript = " ".join(w.text for w in words)
    client = anthropic.Anthropic()
    sys = (
        "You are a video editor planning a " + fmt + "-form edit. From the "
        "transcript, return ONLY JSON: {\"headline\": short 2-5 word hook or null, "
        "\"cut_phrases\": [exact short quotes to REMOVE — false starts, mistakes, "
        "rambling, 'I forgot the script']}. Keep cut_phrases short and verbatim."
    )
    msg = client.messages.create(
        model="claude-sonnet-5", max_tokens=600, system=sys,
        messages=[{"role": "user", "content": transcript[:4000]}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return
    data = json.loads(m.group(0))
    # (headline intentionally not taken from the LLM — the on-screen title only
    #  comes from a clear enumeration hook, never invented text.)
    for phrase in (data.get("cut_phrases") or [])[:12]:
        span = _locate(words, str(phrase))
        if span:
            plan["removals"].append((span[0], span[1], "mistake", f"removed “{phrase[:40]}”"))
    if data.get("cut_phrases"):
        plan["notes"].append("AI removed spoken mistakes")


def auto_direct(words: Sequence[Word], info, instruction: str = "", fmt: str = "short") -> Optional[Dict]:
    """AI creative director — decide the WHOLE edit from the content, so the user
    (or an automated workflow) doesn't configure anything. Returns a decisions
    dict, or None when Claude isn't available (caller falls back to heuristics).

    Decides: captions off/clean/dynamic, music off/subtle/energetic, a target
    length, and an optional short hook. The detailed cuts are handled separately
    by the smart-cut pass.
    """
    if not words or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import json as _json

        import anthropic

        transcript = " ".join(w.text for w in words)
        dur = getattr(info, "duration", 0.0) or 0.0
        model = os.environ.get("SSGP_MODEL") or "claude-sonnet-5"
        sys = (
            "You are the creative director for Sugar Sweet Georgia Puppies (a puppy store). "
            "Decide how to turn this RAW clip into the best possible " + fmt + "-form social "
            "video. Judge from what is said, the energy, and the length — make real choices, "
            "don't add things by default. Return ONLY JSON:\n"
            '{"captions":"off|clean|dynamic","music":"off|subtle|energetic",'
            '"target_seconds": number or null, "hook": short 2-5 word title or null, '
            '"reasoning":"one short sentence"}\n'
            "Guidance: captions DYNAMIC for punchy talking that benefits from emphasis; CLEAN "
            "for calm/informational talking; OFF when there's little meaningful speech (mostly "
            "ambience, music or cuteness) — it doesn't always need captions. Music ENERGETIC for "
            "fun/fast, SUBTLE for calm, OFF when the talking should stand alone. A hook only if "
            "there's a genuinely strong opening line; otherwise null. Short-form target 15-60s."
        )
        user = f"Length: {dur:.0f}s.\nTranscript: {transcript[:3500]}"
        if instruction.strip():
            user += f"\nThe user's goal (respect it): {instruction.strip()}"
        client = anthropic.Anthropic()
        msg = client.messages.create(model=model, max_tokens=400, system=sys,
                                     messages=[{"role": "user", "content": user}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        d = _json.loads(m.group(0)) if m else {}
        return _clean_direction(d)
    except Exception:
        return None


def auto_heuristic(words: Sequence[Word], info, fmt: str = "short") -> Dict:
    """No-LLM fallback director: sensible defaults from simple signals."""
    dur = getattr(info, "duration", 0.0) or 0.0
    n = len(words)
    speech_ratio = (sum(w.end - w.start for w in words) / dur) if (dur and words) else 0.0
    if n < 4 or speech_ratio < 0.12:
        caps = "off"            # barely any talking -> no captions
    elif fmt == "long":
        caps = "clean"
    else:
        caps = "dynamic"
    return _clean_direction({"captions": caps, "music": "subtle", "target_seconds": None,
                             "hook": None, "reasoning": "auto (no AI key): chose from speech amount"})


def _clean_direction(d: Dict) -> Dict:
    caps = str(d.get("captions", "dynamic")).lower()
    if caps not in ("off", "clean", "dynamic"):
        caps = "dynamic"
    mus = str(d.get("music", "subtle")).lower()
    if mus not in ("off", "subtle", "energetic"):
        mus = "subtle"
    tgt = d.get("target_seconds")
    try:
        tgt = float(tgt) if tgt not in (None, "", "null") else None
    except (TypeError, ValueError):
        tgt = None
    hook = d.get("hook")
    hook = str(hook)[:40] if hook and str(hook).lower() not in ("null", "none", "") else None
    return {"captions": caps, "music": mus, "target_seconds": tgt, "hook": hook,
            "reasoning": str(d.get("reasoning", ""))[:200]}


def _locate(words: Sequence[Word], phrase: str) -> Optional[Segment]:
    """Find a phrase's time span in the word list by normalized-token match."""
    toks = [_norm(t) for t in phrase.split() if _norm(t)]
    if not toks:
        return None
    wt = [_norm(w.text) for w in words]
    for i in range(len(wt) - len(toks) + 1):
        if wt[i:i + len(toks)] == toks:
            return (float(words[i].start), float(words[i + len(toks) - 1].end))
    return None


# ---------------------------------------------------------------------------
# "What I did" summary — assembled from what actually happened
# ---------------------------------------------------------------------------

def summarize(applied: dict, cfg: dict) -> List[str]:
    """Human-readable edit decisions, built from the real applied data so it can
    never claim something the render didn't do."""
    out: List[str] = []
    fmt = applied.get("format", "short")
    W, H = applied.get("width"), applied.get("height")
    out.append(f"Made a {'long-form 16:9' if fmt == 'long' else 'short-form 9:16'} video ({W}×{H}).")

    rf = applied.get("reframe")
    if rf == "blur_fill":
        out.append("Fit the footage with a blurred background so the subject is never cropped.")
    elif rf in ("cover_center", "cover_at"):
        out.append("Reframed to fill the vertical frame.")

    ad = applied.get("auto_director")
    if isinstance(ad, dict):
        note = ad.get("reasoning") or "AI chose the whole edit"
        out.append("AI director: " + note)
        out.append(f"Chose captions: {ad.get('captions')}, music: {ad.get('music')}.")
    if applied.get("ai_editing"):
        out.append("AI editor read the transcript and edited to match your description.")
    if applied.get("intro_trimmed"):
        out.append("Cut the weak intro so it opens on the real content.")
    sc = applied.get("smart_cut")
    if isinstance(sc, dict) and sc.get("removed"):
        reasons = [r for r in (sc.get("reasons") or []) if r][:3]
        line = f"Cut {len(sc['removed'])} part(s) the AI judged weak"
        if reasons:
            line += ": " + "; ".join(reasons)
        out.append(line + ".")
    sil = applied.get("silences_found")
    if sil:
        out.append(f"Tightened {sil} silent gap(s) / dead air.")

    src, dur = applied.get("source_duration"), applied.get("output_duration")
    if src and dur and dur < src - 0.2:
        out.append(f"Tightened the length from {src:.0f}s to {dur:.0f}s.")
    if applied.get("speed"):
        out.append(f"Sped up {applied['speed']}× to fit the target (nothing cut).")

    g = applied.get("graphics")
    if isinstance(g, dict) and (g.get("hook") or g.get("pops")):
        bits = []
        if g.get("hook"):
            bits.append(f"a “{g['hook']}” hook")
        if g.get("pops"):
            bits.append(f"{g['pops']} word pop-up(s)")
        out.append("Added " + " and ".join(bits) + ".")
    if applied.get("captions"):
        mode = cfg.get("captions", {}).get("mode", "dynamic")
        out.append(f"Burned in {mode} captions, synced to the speech.")
    if applied.get("corrections"):
        out.append(f"Fixed {len(applied['corrections'])} misheard word(s).")

    if applied.get("audio_cleaned"):
        out.append("Cleaned up the audio — leveled the voice and rolled off low rumble.")
    music = applied.get("music")
    if music:
        out.append(f"Laid in background music ({music}), ducked under the voice.")
    if applied.get("hdr_tonemapped"):
        out.append("Corrected HDR color to standard range.")
    if applied.get("cta"):
        out.append("Added an end card with the business name and phone number.")
    return out
