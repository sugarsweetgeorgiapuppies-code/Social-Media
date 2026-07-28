"""Render all text (captions, watermark, CTA) as image overlays with Pillow.

Why: many FFmpeg builds — including the current default Homebrew build on
macOS — ship WITHOUT the text libraries (libass / freetype), so the `ass`,
`subtitles` and `drawtext` filters aren't available. Instead of depending on
that, we draw text ourselves with Pillow into transparent PNGs and composite
them with FFmpeg's `overlay` filter, which every build has. Result: the editor
works on any FFmpeg.

Captions are emitted as a concat "track" of full-frame transparent PNGs (one
per word-state, transparent in the gaps) so the whole animated caption line is
a single overlay input — not hundreds of inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from .captions import group_lines
from .transcribe import Word

_WEIGHT_FILE = {
    900: "Montserrat-ExtraBold.ttf",   # closest bundled
    800: "Montserrat-ExtraBold.ttf",
    700: "Montserrat-Bold.ttf",
    600: "Montserrat-Bold.ttf",
    400: "Montserrat-Bold.ttf",
}

_FONT_CACHE: dict = {}


def _rgb(hexs: str) -> Tuple[int, int, int]:
    h = hexs.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgba(hexs: str, alpha: float = 1.0) -> Tuple[int, int, int, int]:
    r, g, b = _rgb(hexs)
    return (r, g, b, max(0, min(255, int(round(alpha * 255)))))


def _font(fonts_dir: Path, weight: int, size: int) -> ImageFont.FreeTypeFont:
    fname = _WEIGHT_FILE.get(int(weight), "Montserrat-ExtraBold.ttf")
    path = fonts_dir / fname
    key = (str(path), size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
    return _FONT_CACHE[key]


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------


def _draw_caption_frame(
    line: Sequence[Word], active_idx: int, cap: dict, fonts_dir: Path, W: int, H: int
) -> Image.Image:
    """Draw one caption line (with one word highlighted) onto a full frame."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    uppercase = bool(cap.get("uppercase", False))
    base_size = int(cap.get("font_size", 78))
    hi_scale = float(cap.get("highlight_scale", 1.14))
    active_size = int(round(base_size * hi_scale))
    weight = int(cap.get("font_weight", 800))
    base_font = _font(fonts_dir, weight, base_size)
    active_font = _font(fonts_dir, weight, active_size)

    fill = _rgba(cap.get("fill_color", "#ffffff"))
    stroke = _rgba(cap.get("stroke_color", "#1a1a1a"))
    highlight = _rgba(cap.get("highlight_color", "#ffd24a"))
    stroke_w = int(cap.get("stroke_width", 6))

    def text_of(w: Word) -> str:
        return w.text.upper() if uppercase else w.text

    # measure total width (words + single spaces)
    space_w = base_font.getlength(" ")
    widths: List[float] = []
    for i, w in enumerate(line):
        f = active_font if i == active_idx else base_font
        widths.append(f.getlength(text_of(w)))
    total_w = sum(widths) + space_w * (len(line) - 1)

    y = int(float(cap.get("position_pct", 0.74)) * H)
    x = (W - total_w) / 2.0
    for i, w in enumerate(line):
        f = active_font if i == active_idx else base_font
        color = highlight if i == active_idx else fill
        draw.text(
            (x, y), text_of(w), font=f, fill=color, anchor="lm",
            stroke_width=stroke_w, stroke_fill=stroke,
        )
        x += widths[i] + space_w
    return img


def build_caption_track(
    words: Sequence[Word], cap: dict, fonts_dir: Path, W: int, H: int, work: Path
) -> Optional[str]:
    """Render the animated caption line as a concat list of full-frame PNGs.

    Returns the path to an ffconcat list file to be used as an overlay input,
    or None if there are no words.
    """
    if not words:
        return None
    cap_dir = work / "caps"
    cap_dir.mkdir(parents=True, exist_ok=True)

    transparent = cap_dir / "gap.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(transparent)

    lines = group_lines(words, int(cap.get("max_chars_per_line", 22)), float(cap.get("line_pause", 0.7)))
    states: List[Tuple[str, float]] = []
    cursor = 0.0
    n = 0
    for line in lines:
        line_start = line[0].start
        line_end = line[-1].end + 0.12
        if line_start > cursor + 1e-3:
            states.append((str(transparent), line_start - cursor))
        for i, w in enumerate(line):
            seg_start = w.start
            seg_end = line[i + 1].start if i + 1 < len(line) else line_end
            dur = max(0.04, seg_end - seg_start)
            frame = _draw_caption_frame(line, i, cap, fonts_dir, W, H)
            fp = cap_dir / f"s{n:04d}.png"
            frame.save(fp)
            states.append((str(fp), dur))
            n += 1
        cursor = line_end
    # small transparent tail so the last word doesn't linger
    states.append((str(transparent), 0.2))

    list_path = work / "captions.ffconcat"
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write("ffconcat version 1.0\n")
        for path, dur in states:
            fh.write(f"file '{path}'\n")
            fh.write(f"duration {dur:.3f}\n")
        # concat demuxer needs the last file repeated to flush the final segment
        fh.write(f"file '{states[-1][0]}'\n")
    return str(list_path)


# ---------------------------------------------------------------------------
# Watermark
# ---------------------------------------------------------------------------


def render_watermark(wm: dict, fonts_dir: Path, W: int, H: int, out_png: Path) -> str:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    opacity = float(wm.get("opacity", 0.88))
    font = _font(fonts_dir, int(wm.get("font_weight", 700)), int(wm.get("font_size", 34)))
    fill = _rgba(wm.get("fill_color", "#ffffff"), opacity)
    stroke = _rgba(wm.get("stroke_color", "#1a1a1a"), opacity)
    text = str(wm.get("text", ""))
    y = int(float(wm.get("position_y_pct", 0.045)) * H)
    draw.text(
        (W / 2.0, y), text, font=font, fill=fill, anchor="ma",
        stroke_width=int(wm.get("stroke_width", 2)), stroke_fill=stroke,
    )
    img.save(out_png)
    return str(out_png)


# ---------------------------------------------------------------------------
# CTA end card
# ---------------------------------------------------------------------------


def render_cta_card(cta: dict, fonts_dir: Path, W: int, H: int, out_png: Path) -> str:
    bg = _rgb(cta.get("background", "#1a1a1a"))
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    weight = int(cta.get("font_weight", 800))

    def fit_font(text: str, size: int) -> ImageFont.FreeTypeFont:
        f = _font(fonts_dir, weight, size)
        while size > 28 and f.getlength(text) > W * 0.9:
            size -= 4
            f = _font(fonts_dir, weight, size)
        return f

    def center(text: str, size: int, color, y_frac: float):
        if not text:
            return
        f = fit_font(text, size)
        draw.text((W / 2.0, H * y_frac), text, font=f, fill=_rgb(color), anchor="mm")

    center(str(cta.get("title", "")), int(cta.get("title_size", 76)), cta.get("title_color", "#ffffff"), 0.42)
    center(str(cta.get("subtitle", "")), int(cta.get("subtitle_size", 46)), cta.get("title_color", "#ffffff"), 0.53)
    center(str(cta.get("phone", "")), int(cta.get("phone_size", 64)), cta.get("accent_color", "#ffd24a"), 0.63)
    img.save(out_png)
    return str(out_png)
