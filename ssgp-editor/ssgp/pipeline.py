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

from . import dogcut
from . import knowledge
from . import music as music_mod
from . import silence as silence_mod
from . import smartcut
from . import textrender
from .config import resolve_path
from .ffmpeg_utils import (
    ProbeInfo,
    ensure_ffmpeg,
    probe,
    run,
)
from .transcribe import Word, transcribe_words

Segment = Tuple[float, float]
ProgressCb = Callable[[int, str], None]


def _noop(pct: int, stage: str) -> None:  # default progress sink
    pass


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
                know = knowledge.load_knowledge()
                words = transcribe_words(
                    audio_wav,
                    model=cap.get("model", "base"),
                    language=cap.get("language"),
                    compute_type=cap.get("compute_type", "int8"),
                    device=cap.get("device", "auto"),
                    beam_size=int(cap.get("beam_size", 5)),
                    initial_prompt=knowledge.build_prompt(know),
                )
                applied["words"] = len(words)
                applied["transcript_source"] = "whisper"
                # auto-fix known breed-name mishears (docks -> Dachshund, ...)
                words, fixes = knowledge.correct_words(words, know.get("corrections", {}))
                if fixes:
                    applied["corrections"] = fixes
            except Exception as exc:  # transcription failed (e.g. model download blocked)
                applied["captions_error"] = str(exc)
                words = []

    if words:
        applied["transcript"] = " ".join(w.text for w in words)

    # ---- 4) captions overlay track (ORIGINAL timeline) ---------------------
    # Captions are burned onto the FULL clip BEFORE any cutting, so they become
    # part of the frames and get cut in lockstep with the video — they can
    # never drift out of sync no matter how many cuts happen.
    caption_list = None
    if words:
        progress(30, "captions")
        caption_list = textrender.build_caption_track(words, cfg["captions"], fonts_dir, W, H, work, FPS)

    # ---- 5) style the FULL clip: reframe + zoom + captions + watermark -----
    progress(48, "video")
    styled_full = str(work / "styled_full.mp4")
    _video_pass(source_path, styled_full, cfg, W, H, FPS, src_duration,
                [(0.0, src_duration)], caption_list, fonts_dir, work, log_path)
    applied["zoom"] = bool(cfg["zoom"].get("enabled"))
    applied["watermark"] = bool(cfg["watermark"].get("enabled"))
    applied["captions"] = caption_list is not None

    # ---- 6) plan cuts (silence + optional AI smart-cut + dog-only) --------
    progress(70, "plan-cuts")
    keeps: List[Segment] = [(0.0, src_duration)]
    c = cfg["cuts"]
    if want_cuts:
        silences = silence_mod.detect_silences(
            audio_wav,
            threshold_db=float(c.get("silence_threshold_db", -30)),
            min_gap=float(c.get("min_gap", 0.6)),
        )
        keeps = silence_mod.compute_keep_segments(
            src_duration, silences,
            keep_pad=float(c.get("keep_pad", 0.15)),
            min_segment=float(c.get("min_segment", 0.2)),
            max_removed_per_gap=c.get("max_removed_per_gap"),
        )
        keeps = silence_mod.snap_segments_to_words(keeps, words)
        applied["silences_found"] = len(silences)

        if c.get("smart_cut"):
            progress(74, "smart-cut")
            sc = smartcut.plan_removals(words, c)
            removals = sc.get("removals", [])
            if removals:
                keeps = silence_mod.subtract_ranges(keeps, removals, float(c.get("min_segment", 0.2)))
            applied["smart_cut"] = {
                "status": sc.get("status"),
                "detail": sc.get("detail"),
                "removed": [[round(s, 2), round(e, 2)] for s, e in removals],
                "reasons": sc.get("reasons", []),
            }

    # Dog-only cut is visual — runs independently of silence trimming.
    if c.get("dog_cut"):
        progress(76, "dog-detect")
        dc = dogcut.plan_removals(source_path, src_duration, c, work)
        dremovals = dc.get("removals", [])
        if dremovals:
            keeps = silence_mod.subtract_ranges(keeps, dremovals, float(c.get("min_segment", 0.2)))
        applied["dog_cut"] = {"status": dc.get("status"), "detail": dc.get("detail"),
                              "removed": [[round(s, 2), round(e, 2)] for s, e in dremovals]}

    applied["segments_kept"] = len(keeps)

    cut_duration = silence_mod.total_kept_duration(keeps)
    applied["output_duration"] = round(cut_duration, 2)
    single_segment = len(keeps) == 1 and abs(keeps[0][0]) < 1e-3 and abs(keeps[0][1] - src_duration) < 0.05

    # ---- 7) cut the captioned video + source audio together (lockstep) ----
    cut_path = str(work / "cut.mp4")
    if single_segment:
        if info.has_audio:
            run(["ffmpeg", "-y", "-i", styled_full, "-i", source_path,
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                 "-b:a", cfg["output"].get("audio_bitrate", "192k"), "-shortest", cut_path], log_path)
        else:
            cut_path = styled_full
    else:
        progress(80, "cut")
        _apply_cuts_av(styled_full, source_path, cut_path, keeps, info.has_audio, FPS, cfg, log_path)

    # ---- 8) audio pass (voice + ducked music) ------------------------------
    progress(88, "audio")
    audio_path = str(work / "audio.m4a")
    music_used = _audio_pass(cut_path, audio_path, cfg, cut_duration, info.has_audio, work, job_id, log_path)
    applied["music"] = music_used

    # ---- 9) mux + optional CTA + finalise ----------------------------------
    progress(94, "mux")
    main_mp4 = str(work / "main.mp4")
    run([
        "ffmpeg", "-y", "-i", cut_path, "-i", audio_path,
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


def _apply_cuts_av(video_src: str, audio_src: str, dst: str, keeps: Sequence[Segment],
                   has_audio: bool, fps: int, cfg: dict, log_path):
    """Trim + concat the kept segments, taking VIDEO from ``video_src`` (the
    already-captioned styled clip) and AUDIO from ``audio_src`` (the original),
    using the SAME cut points. Because the captions are already baked into the
    video frames, they are cut in perfect lockstep and cannot drift.
    """
    o = cfg["output"]
    v_chains, v_labels = [], []
    a_chains, a_labels = [], []
    for i, (a, b) in enumerate(keeps):
        v_chains.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        v_labels.append(f"[v{i}]")
        if has_audio:
            a_chains.append(f"[1:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
            a_labels.append(f"[a{i}]")
    n = len(keeps)
    fc = ";".join(v_chains) + f";{''.join(v_labels)}concat=n={n}:v=1:a=0[v]"
    maps = ["-map", "[v]"]
    inputs = ["-i", video_src]
    if has_audio:
        inputs += ["-i", audio_src]
        fc += ";" + ";".join(a_chains) + f";{''.join(a_labels)}concat=n={n}:v=0:a=1[a]"
        maps += ["-map", "[a]"]

    cmd = [
        "ffmpeg", "-y", *inputs, "-filter_complex", fc, *maps,
        "-c:v", o.get("video_codec", "libx264"), "-crf", str(o.get("crf", 20)),
        "-preset", o.get("preset", "medium"), "-pix_fmt", o.get("pixel_format", "yuv420p"),
        "-r", str(fps),
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", o.get("audio_bitrate", "192k")]
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
        min_gap = float(z.get("punch_min_gap", 0.8))
        # cut times on the output timeline = cumulative start of each keep>0,
        # but only where a meaningful chunk was removed (skip tiny pauses so the
        # zoom doesn't jitter on every breath).
        acc = 0.0
        cut_times: List[float] = []
        for i, (a, b) in enumerate(keeps):
            if i > 0:
                removed = a - keeps[i - 1][1]  # seconds removed at this boundary
                if removed >= min_gap:
                    cut_times.append(acc)
            acc += (b - a)
        for c in cut_times:
            expr += (
                f"+{amt}*exp(-max(0\\,(on/{fps}-{c:.3f}))/{decay})"
                f"*gt(on/{fps}\\,{c - 0.03:.3f})"
            )
    return expr


def _video_pass(src, dst, cfg, W, H, FPS, duration, keeps, caption_list, fonts_dir, work, log_path):
    """Reframe to vertical, add motion, then composite caption + watermark PNGs.

    Text is drawn by Pillow into transparent overlays (see textrender), so this
    works on FFmpeg builds without libass/freetype.
    """
    # base video chain (no text): reframe + optional zoom
    base = [
        f"fps={FPS}",
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
    ]
    if cfg["zoom"].get("enabled"):
        expr = _zoompan_expr(cfg, duration, FPS, keeps)
        base.append(
            f"zoompan=z='{expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={FPS}"
        )
    base.append("setsar=1")  # square pixels (zoompan can emit odd SAR)

    inputs = ["-i", src]
    fc = f"[0:v]{','.join(base)}[base]"
    last = "base"
    idx = 1

    # caption overlay track (a concat of transparent PNGs)
    if caption_list:
        inputs += ["-f", "concat", "-safe", "0", "-i", caption_list]
        fc += f";[{idx}:v]fps={FPS},format=rgba[cap];[{last}][cap]overlay=0:0:eof_action=pass:shortest=0[vc]"
        last = "vc"
        idx += 1

    # watermark overlay (single static PNG)
    wm = cfg["watermark"]
    if wm.get("enabled") and wm.get("text"):
        wm_png = work / "watermark.png"
        textrender.render_watermark(wm, fonts_dir, W, H, wm_png)
        inputs += ["-loop", "1", "-i", str(wm_png)]
        fc += f";[{last}][{idx}:v]overlay=0:0:eof_action=pass[vw]"
        last = "vw"
        idx += 1

    o = cfg["output"]
    run([
        "ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", f"[{last}]", "-an",
        "-c:v", o.get("video_codec", "libx264"), "-crf", str(o.get("crf", 20)),
        "-preset", o.get("preset", "medium"), "-pix_fmt", o.get("pixel_format", "yuv420p"),
        "-r", str(FPS), "-t", f"{duration:.3f}", dst,
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
    replace_voice = bool(m.get("replace_voice", False))

    # Music-only: drop the voice entirely and play the bed over the video.
    # (Captions were already transcribed from the original voice earlier.)
    if music_path and (replace_voice or not has_voice):
        solo = float(m.get("solo_volume", 0.85)) if replace_voice else min(1.0, max(vol * 4, 0.6))
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
        return os.path.basename(music_path) + " (voice removed)" if replace_voice else os.path.basename(music_path)

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
    """Render the optional outro card (Pillow PNG) as its own short clip."""
    cta = cfg["cta"]
    dur = float(cta.get("duration", 1.8))
    card_png = work / "cta.png"
    textrender.render_cta_card(cta, fonts_dir, W, H, card_png)

    o = cfg["output"]
    run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{dur}", "-i", str(card_png),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{dur}",
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
