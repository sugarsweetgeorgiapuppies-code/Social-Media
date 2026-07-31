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
from .config import ROOT
from .transcribe import Word


# ---------------------------------------------------------------------------
# Logo helpers (watermark + CTA)
# ---------------------------------------------------------------------------


def _resolve_asset(path) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p if p.exists() else None


_LOGO_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _resolve_logo(path) -> Optional[Path]:
    """Find the logo: the configured path if it exists, otherwise ANY image
    dropped in the assets/ folder (so the exact filename doesn't matter)."""
    p = _resolve_asset(path)
    if p:
        return p
    assets = ROOT / "assets"
    if assets.exists():
        imgs = sorted(f for f in assets.iterdir() if f.suffix.lower() in _LOGO_EXT)
        if imgs:
            return imgs[0]
    return None


def _remove_white_bg(logo: "Image.Image", thresh: int = 35) -> "Image.Image":
    """Make only the background-connected near-white transparent (flood-fill
    from the corners), so interior white — like the dog's white body — stays."""
    w, h = logo.size
    rgb = logo.convert("RGB")
    marker = (255, 0, 254)
    filled = False
    for c in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        r, g, b = rgb.getpixel(c)
        if r > 228 and g > 228 and b > 228:
            ImageDraw.floodfill(rgb, c, marker, thresh=thresh)
            filled = True
    if not filled:
        return logo  # already transparent, or no white border
    out = logo.copy()
    px, rp = out.load(), rgb.load()
    for y in range(h):
        for x in range(w):
            if rp[x, y] == marker:
                r, g, b, _a = px[x, y]
                px[x, y] = (r, g, b, 0)
    return out


def _load_logo(path: Path, remove_bg: bool = True) -> "Image.Image":
    logo = Image.open(path).convert("RGBA")
    return _remove_white_bg(logo) if remove_bg else logo


def _fit_width(logo: "Image.Image", target_w: float) -> "Image.Image":
    tw = max(1, int(target_w))
    th = max(1, int(logo.height * tw / logo.width))
    return logo.resize((tw, th), Image.LANCZOS)


def _apply_opacity(logo: "Image.Image", opacity: float) -> "Image.Image":
    if opacity >= 0.999:
        return logo
    alpha = logo.getchannel("A").point(lambda v: int(v * opacity))
    logo = logo.copy()
    logo.putalpha(alpha)
    return logo


def _corner_xy(position: str, W: int, H: int, lw: int, lh: int, margin_pct: float) -> Tuple[int, int]:
    m = int(min(W, H) * margin_pct)
    position = (position or "bottom-right").lower()
    x = W - lw - m if "right" in position else m
    y = H - lh - m if "bottom" in position else m
    return (x, y)

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


_REFERENCE_W = 1080  # all px sizes are authored against a 1080-wide canvas


