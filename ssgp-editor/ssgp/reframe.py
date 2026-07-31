"""Reframe a source video to the output canvas.

The old pipeline always did fill-and-center-crop, which is correct for turning a
horizontal phone clip into a 9:16 Reel but DESTROYS the subject when going the
other way (e.g. a vertical clip into a 16:9 frame crops the person out). This
module produces the right filtergraph for several strategies so short-form and
long-form can each pick what looks good:

- ``cover_center`` : scale to fill, center-crop. Best for short-form 9:16.
- ``cover_at``     : scale to fill, crop toward a focus point (crop_x/crop_y).
- ``fit_pad``      : letterbox — scale to fit, pad the bars (no pixels lost).
- ``blur_fill``    : scale to fit in front of a blurred, zoomed copy of itself
                     (no bars, no lost pixels). Best default for long-form.
- ``subject_track``: like cover_at using a detected subject; falls back to
                     blur_fill when nothing is found (detection wired later).

Every strategy is expressed as a filter_complex fragment from an input label to
an output label, so it drops into both the main video pass and the multi-clip
stitcher unchanged. Works on any FFmpeg (only core filters: scale/crop/pad/
gblur/overlay/split).
"""

from __future__ import annotations

from typing import List

VALID_MODES = {"cover_center", "cover_at", "fit_pad", "blur_fill", "subject_track"}


def normalize_mode(mode: str | None, default: str = "cover_center") -> str:
    m = (mode or "").strip().lower()
    return m if m in VALID_MODES else default


def reframe_fc(in_label: str, out_label: str, mode: str, W: int, H: int,
               crop_x: float = 0.5, crop_y: float = 0.5, blur_sigma: float = 24.0) -> str:
    """Return a filtergraph string mapping ``in_label`` -> ``out_label``, sized
    exactly W x H. Labels include their brackets, e.g. "[pre]" -> "[rf]"."""
    mode = normalize_mode(mode)
    cx = min(max(float(crop_x), 0.0), 1.0)
    cy = min(max(float(crop_y), 0.0), 1.0)

    if mode == "fit_pad":
        return (f"{in_label}scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1{out_label}")

    if mode == "blur_fill":
        # blurred, filled background + the whole frame fit in front of it
        return (
            f"{in_label}split=2[_bg][_fg];"
            f"[_bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma={blur_sigma:.1f}[_bgb];"
            f"[_fg]scale={W}:{H}:force_original_aspect_ratio=decrease[_fgs];"
            f"[_bgb][_fgs]overlay=(W-w)/2:(H-h)/2,setsar=1{out_label}"
        )

    if mode in ("cover_at", "subject_track"):
        # fill then crop toward the focus point. After the increase-scale the
        # scaled frame is >= W x H, so the crop offset is (scaled - target)*focus.
        return (f"{in_label}scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:x='(iw-{W})*{cx:.3f}':y='(ih-{H})*{cy:.3f}',"
                f"setsar=1{out_label}")

    # cover_center (default) — the proven fill + center-crop
    return (f"{in_label}scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1{out_label}")


def reframe_vf(mode: str, W: int, H: int, crop_x: float = 0.5, crop_y: float = 0.5,
               blur_sigma: float = 24.0) -> str:
    """Convenience for call sites that use a single-stream ``-vf`` and never need
    blur_fill (which requires split/overlay). blur_fill degrades to fit_pad here."""
    mode = normalize_mode(mode)
    if mode == "blur_fill":
        mode = "fit_pad"
    if mode == "fit_pad":
        return (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    if mode in ("cover_at", "subject_track"):
        cx = min(max(float(crop_x), 0.0), 1.0)
        cy = min(max(float(crop_y), 0.0), 1.0)
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:x='(iw-{W})*{cx:.3f}':y='(ih-{H})*{cy:.3f}',setsar=1")
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
