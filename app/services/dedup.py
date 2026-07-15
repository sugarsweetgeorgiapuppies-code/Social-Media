"""Duplicate detection for the content idea database.

The agent keeps a memory of what it has already suggested so it does not
recommend the same concept over and over. A fingerprint is a hash of the
normalised concept signals (title + hook + category + breed). We only block a
new idea when a near-identical one already exists AND the new one is not an
intentional retest.
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Idea

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "with", "this", "that",
    "puppy", "puppies", "dog", "dogs", "video", "our", "your", "in", "on", "at",
}


def _norm(text: str) -> str:
    words = [w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP]
    return " ".join(sorted(set(words)))


def fingerprint(title: str, hook: str, category: str, breed: str) -> str:
    basis = "|".join(
        [_norm(title), _norm(hook), (category or "").lower(), (breed or "").lower()]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def recent_idea_labels(db: Session, limit: int = 60) -> list[str]:
    """Titles + hooks of recent, non-archived ideas (fed to the strategist)."""
    rows = db.scalars(
        select(Idea)
        .where(Idea.status != "Archived")
        .order_by(Idea.created_at.desc())
        .limit(limit)
    ).all()
    labels = []
    for r in rows:
        label = r.title
        if r.hook:
            label = f"{r.title} — {r.hook[:80]}"
        labels.append(label)
    return labels


def is_duplicate(db: Session, fp: str, *, allow_retest: bool) -> bool:
    if allow_retest:
        return False
    existing = db.scalar(
        select(Idea).where(Idea.fingerprint == fp, Idea.status != "Archived").limit(1)
    )
    return existing is not None
