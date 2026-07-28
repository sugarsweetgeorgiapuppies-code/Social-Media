"""The render pipeline: raw clip -> finished vertical Reel.

Stages (each reports progress):
  1. probe             — read source dimensions / duration / audio
  2. extract audio     — 16 kHz mono wav for whisper + silencedetect
  3. transcribe        — faster-whisper word timestamps  (captions)
  4. plan cuts         — silencedetect -> keep segments  (auto cuts)
  5. cut pass          — trim + concat to the tight timeline
  6. build captions    — animated word-by-word .ass
  7. video pass        — reframe 9:16 + Ken Burns/punch + captions + watermark
  8. audio pass        — music bed ducked under the voice
  9. mux / CTA         — combine, optional end card, finalise H.264 +faststart

Everything is driven by the merged config dict; nothing is hard-coded.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from . import captions as captions_mod
from . import music as music_mod
from . import silence as silence_mod
from .config import resolve_path
from .ffmpeg_utils import (
    ProbeInfo,
    ensure_ffmpeg,
    hex_to_ffmpeg,
    probe,
    run,
)
from .transcribe import Word, transcribe_words

Segment = Tuple[float, float]
ProgressCb = Callable[[int, str], None]


def _noop(pct: int, stage: str) -> None:  # default progress sink
    pass


# fonts bundled with the project, keyed by weight
_WEIGHT_FILE = {
    800: "Montserrat-ExtraBold.ttf",
    700: "Montserrat-Bold.ttf",
}


def _font_file(fonts_dir: Path, weight: int) -> str:
    fname = _WEIGHT_FILE.get(int(weight))
    if fname and (fonts_dir / fname).exists():
        return str(fonts_dir / fname)
    # fall back to whichever bundled font exists
    for fname in ("Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf"):
        if (fonts_dir / fname).exists():
            return str(fonts_dir / fname)
    return "Montserrat"  # let fontconfig resolve by name


def _ff_escape_path(p: str) -> str:
    """Escape a path for use inside an ffmpeg filter option value."""
    return p.replace("\\", "/").replace(":", "\\:")


# ---------------------------------------------------------------------------


def render_video(
    source_path: str,
    out_path: str,
    cfg: dict,
    work_dir: str,
    progress: Optional[ProgressCb] = None,
    log_path: Optional[str] = None,
    job_id: str = "job",
) -> dict:
    """Render ``source_path`` into a finished vertical MP4 at ``out_path``.

    Returns a small dict of what was applied (useful for the UI / debugging).
    """
    progress = progress or _noop
    ensure_ffmpeg()

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    fonts_dir = resolve_path(cfg, "fonts_dir")

    out = cfg["output"]
    W, H, FPS = int(out["width"]), int(out["height"]), int(out["fps"])

    progress(2, "probe")
    info: ProbeInfo = probe(source_path)
    src_duration = info.duration or 0.0

    applied = {"width": W, "height": H, "fps": FPS, "source_duration": round(src_duration, 2)}

    # ---- 2/3) audio extraction + transcription -----------------------------
    words: List[Word] = []
    want_captions = bool(cfg["captions"].get("enabled")) and info.has_audio
    want_cuts = bool(cfg["cuts"].get("enabled")) and info.has_audio

    audio_wav = str(work / "audio.wav")
    if info.has_audio and (want_captions or want_cuts):
        progress(5, "extract-audio")
        run([
            "ffmpeg", "-y", "-i", source_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", audio_wav,
        ], log_path)

    if want_captions:
        progress(10, "transcribe")
        cap = cfg["captions"]
        # "bring your own transcript": if caption words are supplied in options
        # (list of {text,start,end} on the ORIGINAL timeline) skip Whisper.
        provided = cap.get("words")
        if provided:
            words = [
                Word(text=str(w["text"]), start=float(w["start"]), end=float(w["end"]))
                for w in provided if w.get("text")
            ]
            applied["words"] = len(words)
            applied["transcript_source"] = "provided"
        else:
            try:
                words = transcribe_words(
                    audio_wav,
                    model=cap.get("model", "base"),
                    language=cap.get("language"),
                    compute_type=cap.get("compute_type", "int8"),
                    device=cap.get("device", "auto"),
                    beam_size=int(cap.get("beam_size", 5)),
                )
                applied["words"] = len(words)
                applied["transcript_source"] = "whisper"
            except Exception as exc:  # transcription failed (e.g. model download blocked)
                applied["captions_error"] = str(exc)
                words = []

    # ---- 4) plan cuts ------------------------------------------------------
    progress(38, "plan-cuts")
    keeps: List[Segment] = [(0.0, src_duration)]
    if want_cuts:
        c = cfg["cuts"]
        silences = silence_mod.detect_silences(
            audio_wav,
            threshold_db=float(c.get("silence_threshold_db", -30)),
            min_gap=float(c.get("min_gap", 0.6)),
        )
        keeps = silence_mod.compute_keep_segments(
            src_duration,
            silences,
            keep_pad=float(c.get("keep_pad", 0.15)),
            min_segment=float(c.get("min_segment", 0.2)),
            max_removed_per_gap=c.get("max_removed_per_gap"),
        )
        # never clip a word: extend any boundary that lands inside speech
        keeps = silence_mod.snap_segments_to_words(keeps, words)
        applied["silences_found"] = len(silences)
        applied["segments_kept"] = len(keeps)

    cut_duration = silence_mod.total_kept_duration(keeps)
    applied["output_duration"] = round(cut_duration, 2)

    # remap caption words onto the cut timeline
    if words:
        words = silence_mod.remap_words(words, keeps)

    single_segment = len(keeps) == 1 and abs(keeps[0][0]) < 1e-3 and abs(keeps[0][1] - src_duration) < 0.05

    # ---- 5) cut pass -------------------------------------------------------
    if single_segment:
        cut_path = source_path
    else:
        progress(46, "cut")
        cut_path = str(work / "cut.mp4")
        _apply_cuts(source_path, cut_path, keeps, info.has_audio, FPS, log_path)

    # ---- 6) captions .ass --------------------------------------------------
    ass_path = None
    if words:
        progress(56, "captions")
        ass_text = captions_mod.build_ass(words, cfg["captions"], W, H)
        ass_path = str(work / "captions.ass")
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(ass_text)

    # ---- 7) video pass (reframe + zoom + captions + watermark) -------------
    progress(60, "video")
    video_only = str(work / "video.mp4")
    _video_pass(cut_path, video_only, cfg, W, H, FPS, cut_duration, keeps, ass_path, fonts_dir, work, log_path)
    applied["zoom"] = bool(cfg["zoom"].get("enabled"))
    applied["watermark"] = bool(cfg["watermark"].get("enabled"))
    applied["captions"] = ass_path is not None

    # ---- 8) audio pass (voice + ducked music) ------------------------------
    progress(86, "audio")
    audio_path = str(work / "audio.m4a")
    music_used = _audio_pass(cut_path, audio_path, cfg, cut_duration, info.has_audio, work, job_id, log_path)
    applied["music"] = music_used

    # ---- 9) mux + optional CTA + finalise ----------------------------------
    progress(94, "mux")
    main_mp4 = str(work / "main.mp4")
    run([
        "ffmpeg", "-y", "-i", video_only, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
        "-shortest", main_mp4,
    ], log_path)

    cta = cfg["cta"]
    if cta.get("enabled") and (cta.get("title") or cta.get("phone")):
        progress(97, "cta")
        card = str(work / "card.mp4")
        _build_cta_card(card, cfg, W, H, FPS, fonts_dir, work, log_path)
        _concat_finalise([main_mp4, card], out_path, cfg, log_path)
        applied["cta"] = True
    else:
        _finalise_copy(main_mp4, out_path, cfg, log_path)
        applied["cta"] = False

    progress(100, "done")
    return applied


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


def _apply_cuts(src: str, dst: str, keeps: Sequence[Segment], has_audio: bool, fps: int, log_path):
    """Trim + concat the kept segments into a single tight clip."""
    v_chains, a_chains = [], []
    v_labels, a_labels = [], []
    for i, (a, b) in enumerate(keeps):
        v_chains.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        v_labels.append(f"[v{i}]")
        if has_audio:
            a_chains.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
            a_labels.append(f"[a{i}]")
    n = len(keeps)
    fc = ";".join(v_chains)
    fc += f";{''.join(v_labels)}concat=n={n}:v=1:a=0[v]"
    maps = ["-map", "[v]"]
    if has_audio:
        fc += ";" + ";".join(a_chains)
        fc += f";{''.join(a_labels)}concat=n={n}:v=0:a=1[a]"
        maps += ["-map", "[a]"]

    cmd = [
        "ffmpeg", "-y", "-i", src, "-filter_complex", fc, *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [dst]
    run(cmd, log_path)


def _zoompan_expr(cfg: dict, duration: float, fps: int, keeps: Sequence[Segment]) -> str:
    """Build the Ken-Burns push-in + per-cut punch zoom expression."""
    z = cfg["zoom"]
    intensity = float(z.get("intensity", 0.06))
    total_frames = max(1.0, duration * fps)
    expr = f"1+{intensity}*min(on/{total_frames:.3f}\\,1)"

    if z.get("punch_on_cuts") and len(keeps) > 1:
        amt = float(z.get("punch_amount", 0.045))
        decay = max(0.05, float(z.get("punch_decay", 0.45)))
        # cut times on the output timeline = cumulative start of each keep>0
        acc = 0.0
        cut_times: List[float] = []
        for i, (a, b) in enumerate(keeps):
            if i > 0:
                cut_times.append(acc)
            acc += (b - a)
        for c in cut_times:
            expr += (
                f"+{amt}*exp(-max(0\\,(on/{fps}-{c:.3f}))/{decay})"
                f"*gt(on/{fps}\\,{c - 0.03:.3f})"
            )
    return expr


def _video_pass(src, dst, cfg, W, H, FPS, duration, keeps, ass_path, fonts_dir, work, log_path):
    """Reframe to vertical, add motion, burn captions, stamp watermark."""
    chain = [
        f"fps={FPS}",
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
    ]

    if cfg["zoom"].get("enabled"):
        expr = _zoompan_expr(cfg, duration, FPS, keeps)
        chain.append(
            f"zoompan=z='{expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={FPS}"
        )

    if ass_path:
        ass_esc = _ff_escape_path(ass_path)
        fonts_esc = _ff_escape_path(str(fonts_dir))
        chain.append(f"ass=filename={ass_esc}:fontsdir={fonts_esc}")

    wm = cfg["watermark"]
    if wm.get("enabled") and wm.get("text"):
        wm_file = work / "watermark.txt"
        wm_file.write_text(str(wm["text"]), encoding="utf-8")
        font = _font_file(fonts_dir, wm.get("font_weight", 700))
        y = f"h*{float(wm.get('position_y_pct', 0.045))}"
        fill = hex_to_ffmpeg(wm.get("fill_color", "#ffffff"))
        stroke = hex_to_ffmpeg(wm.get("stroke_color", "#1a1a1a"))
        chain.append(
            f"drawtext=fontfile={_ff_escape_path(font)}"
            f":textfile={_ff_escape_path(str(wm_file))}"
            f":fontcolor={fill}@{float(wm.get('opacity', 0.88))}"
            f":fontsize={int(wm.get('font_size', 34))}"
            f":borderw={int(wm.get('stroke_width', 2))}:bordercolor={stroke}"
            f":x=(w-text_w)/2:y={y}"
        )

    chain.append("setsar=1")  # square pixels (zoompan can emit odd SAR)
    vf = ",".join(chain)
    o = cfg["output"]
    run([
        "ffmpeg", "-y", "-i", src, "-vf", vf, "-an",
        "-c:v", o.get("video_codec", "libx264"), "-crf", str(o.get("crf", 20)),
        "-preset", o.get("preset", "medium"), "-pix_fmt", o.get("pixel_format", "yuv420p"),
        "-r", str(FPS), dst,
    ], log_path)


def _audio_pass(cut_path, dst, cfg, duration, has_voice, work, job_id, log_path) -> Optional[str]:
    """Produce the final audio: voice + music bed ducked under the voice."""
    m = cfg["music"]
    music_path = None
    if m.get("enabled"):
        from .config import ROOT
        music_folder = ROOT / m.get("folder", "music")
        chosen = music_mod.pick_track(
            music_folder, m.get("track"), m.get("selection", "random"), seed=job_id
        )
        music_path = str(chosen) if chosen else None

    dur = max(0.1, duration)
    fi = float(m.get("fade_in", 0.5))
    fo = float(m.get("fade_out", 0.8))
    vol = float(m.get("volume", 0.18))
    atk = int(m.get("duck_attack", 5))
    rel = int(m.get("duck_release", 300))

    # Case A: voice + music -> duck music under voice, then mix
    if has_voice and music_path:
        fade_out_st = max(0.0, dur - fo)
        fc = (
            f"[1:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={vol},"
            f"afade=t=in:st=0:d={fi},afade=t=out:st={fade_out_st:.3f}:d={fo}[m];"
            f"[m][0:a]sidechaincompress=threshold=0.03:ratio=12:attack={atk}:release={rel}:makeup=1[mc];"
            f"[0:a][mc]amix=inputs=2:duration=first:normalize=0[a]"
        )
        run([
            "ffmpeg", "-y", "-i", cut_path, "-stream_loop", "-1", "-i", music_path,
            "-filter_complex", fc, "-map", "[a]", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-b:a", cfg["output"].get("audio_bitrate", "192k"), dst,
        ], log_path)
        return os.path.basename(music_path)

    # Case B: voice only
    if has_voice:
        run([
            "ffmpeg", "-y", "-i", cut_path, "-vn", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-b:a", cfg["output"].get("audio_bitrate", "192k"), dst,
        ], log_path)
        return None

    # Case C: music only (silent source) -> play the bed at an audible level
    if music_path:
        solo = min(1.0, max(vol * 4, 0.6))
        fade_out_st = max(0.0, dur - fo)
        fc = (
            f"[0:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={solo},"
            f"afade=t=in:st=0:d={fi},afade=t=out:st={fade_out_st:.3f}:d={fo}[a]"
        )
        run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", music_path,
            "-filter_complex", fc, "-map", "[a]", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-b:a", cfg["output"].get("audio_bitrate", "192k"), dst,
        ], log_path)
        return os.path.basename(music_path)

    # Case D: nothing -> silent track (keeps downstream muxing/concat uniform)
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{dur:.3f}", "-c:a", "aac", "-b:a", "128k", dst,
    ], log_path)
    return None


def _build_cta_card(dst, cfg, W, H, FPS, fonts_dir, work, log_path):
    """Render the optional outro card as its own short clip (with silent audio)."""
    cta = cfg["cta"]
    dur = float(cta.get("duration", 1.8))
    bg = hex_to_ffmpeg(cta.get("background", "#1a1a1a"))
    font = _font_file(fonts_dir, cta.get("font_weight", 800))
    fesc = _ff_escape_path(font)

    def fit(text: str, size: int) -> int:
        """Shrink the font so the line fits ~92% of the frame width."""
        if not text:
            return size
        # ExtraBold glyphs average ~0.60em wide; keep some side padding
        max_w = W * 0.92
        est = len(text) * size * 0.60
        if est > max_w:
            size = int(max_w / (len(text) * 0.60))
        return max(28, size)

    def draw(text_key, size, color, y_expr):
        text = str(cta.get(text_key, "") or "")
        if not text:
            return None
        size = fit(text, size)
        fpath = work / f"cta_{text_key}.txt"
        fpath.write_text(text, encoding="utf-8")
        return (
            f"drawtext=fontfile={fesc}:textfile={_ff_escape_path(str(fpath))}"
            f":fontcolor={hex_to_ffmpeg(color)}:fontsize={size}"
            f":x=(w-text_w)/2:y={y_expr}"
        )

    layers = [
        draw("title", int(cta.get("title_size", 76)), cta.get("title_color", "#ffffff"), "h*0.40-text_h/2"),
        draw("subtitle", int(cta.get("subtitle_size", 46)), cta.get("title_color", "#ffffff"), "h*0.52"),
        draw("phone", int(cta.get("phone_size", 64)), cta.get("accent_color", "#ffd24a"), "h*0.62"),
    ]
    vf = ",".join([l for l in layers if l]) or "null"
    o = cfg["output"]
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:r={FPS}:d={dur}",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", vf, "-t", f"{dur}",
        "-c:v", o.get("video_codec", "libx264"), "-crf", str(o.get("crf", 20)),
        "-preset", o.get("preset", "medium"), "-pix_fmt", o.get("pixel_format", "yuv420p"),
        "-c:a", "aac", "-b:a", "128k", "-r", str(FPS), dst,
    ], log_path)


def _concat_finalise(parts: Sequence[str], out_path: str, cfg, log_path):
    """Concatenate clips (re-encoding once) into the final H.264 +faststart."""
    o = cfg["output"]
    inputs = []
    for p in parts:
        inputs += ["-i", p]
    n = len(parts)
    # normalise SAR/format on every input so concat's strict matching passes
    pre = "".join(f"[{i}:v:0]setsar=1,format=yuv420p[v{i}];" for i in range(n))
    streams = "".join(f"[v{i}][{i}:a:0]" for i in range(n))
    fc = f"{pre}{streams}concat=n={n}:v=1:a=1[v][a]"
    movflags = ["-movflags", "+faststart"] if o.get("faststart", True) else []
    run([
        "ffmpeg", "-y", *inputs, "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-c:v", o.get("video_codec", "libx264"), "-crf", str(o.get("crf", 20)),
        "-preset", o.get("preset", "medium"), "-pix_fmt", o.get("pixel_format", "yuv420p"),
        "-c:a", "aac", "-b:a", o.get("audio_bitrate", "192k"), *movflags, out_path,
    ], log_path)


def _finalise_copy(main_mp4: str, out_path: str, cfg, log_path):
    """No CTA: just remux to add +faststart (stream copy, fast)."""
    o = cfg["output"]
    movflags = ["-movflags", "+faststart"] if o.get("faststart", True) else []
    run([
        "ffmpeg", "-y", "-i", main_mp4, "-c", "copy", *movflags, out_path,
    ], log_path)