def text_scale(W: int) -> float:
    """Scale factor so text keeps the same on-screen proportion on any canvas
    width (1.0 at 1080 wide -> unchanged short-form; ~1.78 at 1920 wide so 16:9
    isn't rendered half-size)."""
    return max(0.5, float(W) / _REFERENCE_W)


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

    s = text_scale(W)
    uppercase = bool(cap.get("uppercase", False))
    base_size = int(cap.get("font_size", 78) * s)
    hi_scale = float(cap.get("highlight_scale", 1.14))
    active_size = int(round(base_size * hi_scale))
    weight = int(cap.get("font_weight", 800))
    base_font = _font(fonts_dir, weight, base_size)
    active_font = _font(fonts_dir, weight, active_size)

    fill = _rgba(cap.get("fill_color", "#ffffff"))
    stroke = _rgba(cap.get("stroke_color", "#1a1a1a"))
    highlight = _rgba(cap.get("highlight_color", "#ffd24a"))
    stroke_w = max(1, int(cap.get("stroke_width", 6) * s))

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
    words: Sequence[Word], cap: dict, fonts_dir: Path, W: int, H: int, work: Path, fps: int = 30
) -> Optional[str]:
    """Render the animated caption line as a concat list of full-frame PNGs.

    Every state is pinned to an ABSOLUTE timestamp and each concat duration is
    just the gap to the next state. Nothing is ever clamped *up*, so durations
    can never accumulate error — captions stay locked to the voice from the
    first word to the last, no matter how close together real speech packs the
    words. Returns the ffconcat list path, or None if there are no words.
    """
    if not words:
        return None

    # optional global timing nudge (seconds); negative = show captions earlier
    offset = float(cap.get("time_offset", 0.0))
    if offset:
        words = [Word(text=w.text, start=max(0.0, w.start + offset), end=max(0.05, w.end + offset)) for w in words]

    cap_dir = work / "caps"
    cap_dir.mkdir(parents=True, exist_ok=True)
    transparent = str((cap_dir / "gap.png").resolve())
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(transparent)

    lines = group_lines(words, int(cap.get("max_chars_per_line", 22)), float(cap.get("line_pause", 0.7)))

    # "clean" captions (and long-form) render ONE still image per line instead of
    # one per word — no active-word highlight, and far fewer PNGs on long videos.
    per_line = str(cap.get("render_granularity") or
                   ("per_line" if cap.get("mode") == "clean" else "per_word")) == "per_line"

    # Build (absolute_time, image) events. Per-word: each word highlighted at its
    # own start. Per-line: the whole line appears at once. Then blank at line end.
    events: List[Tuple[float, str]] = [(0.0, transparent)]
    n = 0
    for line in lines:
        if per_line:
            frame = _draw_caption_frame(line, -1, cap, fonts_dir, W, H)  # -1 = no highlight
            fp = cap_dir / f"s{n:04d}.png"
            frame.save(fp)
            events.append((max(0.0, float(line[0].start)), str(fp.resolve())))
            n += 1
        else:
            for i, w in enumerate(line):
                frame = _draw_caption_frame(line, i, cap, fonts_dir, W, H)
                fp = cap_dir / f"s{n:04d}.png"
                frame.save(fp)
                events.append((max(0.0, float(w.start)), str(fp.resolve())))
                n += 1
        events.append((float(line[-1].end) + 0.10, transparent))  # blank after the line

    # Sort by time and enforce strictly-increasing timeline. When two states are
    # closer than one frame, keep the later image at the earlier time (drop the
    # sub-frame gap) — this NEVER adds time, so there is zero drift.
    events.sort(key=lambda e: e[0])
    min_dt = 1.0 / max(1, fps)
    pinned: List[Tuple[float, str]] = []
    for t, p in events:
        if pinned and t - pinned[-1][0] < min_dt:
            pinned[-1] = (pinned[-1][0], p)  # replace image, keep the earlier time
        else:
            pinned.append((t, p))

    list_path = work / "captions.ffconcat"
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write("ffconcat version 1.0\n")
        for idx, (t, p) in enumerate(pinned):
            nxt = pinned[idx + 1][0] if idx + 1 < len(pinned) else t + 0.3
            dur = max(min_dt, nxt - t)
            # absolute path — concat resolves relative entries against the list's dir
            fh.write(f"file '{p}'\n")
            fh.write(f"duration {dur:.3f}\n")
        # concat needs the last file repeated to flush the final segment
        fh.write(f"file '{pinned[-1][1]}'\n")
    return str(list_path)


# ---------------------------------------------------------------------------
# Watermark
# ---------------------------------------------------------------------------


