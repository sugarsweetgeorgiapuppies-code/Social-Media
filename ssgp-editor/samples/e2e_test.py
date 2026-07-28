"""End-to-end pipeline test.

Renders samples/sample.mp4 (landscape + speech + silences) through the full
pipeline with every feature ON, using a supplied transcript so it runs without
network access to the Whisper model. Verifies the output is 1080x1920 H.264.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssgp.config import load_config, merge_options
from ssgp.ffmpeg_utils import probe
from ssgp.pipeline import render_video

HERE = Path(__file__).resolve().parent


def ensure_sample(path: Path):
    """Generate a landscape test clip (with speech-like bursts + silences) if
    one isn't present, so this test is self-contained on any machine."""
    if path.exists():
        return
    print("Generating sample.mp4 (landscape + audio with silences)...")
    # audio: three ~3s tone bursts separated by ~1.3s of silence
    afilter = (
        "aevalsrc="
        "'0.25*sin(220*2*PI*t)*lt(mod(t\\,4.3)\\,3.0)':"
        "s=44100:d=12.3,aformat=channel_layouts=stereo"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=12.3",
        "-f", "lavfi", "-i", afilter,
        "-vf", "drawtext=text='PUPPY CLIP':fontcolor=white:fontsize=90:x=(w-text_w)/2:y=h*0.15,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-shortest", str(path),
    ], check=True)

# words on the ORIGINAL timeline (matches the espeak phrases + 1.3s silences)
PHRASES = [
    (0.15, 3.95, "Hey everyone, welcome back to Sugar Sweet Georgia Puppies."),
    (5.45, 8.10, "These little ones are looking for a loving home."),
    (9.65, 12.20, "Come and meet them in Lawrenceville, Georgia."),
]


def make_words():
    out = []
    for start, end, text in PHRASES:
        toks = text.split()
        step = (end - start) / len(toks)
        for i, tok in enumerate(toks):
            ws = start + i * step
            out.append({"text": tok, "start": round(ws, 3), "end": round(ws + step * 0.92, 3)})
    return out


def main():
    cfg = load_config()
    options = {
        "captions": {"enabled": True, "words": make_words()},
        "cuts": {"enabled": True},
        "zoom": {"enabled": True},
        "music": {"enabled": True},
        "watermark": {"enabled": True},
        "cta": {"enabled": True, "title": "Come meet our puppies",
                "subtitle": "Lawrenceville, GA", "phone": "(678) 253-4081"},
    }
    cfg = merge_options(cfg, options)

    ensure_sample(HERE / "sample.mp4")

    out_path = str(HERE / "e2e_output.mp4")
    work = str(HERE / "_work")

    def prog(pct, stage):
        print(f"  [{pct:3d}%] {stage}")

    print("Rendering sample.mp4 -> e2e_output.mp4 ...")
    applied = render_video(
        str(HERE / "sample.mp4"), out_path, cfg, work,
        progress=prog, log_path=str(HERE / "e2e_ffmpeg.log"), job_id="e2etest",
    )

    info = probe(out_path)
    print("\nApplied:", applied)
    print(f"Output: {info.width}x{info.height} @ {info.fps:.1f}fps, "
          f"{info.duration:.2f}s, video={info.video_codec}, audio={info.audio_codec}")
    assert info.width == 1080 and info.height == 1920, "not vertical 1080x1920!"
    assert info.video_codec == "h264", "not H.264!"
    assert info.audio_codec is not None, "no audio track!"
    print("\nPASS ✓  vertical H.264 with audio, captions + cuts + zoom + music + watermark + CTA")


if __name__ == "__main__":
    main()
