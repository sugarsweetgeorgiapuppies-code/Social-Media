"""Smart on-screen graphics — the "real editing" layer.

Turns a plain talking clip into a punchy Reel: an opening HOOK title card and
animated KEYWORD POP-UPS timed to the speech (breed names, prices, "first /
second / third", "hypoallergenic", …). It's rendered as ONE transparent
overlay track (a concat of full-frame PNGs), exactly like the captions, so it
is burned on before any cutting and can never drift out of sync.

Driven by the transcript + the store knowledge base (breeds/terms/names), with
an optional Claude pass to pick a snappier hook. No API key needed — the
rule-based planner alone produces the hook, the pops and the number badges.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from .knowledge import _norm
from .textrender import _font, _rgb, _rgba, text_scale
from .transcribe import Word

# words that deserve a call-out even if they aren't in the knowledge base
_MARKETING = {
    "hypoallergenic", "microchipped", "registered", "akc", "vet", "vetted",
    "guarantee", "guaranteed", "healthy", "health", "teacup", "tiny", "potty",
    "trained", "playful", "adorable", "gorgeous", "rare", "new", "available",
    "today", "forever", "family", "home",
}
_STOP_POP = {"the", "and", "a", "an", "of", "to", "is", "are", "this", "that",
             "you", "your", "our", "we", "he", "she", "it", "they", "with"}

_NUM_WORD = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
             "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
_ORDINAL = {"first": "1", "second": "2", "third": "3", "fourth": "4",
            "fifth": "5", "1st": "1", "2nd": "2", "3rd": "3", "4th": "4", "5th": "5"}
_HOOK_NOUNS = {"things", "reasons", "tips", "ways", "facts", "steps", "rules",
               "signs", "breeds", "puppies", "reasons"}


# ---------------------------------------------------------------------------
# Planning: decide the hook + which moments get a pop
# ---------------------------------------------------------------------------

def _phrase_candidates(knowledge: Dict) -> List[Tuple[List[str], str, int]]:
    """(normalised-token-list, display text, score) for every knowledge phrase.
    Longer phrases first so 'cavapoochon' wins over 'cava…'."""
    out: List[Tuple[List[str], str, int]] = []

    def add(items, score):
        for it in items or []:
            toks = [_norm(t) for t in str(it).split() if _norm(t)]
            if toks:
                out.append((toks, str(it).strip(), score))

    add(knowledge.get("breeds"), 3)
    add(knowledge.get("names"), 2)
    add(knowledge.get("terms"), 1)
    out.sort(key=lambda r: -len(r[0]))
    return out


def _auto_hook(words: Sequence[Word]) -> Optional[str]:
    """A punchy opener from the speech: '<N> things 🐾' when they enumerate."""
    toks = [w.text.lower().strip(".,!?") for w in words[:40]]
    for i, t in enumerate(toks[:-1]):
        num = t if t.isdigit() else _NUM_WORD.get(t)
        if num and toks[i + 1] in _HOOK_NOUNS:
            return f"{num} {toks[i + 1]}"
    return None


def _ai_hook(transcript: str) -> Optional[str]:
    """Optional: let Claude write a 2-5 word hook. Silent no-op without a key."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not transcript.strip():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=220,
            system=("Write a punchy 2-5 word on-screen HOOK for a puppy-store "
                    "Reel from the transcript. Title Case, no quotes, no emoji, "
                    "no period. Just the hook."),
            messages=[{"role": "user", "content": transcript[:1200]}],
        )
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        txt = txt.strip('"“”').splitlines()[0].strip()
        return txt[:40] if txt else None
    except Exception:
        return None


