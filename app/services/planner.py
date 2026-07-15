"""Weekly content planner — the employee lays out a real posting schedule.

Picks the best unscheduled ideas (generating more if needed), spreads them
across the coming days with recording dates, and puts them on the calendar.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import agents
from ..logging_config import get_logger
from ..models import Idea, Series, Trend
from ..seed import brand_rules_dict
from . import analytics, dedup, ideas as ideas_svc

log = get_logger(__name__)

# A sensible default posting rhythm across a week (platform rotation).
_ROTATION = ["Instagram", "TikTok", "YouTube Shorts", "Facebook", "Instagram", "TikTok", "Instagram"]


def _active_trend_dicts(db: Session) -> list[dict]:
    rows = db.scalars(select(Trend).where(Trend.status == "active").order_by(Trend.date_discovered.desc()).limit(8)).all()
    return [t.raw | {"name": t.name} for t in rows]


def _series_dicts(db: Session) -> list[dict]:
    rows = db.scalars(select(Series).where(Series.active.is_(True))).all()
    return [{"name": s.name, "repeatable_format": s.repeatable_format} for s in rows]


def _candidate_ideas(db: Session) -> list[Idea]:
    """Unscheduled, un-published ideas ranked by priority."""
    rows = db.scalars(
        select(Idea)
        .where(
            Idea.status.notin_(["Published", "Scheduled", "Archived", "Repurpose"]),
            Idea.publishing_date.is_(None),
        )
        .order_by(Idea.priority_score.desc())
    ).all()
    return list(rows)


def plan_week(db: Session, start_date: dt.date | None = None, posts: int = 5) -> dict:
    """Create/refresh a weekly posting plan. Returns a summary dict."""
    posts = max(1, min(int(posts or 5), 7))
    start = start_date or dt.date.today()
    brand = brand_rules_dict(db)

    candidates = _candidate_ideas(db)

    # Not enough ideas on hand? Generate a fresh slate from current trends.
    if len(candidates) < posts:
        trends = _active_trend_dicts(db)
        series = _series_dicts(db)
        perf = analytics.summarise_for_strategist(db)
        avoid = dedup.recent_idea_labels(db)
        strategy, source = agents.strategise_ideas(brand, trends, series, perf, avoid)
        # trend name->id map for linking (best effort)
        tmap = {t.name: t.id for t in db.scalars(select(Trend)).all()}
        ideas_svc.create_ideas_from_strategy(db, strategy, tmap, source=source)
        candidates = _candidate_ideas(db)

    chosen = candidates[:posts]

    scheduled = []
    # Spread posts across the window (evenly if fewer than 7).
    step = max(1, 7 // posts)
    for idx, idea in enumerate(chosen):
        pub = start + dt.timedelta(days=min(idx * step, 6))
        rec = pub - dt.timedelta(days=1)
        if rec < dt.date.today():
            rec = dt.date.today()
        idea.publishing_date = pub
        idea.recording_date = rec
        if not idea.platform:
            idea.platform = _ROTATION[idx % len(_ROTATION)]
        if idea.status in ("New", "Needs Revision"):
            idea.status = "Scheduled"
        elif idea.status == "Approved":
            idea.status = "Scheduled"
        # Make sure a scheduled post has a script ready to film.
        if not idea.script:
            try:
                ideas_svc.build_filming_package(db, idea)
            except Exception:
                log.exception("Could not build package while planning idea %s", idea.id)
        scheduled.append(
            {
                "idea_id": idea.id,
                "title": idea.title,
                "platform": idea.platform,
                "record_on": rec.isoformat(),
                "post_on": pub.isoformat(),
            }
        )

    db.flush()
    return {
        "start_date": start.isoformat(),
        "count": len(scheduled),
        "posts": scheduled,
    }
