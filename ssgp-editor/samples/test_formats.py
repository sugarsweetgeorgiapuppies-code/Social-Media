#!/usr/bin/env python3
"""No-network tests for the Short/Long format + reframe engine.

Uses ffmpeg lavfi sources and a provided transcript (captions.words) so nothing
downloads (Whisper is bypassed). Run:  python3 samples/test_formats.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from ssgp.config import load_config, merge_options  # noqa: E402
from ssgp import formats  # noqa: E402
from ssgp.reframe import reframe_fc, VALID_MODES  # noqa: E402
from ssgp.pipeline import render_video  # noqa: E402


def _dims(path: str):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    w, h = out.split(",")
    return int(w), int(h)


def _make_vertical(path: str, dur: int = 5):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=teal:s=608x1080:d={dur},drawbox=x=154:y=340:w=300:h=300:color=yellow:t=fill,format=yuv420p",
        "-f", "lavfi", "-i", f"sine=frequency=200:duration={dur}",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", path, "-y",
    ], check=True)


WORDS = [{"text": "Welcome", "start": 0.3, "end": 0.8}, {"text": "to", "start": 0.8, "end": 1.0},
         {"text": "our", "start": 1.0, "end": 1.2}, {"text": "kennel", "start": 1.2, "end": 1.8},
         {"text": "tour", "start": 1.8, "end": 2.3}, {"text": "today", "start": 2.5, "end": 3.0}]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ssgp_fmt_"))
    src = str(tmp / "vsrc.mp4")
    _make_vertical(src)

    # 1) every reframe mode yields the exact target canvas
    for mode in sorted(VALID_MODES):
        out = str(tmp / f"rf_{mode}.mp4")
        fc = reframe_fc("[0:v]", "[rf]", mode, 1920, 1080) + ";[rf]format=yuv420p[v]"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
                        "-filter_complex", fc, "-map", "[v]", "-frames:v", "1", out, "-y"], check=True)
        assert _dims(out) == (1920, 1080), f"{mode} wrong dims {_dims(out)}"
    print("PASS  reframe modes ->", ", ".join(sorted(VALID_MODES)))

    # 2) format bundles drive geometry + reframe end-to-end through render_video
    cases = {"short": (1080, 1920, "cover_center"), "long": (1920, 1080, "blur_fill")}
    for fmt, (ew, eh, erf) in cases.items():
        cfg = load_config()
        cfg = merge_options(cfg, formats.bundle(fmt))
        cfg["format"] = fmt
        cfg["captions"]["enabled"] = True
        cfg["captions"]["words"] = WORDS
        cfg["music"]["enabled"] = False
        out = str(tmp / f"pipe_{fmt}.mp4")
        applied = render_video(src, out, cfg, str(tmp / f"work_{fmt}"), job_id=fmt)
        assert _dims(out) == (ew, eh), f"{fmt} dims {_dims(out)} != {(ew, eh)}"
        assert applied["format"] == fmt and applied["reframe"] == erf, f"{fmt} applied wrong: {applied.get('format')}/{applied.get('reframe')}"
        print(f"PASS  {fmt:5s} -> {ew}x{eh} {erf}  (caps={applied.get('captions')}, gfx={'on' if applied.get('graphics') else 'off'})")

    # 3) instruction + aspect override reaches the config
    from ssgp.instructions import interpret
    o, notes = interpret("make it 16:9 for youtube")
    assert o.get("output", {}).get("width") == 1920, f"aspect override missing: {o}"
    print("PASS  instruction '16:9 for youtube' ->", o["output"])

    # 4) edit plan: short trims a weak intro; long stays chronological
    from ssgp import plan as P
    from ssgp.transcribe import Word
    intro_words = [Word("Hey", 0.0, 0.3), Word("guys", 0.3, 0.6), Word("so", 0.6, 0.8),
                   Word("today", 0.8, 1.2), Word("our", 1.4, 1.6), Word("Maltipoos", 1.6, 2.3),
                   Word("are", 2.3, 2.5), Word("hypoallergenic", 2.5, 3.4)]
    sp = P.build_edit_plan("short", intro_words, {"cuts": {"enabled": True}})
    assert sp["opening_strategy"] == "strongest_hook", sp
    assert any(k == "weak_intro" for (_a, _b, k, *_r) in sp["removals"]), sp["removals"]
    lp = P.build_edit_plan("long", intro_words, {"cuts": {"enabled": True}})
    assert lp["opening_strategy"] == "chronological" and not lp["removals"], lp
    dec = P.summarize({"format": "long", "width": 1920, "height": 1080, "reframe": "blur_fill",
                       "captions": True, "source_duration": 60.0, "output_duration": 48.0}, {})
    assert any("16:9" in d for d in dec) and dec, dec
    print("PASS  edit plan: short trims intro, long chronological, summary built")

    print("\nALL FORMAT TESTS PASSED")


if __name__ == "__main__":
    main()