def plan(words: Sequence[Word], knowledge: Dict, gfx: dict) -> Dict:
    """Return {hook, hook_end, pops:[{start,end,text,kind}], notes:[...]}."""
    notes: List[str] = []
    hook: Optional[str] = None
    if gfx.get("hook", True):
        hook = (gfx.get("headline") or "").strip() or None
        if not hook:
            hook = _auto_hook(words)
        if not hook and gfx.get("use_ai", True):
            hook = _ai_hook(" ".join(w.text for w in words))
    hook_secs = float(gfx.get("hook_seconds", 2.2))
    hook_end = hook_secs if hook else 0.0
    if hook:
        notes.append(f"hook: “{hook}”")

    pops: List[Dict] = []
    if gfx.get("pops", True) and words:
        cands = _phrase_candidates(knowledge)
        wl = list(words)
        i = 0
        while i < len(wl):
            raw = wl[i].text
            low = raw.lower().strip(".,!?;:")
            norm = _norm(raw)
            matched = False

            # knowledge phrase (breed/name/term), longest first
            for toks, disp, score in cands:
                n = len(toks)
                if i + n <= len(wl) and [_norm(wl[j].text) for j in range(i, i + n)] == toks:
                    pops.append({"start": wl[i].start, "end": wl[i + n - 1].end,
                                 "text": disp, "kind": "keyword", "score": score})
                    i += n
                    matched = True
                    break
            if matched:
                continue

            # (Number badges intentionally disabled — they felt gimmicky. The
            #  spoken "number one/two" still reads fine in the captions.)

            # price / number
            if re.search(r"\d", raw) and not re.fullmatch(r"[a-z]+", low):
                pops.append({"start": wl[i].start, "end": wl[i].end,
                             "text": raw.strip(".,!?"), "kind": "number", "score": 2})
                i += 1
                continue

            # marketing word
            if low in _MARKETING and low not in _STOP_POP:
                pops.append({"start": wl[i].start, "end": wl[i].end,
                             "text": low, "kind": "keyword", "score": 1})
                i += 1
                continue
            i += 1

    # thin them out: highest score first, respect spacing + hook window + cap
    pops.sort(key=lambda p: (-p["score"], p["start"]))
    min_gap = float(gfx.get("min_spacing", 2.0))
    hold = float(gfx.get("pop_hold", 1.1))
    kept: List[Dict] = []
    for p in pops:
        if p["start"] < hook_end + 0.25:
            continue
        if any(abs(p["start"] - k["start"]) < min_gap for k in kept):
            continue
        kept.append(p)
        if len(kept) >= int(gfx.get("max_pops", 7)):
            break
    kept.sort(key=lambda p: p["start"])
    # give each pop a hold, but never let it run into the next one
    for idx, p in enumerate(kept):
        end = max(p["end"], p["start"] + hold)
        if idx + 1 < len(kept):
            end = min(end, kept[idx + 1]["start"] - 0.05)
        p["end"] = max(p["start"] + 0.4, end)
    if kept:
        notes.append(f"{len(kept)} text pop{'s' if len(kept) != 1 else ''}")

    return {"hook": hook, "hook_end": hook_end, "pops": kept, "notes": notes}


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _wrap(text: str, max_chars: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines[:3]


def _fit(fonts_dir: Path, weight: int, text: str, size: int, W: int, max_frac: float) -> ImageFont.FreeTypeFont:
    f = _font(fonts_dir, weight, size)
    while size > 30 and f.getlength(text) > W * max_frac:
        size -= 4
        f = _font(fonts_dir, weight, size)
    return f


def _draw_hook(img: "Image.Image", text: str, gfx: dict, fonts_dir: Path, W: int, H: int) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    weight = 800
    s = text_scale(W)
    lines = _wrap(text, int(gfx.get("hook_wrap", 15)))
    size = int(gfx.get("hook_size", 92) * s)
    font = lines and _fit(fonts_dir, weight, max(lines, key=len), size, W, 0.82) or _font(fonts_dir, weight, size)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.06)
    block_h = lh * len(lines)
    top = int(float(gfx.get("hook_pos_pct", 0.16)) * H)

    # translucent band behind the headline
    pad_x, pad_y = int(W * 0.06), int(lh * 0.34)
    max_w = max(font.getlength(ln) for ln in lines)
    band = [W / 2 - max_w / 2 - pad_x, top - pad_y,
            W / 2 + max_w / 2 + pad_x, top + block_h + pad_y]
    draw.rounded_rectangle(band, radius=int(lh * 0.45),
                           fill=_rgba(gfx.get("hook_band", "#12263a"),
                                      float(gfx.get("hook_band_opacity", 0.72))))
    fill = _rgb(gfx.get("hook_color", "#ffffff"))
    stroke = _rgb(gfx.get("pop_stroke", "#12263a"))
    y = top
    for ln in lines:
        draw.text((W / 2, y), ln, font=font, fill=fill, anchor="ma",
                  stroke_width=max(1, int(gfx.get("hook_stroke", 5) * s)), stroke_fill=stroke)
        y += lh


