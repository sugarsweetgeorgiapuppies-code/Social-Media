"""Build an animated word-by-word caption track (ASS subtitles).

Words are grouped into short lines (<= max_chars_per_line, broken on natural
pauses). For every word we emit one subtitle event showing the whole line with
the currently-spoken word highlighted — colour swap plus a subtle size pop —
so the caption reads karaoke-style while staying on brand (white fill, dark
stroke, Montserrat 800, lower third).
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .ffmpeg_utils import hex_to_ass
from .transcribe import Word

# Map a numeric font weight to the family name libass should resolve, plus the
# ASS Bold flag. Bundled fonts expose these family names (see fonts/).
_WEIGHT_FONT = {
    900: ("Montserrat Black", 0),
    800: ("Montserrat ExtraBold", 0),
    700: ("Montserrat", 1),
    600: ("Montserrat SemiBold", 0),
    500: ("Montserrat Medium", 0),
    400: ("Montserrat", 0),
}


def font_for_weight(weight: int) -> Tuple[str, int]:
    if weight in _WEIGHT_FONT:
        return _WEIGHT_FONT[weight]
    nearest = min(_WEIGHT_FONT, key=lambda w: abs(w - weight))
    return _WEIGHT_FONT[nearest]


def _fmt_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def _ends_sentence(text: str) -> bool:
    """True if a word ends a sentence (so the next caption line should start)."""
    t = text.rstrip('"\')')
    if not t:
        return False
    return t[-1] in ".!?" and not t[-1:].isdigit()


def group_lines(words: Sequence[Word], max_chars: int, line_pause: float) -> List[List[Word]]:
    """Group a flat word list into caption lines.

    A new line starts when the current one would overflow, on a natural spoken
    pause, OR right after a word that ends a sentence — so a caption never mixes
    the tail of one sentence with the start of the next (which reads as
    mistimed).
    """
    lines: List[List[Word]] = []
    cur: List[Word] = []
    cur_len = 0
    prev_end = None
    prev_ended_sentence = False
    for w in words:
        wlen = len(w.text)
        gap = (w.start - prev_end) if prev_end is not None else 0.0
        would_overflow = cur and (cur_len + 1 + wlen) > max_chars
        natural_break = cur and gap >= line_pause
        if would_overflow or natural_break or prev_ended_sentence:
            if cur:
                lines.append(cur)
            cur, cur_len = [], 0
        cur.append(w)
        cur_len += (1 if cur_len else 0) + wlen
        prev_end = w.end
        prev_ended_sentence = _ends_sentence(w.text)
    if cur:
        lines.append(cur)
    return lines


def build_ass(
    words: Sequence[Word],
    cap: dict,
    width: int,
    height: int,
) -> str:
    """Return a complete .ass document as a string."""
    fontname, bold = font_for_weight(int(cap.get("font_weight", 800)))
    font_size = int(cap.get("font_size", 78))
    primary = hex_to_ass(cap.get("fill_color", "#ffffff"))
    outline = hex_to_ass(cap.get("stroke_color", "#1a1a1a"))
    highlight = hex_to_ass(cap.get("highlight_color", "#ffd24a"))
    stroke_w = float(cap.get("stroke_width", 6))
    shadow = float(cap.get("shadow", 2))
    hi_scale = int(round(float(cap.get("highlight_scale", 1.14)) * 100))

    # vertical placement: baseline at position_pct down the frame.
    position_pct = float(cap.get("position_pct", 0.74))
    margin_v = max(0, int(round((1.0 - position_pct) * height)))
    side_margin = max(0, int(round((1.0 - float(cap.get("width_pct", 0.84))) / 2 * width)))
    uppercase = bool(cap.get("uppercase", False))
    max_chars = int(cap.get("max_chars_per_line", 22))
    line_pause = float(cap.get("line_pause", 0.7))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{fontname},{font_size},{primary},{primary},{outline},&H64000000,{bold},0,0,0,100,100,0,0,1,{stroke_w},{shadow},2,{side_margin},{side_margin},{margin_v},1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text
"""

    def render(word_text: str) -> str:
        return _escape(word_text.upper() if uppercase else word_text)

    events: List[str] = []
    lines = group_lines(words, max_chars, line_pause)
    for line in lines:
        line_start = line[0].start
        line_end = line[-1].end + 0.12
        for i, w in enumerate(line):
            seg_start = w.start
            seg_end = line[i + 1].start if i + 1 < len(line) else line_end
            if seg_end <= seg_start:
                seg_end = seg_start + 0.08
            # build the line text with word i highlighted
            parts: List[str] = []
            for j, ww in enumerate(line):
                if j == i:
                    parts.append(f"{{\\c{highlight}\\fscx{hi_scale}\\fscy{hi_scale}}}{render(ww.text)}{{\\r}}")
                else:
                    parts.append(render(ww.text))
            text = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Caption,,0,0,0,,{text}"
            )

    return header + "\n".join(events) + "\n"
