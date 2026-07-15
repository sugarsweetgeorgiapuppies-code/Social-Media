"""Performance analytics: build rows for the analyst and run analysis."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import agents
from ..models import Idea, Performance
from ..seed import brand_rules_dict


def performance_rows(db: Session, limit: int = 100) -> list[dict]:
    """Flatten performance + idea context into rows for the analyst."""
    rows = db.scalars(
        select(Performance).order_by(Performance.date.desc()).limit(limit)
    ).all()
    out: list[dict] = []
    for p in rows:
        idea = p.idea
        out.append(
            {
                "date": p.date.isoformat() if p.date else None,
                "platform": p.platform or (idea.platform if idea else ""),
                "category": p.category or (idea.category if idea else ""),
                "video_format": p.video_format or (idea.content_type if idea else ""),
                "hook": p.hook or (idea.hook if idea else ""),
                "breed": idea.breed if idea else "",
                "series": idea.series.name if idea and idea.series else "",
                "video_length_seconds": p.video_length_seconds,
                "views": p.views,
                "reach": p.reach,
                "likes": p.likes,
                "comments": p.comments,
                "shares": p.shares,
                "saves": p.saves,
                "avg_watch_time_seconds": p.avg_watch_time_seconds,
                "completion_rate": p.completion_rate,
                "follower_growth": p.follower_growth,
                "profile_visits": p.profile_visits,
                "website_clicks": p.website_clicks,
                "calls": p.calls,
                "messages": p.messages,
                "appointments": p.appointments,
                "notes": p.notes,
            }
        )
    return out


def summarise_for_strategist(db: Session) -> str:
    """A short natural-language performance summary the strategist can use."""
    rows = performance_rows(db, limit=40)
    if not rows:
        return "No performance data yet."
    total = len(rows)
    top = sorted(
        rows,
        key=lambda r: (r.get("shares", 0) * 3 + r.get("saves", 0) * 3
                       + r.get("comments", 0) * 2 + (r.get("completion_rate") or 0)),
        reverse=True,
    )[:3]
    bits = [f"{total} posts logged."]
    for r in top:
        bits.append(
            f"Strong: '{(r.get('hook') or '')[:60]}' ({r.get('category')}, "
            f"{r.get('platform')}) — {r.get('shares',0)} shares, {r.get('saves',0)} saves."
        )
    return " ".join(bits)


def run_analysis(db: Session) -> tuple[dict, str]:
    brand = brand_rules_dict(db)
    rows = performance_rows(db)
    return agents.analyse_performance(brand, rows)
