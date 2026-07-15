"""Persist and manage researched trends."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Trend


def save_trends(db: Session, payload: dict, source: str) -> tuple[list[Trend], dict[str, int]]:
    """Store kept trends; return the rows and a name->id map for linking ideas."""
    saved: list[Trend] = []
    name_to_id: dict[str, int] = {}
    today = dt.date.today()

    for t in payload.get("trends", []):
        name = (t.get("name") or "").strip()
        if not name:
            continue
        trend = Trend(
            date_discovered=today,
            name=name,
            platform=t.get("platform", ""),
            description=t.get("description", ""),
            why_working=t.get("why_working", ""),
            brand_fit=t.get("brand_fit", ""),
            expected_lifespan=t.get("expected_lifespan", ""),
            adaptation=t.get("adaptation", ""),
            filming_needs=t.get("filming_needs", ""),
            best_platform=t.get("best_platform", t.get("platform", "")),
            reusable_across_platforms=bool(t.get("reusable_across_platforms", True)),
            risks=t.get("risks", ""),
            difficulty=t.get("difficulty", "Medium"),
            est_filming_time=t.get("est_filming_time", ""),
            requirements=t.get("requirements", ""),
            business_objective=t.get("business_objective", ""),
            virality_score=int(t.get("virality_score", 5) or 5),
            conversion_value=int(t.get("conversion_value", 5) or 5),
            source=t.get("source", source),
            status="active",
            raw=t,
        )
        db.add(trend)
        db.flush()
        saved.append(trend)
        name_to_id[name] = trend.id
    return saved, name_to_id


def expire_stale_trends(db: Session, days: int = 21) -> int:
    """Mark old active trends as expired so they aren't treated as current."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    rows = db.scalars(
        select(Trend).where(Trend.status == "active", Trend.date_discovered < cutoff)
    ).all()
    for r in rows:
        r.status = "expired"
    return len(rows)