def _draw_pop(img: "Image.Image", text: str, kind: str, scale: float,
              gfx: dict, fonts_dir: Path, W: int, H: int) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    weight = 800
    s = text_scale(W) * scale
    cy = float(gfx.get("pop_pos_pct", 0.42)) * H

    if kind == "badge":
        # a big number in a brand circle
        base = int(gfx.get("badge_size", 150) * s)
        r = base // 2
        cx = W / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=_rgb(gfx.get("pop_color", "#ffd23f")),
                     outline=_rgb(gfx.get("pop_stroke", "#12263a")), width=max(1, int(base * 0.06)))
        f = _font(fonts_dir, weight, int(base * 0.62))
        draw.text((cx, cy), text, font=f, fill=_rgb(gfx.get("pop_stroke", "#12263a")), anchor="mm")
        return

    disp = text.upper() if gfx.get("pop_uppercase", True) else text
    size = int(gfx.get("pop_size", 104) * s)
    f = _fit(fonts_dir, weight, disp, size, W, 0.88)
    stroke_w = max(1, int(gfx.get("pop_stroke_w", 8) * text_scale(W)))
    off = max(2, int(4 * text_scale(W)))
    # soft shadow then the word
    draw.text((W / 2 + off, cy + off), disp, font=f, fill=(0, 0, 0, 120), anchor="mm",
              stroke_width=stroke_w, stroke_fill=(0, 0, 0, 120))
    draw.text((W / 2, cy), disp, font=f, fill=_rgb(gfx.get("pop_color", "#ffd23f")), anchor="mm",
              stroke_width=stroke_w, stroke_fill=_rgb(gfx.get("pop_stroke", "#12263a")))


# ---------------------------------------------------------------------------
# Timeline flattening -> one overlay concat track
# ---------------------------------------------------------------------------

Element = Tuple[float, float, Callable[["Image.Image"], None]]


def _flatten(elements: List[Element], W: int, H: int, work: Path, fps: int) -> Optional[str]:
    """Render overlapping timed elements into a single ffconcat overlay track."""
    if not elements:
        return None
    gdir = work / "gfx"
    gdir.mkdir(parents=True, exist_ok=True)
    transparent = str((gdir / "gap.png").resolve())
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(transparent)

    bounds = sorted({0.0} | {e[0] for e in elements} | {e[1] for e in elements})
    events: List[Tuple[float, str]] = []
    n = 0
    for k in range(len(bounds) - 1):
        t0, t1 = bounds[k], bounds[k + 1]
        if t1 - t0 < 1e-3:
            continue
        mid = (t0 + t1) / 2
        active = [e for e in elements if e[0] <= mid <= e[1]]
        if not active:
            events.append((t0, transparent))
            continue
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for _, _, draw_fn in active:
            draw_fn(img)
        fp = gdir / f"g{n:04d}.png"
        img.save(fp)
        events.append((t0, str(fp.resolve())))
        n += 1
    events.append((bounds[-1], transparent))  # blank tail so pops disappear

    min_dt = 1.0 / max(1, fps)
    list_path = work / "graphics.ffconcat"
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write("ffconcat version 1.0\n")
        for idx, (t, p) in enumerate(events):
            nxt = events[idx + 1][0] if idx + 1 < len(events) else t + 0.3
            dur = max(min_dt, nxt - t)
            fh.write(f"file '{p}'\n")
            fh.write(f"duration {dur:.3f}\n")
        fh.write(f"file '{events[-1][1]}'\n")
    return str(list_path)


def build_graphics_track(words: Sequence[Word], knowledge: Dict, gfx: dict,
                         fonts_dir: Path, W: int, H: int, work: Path, fps: int = 30) -> Tuple[Optional[str], Dict]:
    """Plan + render the graphics overlay. Returns (ffconcat_path_or_None, summary)."""
    p = plan(words, knowledge, gfx)
    elements: List[Element] = []

    if p["hook"]:
        hook = p["hook"]
        elements.append((0.0, p["hook_end"],
                         lambda img, h=hook: _draw_hook(img, h, gfx, fonts_dir, W, H)))

    for pop in p["pops"]:
        text, kind = pop["text"], pop["kind"]
        start, end = float(pop["start"]), float(pop["end"])
        punch = min(0.10, max(0.04, (end - start) * 0.2))
        # quick punch-in (overshoot) then settle — reads as a "pop"
        elements.append((start, start + punch,
                         lambda img, t=text, k=kind: _draw_pop(img, t, k, 1.14, gfx, fonts_dir, W, H)))
        elements.append((start + punch, end,
                         lambda img, t=text, k=kind: _draw_pop(img, t, k, 1.0, gfx, fonts_dir, W, H)))

    track = _flatten(elements, W, H, work, fps)
    summary = {"hook": p["hook"], "pops": len(p["pops"]), "notes": p["notes"]}
    return track, summary
