"""Store knowledge base: bias transcription toward your breeds and auto-fix
known mishears (dachshund/"docks", maltipoo/"multi poo", ...).

- ``build_prompt`` -> a priming string handed to Whisper so it EXPECTS puppy
  vocabulary (it's a puppy store, so a dachshund is a "dachshund").
- ``correct_words`` -> exact phrase replacements over the transcript word list,
  merging timestamps when a multi-word mishear collapses to one word.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import yaml

from .config import ROOT
from .transcribe import Word


def load_knowledge(path: str | None = None) -> Dict:
    p = Path(path) if path else (ROOT / "knowledge.yaml")
    if not p.exists():
        return {"breeds": [], "terms": [], "corrections": {}}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {
        "breeds": data.get("breeds") or [],
        "terms": data.get("terms") or [],
        "corrections": data.get("corrections") or {},
    }


def build_prompt(k: Dict) -> str | None:
    """A short context string that primes Whisper toward the store vocabulary."""
    parts: List[str] = ["A video from a puppy store."]
    if k.get("terms"):
        parts.append(", ".join(str(t) for t in k["terms"]) + ".")
    if k.get("breeds"):
        parts.append("Breeds: " + ", ".join(str(b) for b in k["breeds"]) + ".")
    prompt = " ".join(parts).strip()
    return prompt or None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def correct_words(words: Sequence[Word], corrections: Dict) -> Tuple[List[Word], List[str]]:
    """Apply phrase replacements to the transcript. Returns (words, applied)."""
    if not corrections or not words:
        return list(words), []

    # normalize rules to (source_token_list, replacement); longest match first
    rules: List[Tuple[List[str], str]] = []
    for src, rep in corrections.items():
        toks = [_norm(t) for t in str(src).split() if _norm(t)]
        if toks:
            rules.append((toks, str(rep)))
    rules.sort(key=lambda r: -len(r[0]))

    wl = list(words)
    out: List[Word] = []
    applied: List[str] = []
    i = 0
    while i < len(wl):
        hit = None
        for toks, rep in rules:
            n = len(toks)
            if i + n <= len(wl) and [_norm(wl[j].text) for j in range(i, i + n)] == toks:
                hit = (n, rep)
                break
        if hit:
            n, rep = hit
            last = wl[i + n - 1]
            tail = re.search(r"[^\w]+$", last.text)  # keep trailing punctuation
            out.append(Word(text=rep + (tail.group(0) if tail else ""),
                            start=wl[i].start, end=last.end))
            applied.append(" ".join(wl[j].text for j in range(i, i + n)) + " -> " + rep)
            i += n
        else:
            out.append(wl[i])
            i += 1
    return out, applied
