"""Turn a plain-English instruction into concrete render option overrides.

Understands the FULL toolset, so requests like:
    "cut the parts without dogs, take the audio out and put music over it,
     add your own captions, no watermark"
actually change what gets rendered. Uses Claude when ANTHROPIC_API_KEY is set
(richer understanding); otherwise falls back to keyword rules. Returns
(overrides_dict, notes) — notes are shown back so you can see how it was read.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Tuple

# What the instruction can control, described for the model.
_CAPABILITIES = """
Options you may set (include ONLY what the request asks for; omit the rest):
- cuts.enabled (bool): trim silences / dead air.
- cuts.min_gap (number, seconds): smaller = tighter, snappier cuts.
- cuts.smart_cut (bool): use AI to cut spoken mistakes, false starts, "I forgot
  the script", off-topic rambling.
- cuts.dog_cut (bool): keep ONLY the parts of the video where a dog/puppy is
  actually on screen; cut everything else. Use when they say things like "cut
  the parts without dogs", "only show the puppies", "when there's no dog".
- captions.enabled (bool): burned-in animated captions.
- captions.uppercase (bool): ALL-CAPS captions.
- captions.language (str, e.g. "es"): force a language.
- zoom.enabled (bool), zoom.intensity (number ~0.03 subtle .. 0.12 strong).
- music.enabled (bool): background music bed.
- music.volume (number 0..1).
- music.replace_voice (bool): remove the person's voice entirely and play only
  music over the video. Use for "take the audio out and put music over it",
  "no talking", "just music", "instrumental". (Captions are still generated
  from what was said.)
- watermark.enabled (bool).
- cta.enabled (bool): the end card.
- output.max_duration (number, seconds): TARGET length — the clip is compressed
  (dead air trimmed + gently sped up) to FIT everything into this many seconds;
  it is NOT chopped off. e.g. "make it 30 seconds" -> 30, "fit it in a minute"
  -> 60, "keep it to 15s" -> 15.
- graphics.enabled (bool): the smart title card + animated word pop-ups. Turn
  OFF for "no text pops", "no graphics", "just captions", "plain".
- graphics.headline (str): force the opening hook text, e.g. 'say "3 reasons"'.
- output.width / output.height (ints): the canvas. 1080x1920 = 9:16 vertical
  (reels/tiktok/shorts), 1920x1080 = 16:9 widescreen (youtube/landscape),
  1080x1080 = square. Set BOTH together when the request implies an orientation.
