"""Silence detection and cut planning.

We ask ffmpeg's ``silencedetect`` where the quiet stretches are, then collapse
any gap longer than ``min_gap`` down to a short natural pause — leaving
``keep_pad`` seconds on each side so a word is never clipped. The resulting
"keep segments" drive both the ffmpeg trim/concat and the remapping of caption
word timestamps onto the shortened timeline.
"""

from __future__ import annotations

import re
import subprocess
from typing import List, Optional, Sequence, Tuple

from .transcribe import Word

Segment = Tuple[float, float]

_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silences(audio_path: str, threshold_db: float, min_gap: float) -> List[Segment]:
    """Return [(start, end), ...] of silences at least ``min_gap`` seconds long."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", audio_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_gap}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stderr

    silences: List[Segment] = []
    start: Optional[float] = None
    for line in text.splitlines():
        m = _SIL_START.search(line)
        if m:
            start = float(m.group(1))
            continue
        m = _SIL_END.search(line)
        if m and start is not None:
            end = float(m.group(1))
            if end > start:
                silences.append((max(0.0, start), end))
            start = None
    return silences


def compute_keep_segments(
    duration: float,
    silences: Sequence[Segment],
    keep_pad: float,
    min_segment: float,
    max_removed_per_gap: Optional[float] = None,
) -> List[Segment]:
    """Turn silence intervals into the list of segments we KEEP.

    Each long silence is collapsed to ``2 * keep_pad`` seconds (pad on each
    side); everything else is kept verbatim.
    """
    keeps: List[Segment] = []
    pointer = 0.0
    for s, e in sorted(silences):
        gap_start = s + keep_pad
        gap_end = e - keep_pad
        if gap_end <= gap_start:
            continue  # silence shorter than the padding — leave it alone
        if max_removed_per_gap:
            removable = gap_end - gap_start
            if removable > max_removed_per_gap:
                gap_end = gap_start + max_removed_per_gap
        if gap_start > pointer:
            keeps.append((pointer, gap_start))
        pointer = max(pointer, gap_end)
    if pointer < duration:
        keeps.append((pointer, duration))

    # drop tiny slivers and clamp
    cleaned = [(max(0.0, a), min(duration, b)) for a, b in keeps if (b - a) >= min_segment]
    return cleaned or [(0.0, duration)]


def snap_segments_to_words(keeps: Sequence[Segment], words: Sequence[Word], guard: float = 0.06) -> List[Segment]:
    """Nudge keep-boundaries so a cut never lands in the middle of a word.

    If a segment boundary falls inside a spoken word (± guard), the boundary is
    extended outward to fully include that word.
    """
    if not words:
        return list(keeps)
    snapped: List[Segment] = []
    for a, b in keeps:
        for w in words:
            # boundary 'a' sits inside a word -> pull start back to word start
            if w.start - guard < a < w.end + guard and a > w.start:
                a = max(0.0, w.start - guard)
            # boundary 'b' sits inside a word -> push end out to word end
            if w.start - guard < b < w.end + guard and b < w.end:
                b = w.end + guard
        if b > a:
            snapped.append((a, b))
    # merge any overlaps created by snapping
    snapped.sort()
    merged: List[Segment] = []
    for seg in snapped:
        if merged and seg[0] <= merged[-1][1] + 1e-3:
            merged[-1] = (merged[-1][0], max(merged[-1][1], seg[1]))
        else:
            merged.append(seg)
    return merged


def total_kept_duration(keeps: Sequence[Segment]) -> float:
    return sum(b - a for a, b in keeps)


def cap_keeps(keeps: Sequence[Segment], max_total: float) -> List[Segment]:
    """Cap the kept segments so their combined length is at most ``max_total``
    seconds (trims the final segment). Used for a target/max output length."""
    if not max_total or max_total <= 0:
        return list(keeps)
    out: List[Segment] = []
    acc = 0.0
    for a, b in keeps:
        seg = b - a
        if acc + seg <= max_total:
            out.append((a, b))
            acc += seg
        else:
            remain = max_total - acc
            if remain > 0.05:
                out.append((a, a + remain))
            break
    return out or list(keeps)[:1]


def subtract_ranges(keeps: Sequence[Segment], removals: Sequence[Segment], min_segment: float = 0.2) -> List[Segment]:
    """Remove ``removals`` (e.g. AI-flagged flubs) from the kept segments."""
    result = list(keeps)
    for r0, r1 in removals:
        nxt: List[Segment] = []
        for a, b in result:
            if r1 <= a or r0 >= b:      # no overlap
                nxt.append((a, b))
                continue
            if r0 > a:                  # keep the head before the removal
                nxt.append((a, r0))
            if r1 < b:                  # keep the tail after the removal
                nxt.append((r1, b))
        result = nxt
    return [(a, b) for a, b in result if (b - a) >= min_segment]


def remap_words(words: Sequence[Word], keeps: Sequence[Segment]) -> List[Word]:
    """Map word timestamps from the original timeline onto the cut timeline."""
    # prefix offset for each keep segment
    prefix: List[float] = []
    acc = 0.0
    for a, b in keeps:
        prefix.append(acc)
        acc += (b - a)

    def map_time(t: float) -> Optional[float]:
        for (a, b), off in zip(keeps, prefix):
            if a <= t <= b:
                return off + (t - a)
        # falls in a removed gap: snap to nearest keep boundary
        for (a, b), off in zip(keeps, prefix):
            if t < a:
                return off  # start of this keep
        return None

    out: List[Word] = []
    for w in words:
        ns = map_time(w.start)
        ne = map_time(w.end)
        if ns is None:
            continue
        if ne is None or ne <= ns:
            ne = ns + max(0.08, w.end - w.start)
        out.append(Word(text=w.text, start=ns, end=ne))
    return out
