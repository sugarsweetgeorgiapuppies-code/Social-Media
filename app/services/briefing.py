"""The daily workflow orchestrator — the AI employee's full morning routine.

run_daily_workflow performs the real end-to-end pipeline:
  1. research (or receive) current trends            -> save
  2. generate brand-specific ideas from trends       -> save (dedup-checked)
  3. select the strongest recommendation
  4. produce a complete filming package for it       -> save + compliance gate
  5. assemble a human daily briefing                 -> save
  6. log the run (source, counts, errors)

The owner then approves/rejects/edits from the dashboard; publishing and
performance feed back into future recommendations via the analyst.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import agents
from ..logging_config import get_logger
from ..models import Briefing, Idea, ResearchLog, Series
from ..seed import brand_rules_dict
from . import analytics, dedup, ideas as ideas_svc, trends as trends_svc

log = get_logger(__name__)


def _series_dicts(db: Session) -> list[dict]:
    rows = db.scalars(select(Series).where(Series.active.is_(True))).all()
    return [
        {
            "name": s.name,
            "repeatable_format": s.repeatable_format,
            "opening_hook": s.opening_hook,
        }
        for s in rows
    ]


def run_daily_workflow(db: Session, run_type: str = "daily") -> Briefing:
    brand = brand_rules_dict(db)
    log_row = ResearchLog(run_type=run_type)
    overall_source = "live_research"

    try:
        # --- 1. Research trends --------------------------------------------
        trends_svc.expire_stale_trends(db)
        trend_payload, tsource = agents.research_trends(brand)
        saved_trends, name_to_id = trends_svc.save_trends(db, trend_payload, tsource)
        if tsource == "inferred":
            overall_source = "inferred"

        # --- 2. Generate ideas ---------------------------------------------
        series = _series_dicts(db)
        perf_summary = analytics.summarise_for_strategist(db)
        avoid = dedup.recent_idea_labels(db)
        trend_dicts = [t.raw | {"name": t.name} for t in saved_trends]
        strategy, ssource = agents.strategise_ideas(
            brand, trend_dicts, series, perf_summary, avoid
        )
        if ssource == "inferred":
            overall_source = "inferred"
        created = ideas_svc.create_ideas_from_strategy(
            db, strategy, name_to_id, source=ssource
        )

        # --- 3. Select the strongest recommendation ------------------------
        primary = max(created, key=lambda i: i.priority_score, default=None)

        # --- 4. Full filming package for the pick --------------------------
        if primary is not None:
            ideas_svc.build_filming_package(db, primary)

        # --- 5. Assemble the briefing --------------------------------------
        engagement_ctx = {
            "trends": [
                {"name": t.name, "adaptation": t.adaptation, "platform": t.best_platform}
                for t in saved_trends
            ],
            "ideas": [
                {
                    "title": i.title,
                    "platform": i.platform,
                    "category": i.category,
                    "content_type": i.content_type,
                    "priority_score": i.priority_score,
                    "is_primary": (primary is not None and i.id == primary.id),
                }
                for i in sorted(created, key=lambda x: x.priority_score, reverse=True)
            ],
            "latest_analysis": _latest_analysis_snapshot(db),
        }
        brief_payload, bsource = agents.generate_briefing(brand, engagement_ctx)
        if bsource == "inferred":
            overall_source = "inferred"

        # --- 6. Persist the briefing ---------------------------------------
        brief = _upsert_briefing(
            db,
            primary_id=primary.id if primary else None,
            source=overall_source,
            payload={
                "headline": brief_payload.get("headline", ""),
                "summary": brief_payload.get("summary", ""),
                "why_film_this_today": brief_payload.get("why_film_this_today", ""),
                "community_engagement": brief_payload.get("community_engagement", []),
                "repurpose_ideas": brief_payload.get("repurpose_ideas", []),
                "trends_worth_using": [_trend_brief(t) for t in saved_trends],
                "idea_ids": [i.id for i in created],
            },
        )

        log_row.status = "ok"
        log_row.source = overall_source
        log_row.trends_found = len(saved_trends)
        log_row.ideas_created = len(created)
        log_row.message = (
            f"Researched {len(saved_trends)} trends, created {len(created)} ideas."
        )
        db.add(log_row)
        db.flush()
        return brief

    except Exception as exc:  # keep scheduled runs resilient
        log.exception("Daily workflow failed")
        log_row.status = "error"
        log_row.message = str(exc)[:500]
        db.add(log_row)
        raise


def _trend_brief(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "platform": t.platform,
        "description": t.description,
        "why_working": t.why_working,
        "expected_lifespan": t.expected_lifespan,
        "adaptation": t.adaptation,
        "difficulty": t.difficulty,
        "est_filming_time": t.est_filming_time,
        "requirements": t.requirements,
        "business_objective": t.business_objective,
        "virality_score": t.virality_score,
        "conversion_value": t.conversion_value,
        "source": t.source,
    }


def _latest_analysis_snapshot(db: Session) -> dict:
    """Cheap snapshot for the briefing (avoids a second analyst call)."""
    return {"note": analytics.summarise_for_strategist(db)}


def _upsert_briefing(db: Session, primary_id, source: str, payload: dict) -> Briefing:
    today = dt.date.today()
    existing = db.scalar(select(Briefing).where(Briefing.date == today))
    if existing:
        existing.headline = payload.get("headline", "")
        existing.summary = payload.get("summary", "")
        existing.primary_idea_id = primary_id
        existing.source = source
        existing.data = payload
        db.flush()
        return existing
    brief = Briefing(
        date=today,
        headline=payload.get("headline", ""),
        summary=payload.get("summary", ""),
        primary_idea_id=primary_id,
        source=source,
        data=payload,
    )
    db.add(brief)
    db.flush()
    return brief
