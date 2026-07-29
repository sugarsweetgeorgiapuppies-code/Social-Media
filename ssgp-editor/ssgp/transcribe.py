"""Local speech-to-text using faster-whisper, returning word-level timestamps.

The model is downloaded once (to the HuggingFace cache) on first use and then
reused. Models are cached in-process per (size, device, compute_type) so a
batch of jobs doesn't reload weights every time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_MODEL_CACHE: Dict[Tuple[str, str, str], object] = {}


@dataclass
class Word:
    text: str
    start: float
    end: float


def _pick_device(device: str) -> Tuple[str, str]:
    """Resolve 'auto' device into (device, compute_type-compatible fallback)."""
    if device and device != "auto":
        return device, device
    try:
        import ctranslate2  # noqa: F401  (faster-whisper dependency)
        # ctranslate2 exposes CUDA device count when built with CUDA
        import ctranslate2 as ct

        if ct.get_cuda_device_count() > 0:
            return "cuda", "cuda"
    except Exception:
        pass
    return "cpu", "cpu"


def _get_model(model: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    resolved_device, _ = _pick_device(device)
    # int8 compute types are for CPU; on GPU prefer float16 unless caller insists
    if resolved_device == "cuda" and compute_type.startswith("int8") and compute_type == "int8":
        compute_type = "float16"
    key = (model, resolved_device, compute_type)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(model, device=resolved_device, compute_type=compute_type)
    return _MODEL_CACHE[key]


def transcribe_words(
    audio_path: str,
    model: str = "base",
    language: Optional[str] = None,
    compute_type: str = "int8",
    device: str = "auto",
    beam_size: int = 5,
    initial_prompt: Optional[str] = None,
) -> List[Word]:
    """Transcribe ``audio_path`` and return a flat list of timed words.

    ``initial_prompt`` primes the model with expected vocabulary (breed names,
    store terms) so it stops mishearing them.
    """
    whisper = _get_model(model, device, compute_type)
    segments, _info = whisper.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        word_timestamps=True,
        vad_filter=False,  # we do our own silence handling in silence.py
        initial_prompt=initial_prompt,
    )

    words: List[Word] = []
    for seg in segments:
        for w in (seg.words or []):
            text = (w.word or "").strip()
            if not text:
                continue
            start = float(w.start if w.start is not None else seg.start)
            end = float(w.end if w.end is not None else seg.end)
            if end <= start:
                end = start + 0.08
            words.append(Word(text=text, start=start, end=end))
    return words