- output.reframe (str): how footage fits the canvas — "cover_center" (fill+crop,
  good for 9:16), "blur_fill" (fit in front of a blurred copy, good for 16:9 so
  the subject isn't cropped), "fit_pad" (letterbox). Prefer blur_fill for 16:9.
"""


def _strip_apos(s: str) -> str:
    return s.replace("'", "").replace("’", "")


def _has(text: str, *phrases: str) -> bool:
    t = _strip_apos(text)  # so "don't" and "dont" both match
    return any(re.search(r"\b" + re.escape(_strip_apos(p)) + r"\b", t) for p in phrases)


def interpret(text: str, base_cfg: dict | None = None) -> Tuple[Dict, List[str]]:
    text = (text or "").strip()
    if not text:
        return {}, []
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            o, notes = _interpret_llm(text)
        except Exception as exc:  # fall back, but leave a breadcrumb
            o, notes = _interpret_rules(text.lower())
            notes = notes + [f"(AI interpret failed: {type(exc).__name__}; used keywords)"]
    else:
        o, notes = _interpret_rules(text.lower())

    # Always apply these deterministic parses on top (reliable, not model-guessed):
    # explicit word corrections ("change X to Y") and protect-the-ending.
    corr = _parse_corrections(text)
    if corr:
        o.setdefault("captions", {}).setdefault("corrections", {}).update(corr)
        notes.append("fix words: " + ", ".join(f"{k}→{v}" for k, v in corr.items()))
    if _has(text.lower(), "cut off the last", "cut off the end", "don't cut the end",
            "dont cut the end", "keep the ending", "keep the end", "cut the last word",
            "cut off the last word", "last word got cut", "ending got cut"):
        o.setdefault("cuts", {}).update({"keep_pad": 0.5, "min_gap": 0.8})
        notes.append("protect the ending")
    return o, notes


def _parse_corrections(text: str) -> Dict[str, str]:
    """Pull explicit caption fixes out of the text: 'change X to Y',
    'fix X to Y', 'replace X with Y', 'say Y not X'. Returns {wrong: right}."""
    out: Dict[str, str] = {}

    def clean(s: str) -> str:
        return s.strip().strip('"\'“”').strip().rstrip(".,!?")

    for m in re.finditer(r"\b(?:change|fix|replace|correct|swap)\s+(.+?)\s+(?:to|with|into|for)\s+(.+?)(?:[.,;]|$)", text, re.I):
        wrong, right = clean(m.group(1)), clean(m.group(2))
        if wrong and right and wrong.lower() != right.lower():
            out[wrong] = right
    for m in re.finditer(r"\b(?:it should say|should say|should be|say)\s+(.+?)\s+not\s+(.+?)(?:[.,;]|$)", text, re.I):
        right, wrong = clean(m.group(1)), clean(m.group(2))
        if wrong and right and wrong.lower() != right.lower():
            out[wrong] = right
    return out


def _interpret_rules(t: str) -> Tuple[Dict, List[str]]:
    o: Dict = {}
    notes: List[str] = []

    def set_(section, key, val, note):
        o.setdefault(section, {})[key] = val
        notes.append(note)

    # music-only / remove voice
    if _has(t, "take the audio out", "take audio out", "remove the audio", "remove audio",
            "remove the voice", "no talking", "no voice", "mute the voice", "mute voice",
            "just music", "music only", "only music", "instrumental", "put music over",
            "music over it", "replace the audio", "silence the voice"):
        o.setdefault("music", {}).update({"enabled": True, "replace_voice": True})
        notes.append("music-only (voice removed)")
    elif _has(t, "no music", "without music", "mute music", "no background music", "no track"):
        set_("music", "enabled", False, "music off")
    elif _has(t, "loud music", "louder music", "more music", "music up"):
        set_("music", "volume", 0.35, "music louder")
    elif _has(t, "quiet music", "soft music", "softer music", "music down", "subtle music"):
        set_("music", "volume", 0.10, "music quieter")
    elif _has(t, "add music", "put music", "background music", "with music", "add a song"):
        set_("music", "enabled", True, "music on")

    # dog-only cutting (computer vision)
    if _has(t, "cut the parts without dogs", "parts without dogs", "cut parts that don't have dogs",
            "parts that don't have dogs", "only show dogs", "only show the dogs", "only the dogs",
            "only show puppies", "only show the puppies", "show the puppies", "puppies only",
            "only the puppies", "no dog", "without a dog", "where there's no dog",
            "cut to dogs", "only parts with dogs", "only parts with puppies", "keep only the dogs",
            "keep the dog parts"):
        o.setdefault("cuts", {}).update({"enabled": True, "dog_cut": True})
        notes.append("cut to dog moments only")

    # captions
    if _has(t, "no captions", "without captions", "no subtitles", "no text"):
        set_("captions", "enabled", False, "captions off")
    elif _has(t, "add captions", "add your own captions", "your own captions", "put captions",
              "with captions", "caption it", "add subtitles"):
        set_("captions", "enabled", True, "captions on")
    if _has(t, "all caps", "uppercase", "caps captions"):
        set_("captions", "uppercase", True, "uppercase captions")

    # smart cut (spoken mistakes)
    if _has(t, "cut mistakes", "remove mistakes", "cut the flubs", "cut flubs", "smart cut",
            "remove the mistakes", "cut out mistakes", "he messed up", "cut the bad takes"):
        set_("cuts", "smart_cut", True, "AI smart-cut on")

    # watermark
    if _has(t, "no watermark", "without watermark", "remove watermark", "no logo"):
        set_("watermark", "enabled", False, "watermark off")

    # zoom / motion
    if _has(t, "no zoom", "static", "no motion", "no movement", "hold still"):
        set_("zoom", "enabled", False, "zoom off")
    elif _has(t, "punchy", "energetic", "more zoom", "dynamic", "lots of movement", "punch"):
        o.setdefault("zoom", {}).update({"enabled": True, "intensity": 0.11})
        notes.append("stronger zoom")
    elif _has(t, "subtle", "calm", "gentle", "slow", "minimal motion"):
        o.setdefault("zoom", {}).update({"enabled": True, "intensity": 0.04})
        notes.append("subtle zoom")

    # cuts pacing
    if _has(t, "don't cut", "do not cut", "no cuts", "keep pauses", "keep the pauses", "no trimming"):
        set_("cuts", "enabled", False, "auto-cuts off")
    elif _has(t, "tight", "cut more", "aggressive cuts", "fast paced", "snappy", "remove pauses"):
        o.setdefault("cuts", {}).update({"enabled": True, "min_gap": 0.35})
        notes.append("tighter cuts")

    # CTA
    if _has(t, "cta", "end card", "call to action", "outro", "add the card", "closing card"):
        set_("cta", "enabled", True, "CTA end card on")

    # aspect / orientation
    if _has(t, "16:9", "16 by 9", "widescreen", "wide screen", "landscape", "horizontal",
            "for youtube", "youtube video", "long form", "long-form"):
        o.setdefault("output", {}).update({"width": 1920, "height": 1080, "reframe": "blur_fill"})
        notes.append("16:9 widescreen")
    elif _has(t, "9:16", "9 by 16", "vertical", "portrait", "for reels", "for a reel",
              "for tiktok", "for shorts", "short form", "short-form"):
        o.setdefault("output", {}).update({"width": 1080, "height": 1920, "reframe": "cover_center"})
        notes.append("9:16 vertical")
    elif _has(t, "square", "1:1", "1 by 1"):
        o.setdefault("output", {}).update({"width": 1080, "height": 1080, "reframe": "blur_fill"})
        notes.append("square 1:1")

    # smart graphics (title card + word pops)
    if _has(t, "no text pops", "no pops", "no graphics", "no title card", "no text overlay",
            "just captions", "plain", "no popups", "no pop ups"):
        set_("graphics", "enabled", False, "graphics off")
    elif _has(t, "add pops", "text pops", "add graphics", "title card", "add a hook",
              "add popups", "pop ups", "make it punchy", "add text pops"):
        set_("graphics", "enabled", True, "graphics on")

    # target length (fit everything into it, don't chop)
    secs = _parse_length(t)
    if secs:
        set_("output", "max_duration", secs, f"fit into {secs:g}s")

    # language
    for lang, code in {"spanish": "es", "french": "fr", "german": "de", "portuguese": "pt"}.items():
        if _has(t, lang):
            set_("captions", "language", code, f"language: {code}")

    return o, notes


def _parse_length(t: str) -> float | None:
    """Pull a target length in seconds out of the text, if any."""
    if _has(t, "under a minute", "less than a minute", "below a minute"):
        return 60.0
    if _has(t, "half a minute"):
        return 30.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(seconds|second|secs|sec|s)\b", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(minutes|minute|mins|min|m)\b", t)
    if m:
        return float(m.group(1)) * 60.0
    return None


def _interpret_llm(text: str) -> Tuple[Dict, List[str]]:
    """Use Claude to map free text onto option overrides (needs API key)."""
    import anthropic

    client = anthropic.Anthropic()
    system = (
        "You configure an AI video editor (short-form 9:16 vertical OR long-form "
        "16:9 widescreen) from a plain-English request. Respect any orientation the "
        "request implies. "
        + _CAPABILITIES
        + "\nReturn ONLY JSON: {\"options\": {nested overrides}, \"summary\": [short "
        "human phrases of what you changed]}. Include only options the request "
        "clearly implies. If it says to cut parts without dogs, set cuts.dog_cut "
        "true. If it says take the audio out / put music over it, set "
        "music.replace_voice true and music.enabled true."
    )
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    overrides = data.get("options", data) if isinstance(data, dict) else {}
    summary = data.get("summary") if isinstance(data, dict) else None
    if not summary:
        summary = ["interpreted by Claude"]
    return overrides, [str(s) for s in summary]