def render_watermark(wm: dict, fonts_dir: Path, W: int, H: int, out_png: Path) -> str:
    """A see-through logo in a corner (preferred), or a text fallback if no logo
    file is present at wm['logo']."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    logo_path = _resolve_logo(wm.get("logo"))
    if logo_path:
        logo = _load_logo(logo_path, bool(wm.get("remove_white_bg", True)))
        logo = _fit_width(logo, W * float(wm.get("logo_width_pct", 0.26)))
        logo = _apply_opacity(logo, float(wm.get("logo_opacity", 0.35)))
        pos = _corner_xy(wm.get("position", "bottom-right"), W, H, logo.width, logo.height,
                         float(wm.get("margin_pct", 0.03)))
        img.alpha_composite(logo, pos)
    elif wm.get("text"):
        draw = ImageDraw.Draw(img)
        s = text_scale(W)
        opacity = float(wm.get("opacity", 0.88))
        font = _font(fonts_dir, int(wm.get("font_weight", 700)), int(wm.get("font_size", 34) * s))
        fill = _rgba(wm.get("fill_color", "#ffffff"), opacity)
        stroke = _rgba(wm.get("stroke_color", "#1a1a1a"), opacity)
        y = int(float(wm.get("position_y_pct", 0.045)) * H)
        draw.text((W / 2.0, y), str(wm["text"]), font=font, fill=fill, anchor="ma",
                  stroke_width=max(1, int(wm.get("stroke_width", 2) * s)), stroke_fill=stroke)
    img.save(out_png)
    return str(out_png)


# ---------------------------------------------------------------------------
# CTA end card
# ---------------------------------------------------------------------------


def render_cta_card(cta: dict, fonts_dir: Path, W: int, H: int, out_png: Path) -> str:
    """Clean outro: logo up top, then business name, location, and a big tap-to-
    call phone pill — name / number / location are the focus."""
    bg = _rgb(cta.get("background", "#0f2439"))
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    weight = int(cta.get("font_weight", 800))
    s = text_scale(W)

    def fit(text: str, size: int, max_frac: float = 0.86) -> ImageFont.FreeTypeFont:
        f = _font(fonts_dir, weight, size)
        while size > 26 and f.getlength(text) > W * max_frac:
            size -= 3
            f = _font(fonts_dir, weight, size)
        return f

    def center(text: str, size: int, color, y: float):
        if not text:
            return
        f = fit(str(text), size)
        draw.text((W / 2.0, y), str(text), font=f, fill=_rgb(color), anchor="mm")

    # --- logo near the top ---
    y = H * 0.30
    logo_path = _resolve_logo(cta.get("logo"))
    if logo_path:
        logo = _load_logo(logo_path, bool(cta.get("remove_white_bg", True)))
        logo = _fit_width(logo, W * float(cta.get("logo_width_pct", 0.62)))
        lx, ly = int((W - logo.width) / 2), int(H * 0.15)
        img.paste(logo, (lx, ly), logo)
        y = ly + logo.height + int(H * 0.055)

    name = cta.get("business") or cta.get("title") or ""
    location = cta.get("location") or cta.get("subtitle") or ""
    tagline = cta.get("cta_line") or ""
    phone = str(cta.get("phone") or "")

    if tagline:
        center(tagline, int(cta.get("tagline_size", 50) * s), cta.get("muted_color", "#bcd3e6"), y)
        y += H * 0.075
    center(name, int(cta.get("name_size", 68) * s), cta.get("title_color", "#ffffff"), y + H * 0.02)
    y += H * 0.095
    center(location, int(cta.get("location_size", 46) * s), cta.get("muted_color", "#bcd3e6"), y)
    y += H * 0.085

    # --- phone as a bright tap-to-call pill (the focus) ---
    if phone:
        f = fit(phone, int(cta.get("phone_size", 82) * s), max_frac=0.7)
        tw = f.getlength(phone)
        try:
            asc, desc = f.getmetrics()
            th = asc + desc
        except Exception:
            th = int(cta.get("phone_size", 82))
        pad_x, pad_y = int(W * 0.055), int(th * 0.42)
        cx, cy = W / 2.0, y + th * 0.1
        box = [cx - tw / 2 - pad_x, cy - th / 2 - pad_y, cx + tw / 2 + pad_x, cy + th / 2 + pad_y]
        draw.rounded_rectangle(box, radius=int(th * 0.7 + pad_y), fill=_rgb(cta.get("accent_color", "#ffd23f")))
        draw.text((cx, cy), phone, font=f, fill=_rgb(cta.get("phone_text_color", cta.get("background", "#0f2439"))), anchor="mm")

    img.save(out_png)
    return str(out_png)
