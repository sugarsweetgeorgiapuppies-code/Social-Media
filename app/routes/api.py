"""HTTP API for the dashboard.

Every control the owner needs (approve, reject, revise, regenerate, shorten,
make funnier/educational, change breed/platform, mark filmed/published, log
performance, save feedback, edit brand rules) is exposed here.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..ai.client import ai_client
from ..config import settings
from ..database import get_db
from ..models import (
    Briefing,
    Competitor,
    Idea,
    Performance,
    ResearchLog,
    Series,
    Trend,
)
from ..schemas import (
    BrandRuleUpdate,
    ChatSend,
    FeedbackCreate,
    IdeaAction,
    IdeaCreate,
    IdeaUpdate,
    PerformanceCreate,
    PlanWeek,
    SeriesUpsert,
)
from ..seed import brand_rules_dict
from ..ai import employee as employee_ai
from ..services import (
    analytics,
    briefing as briefing_svc,
    dedup,
    ideas as ideas_svc,
    planner as planner_svc,
    tasks as tasks_svc,
)
from ..services.ideas import compute_priority
from . import serializers as ser

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
@router.get("/status")
def status(db: Session = Depends(get_db)):
    counts = {
        "trends": db.scalar(select(func.count()).select_from(Trend)) or 0,
        "ideas": db.scalar(select(func.count()).select_from(Idea)) or 0,
        "published": db.scalar(
            select(func.count()).select_from(Idea).where(Idea.status == "Published")
        )
        or 0,
        "awaiting_approval": db.scalar(
            select(func.count()).select_from(Idea).where(Idea.status.in_(["New", "Needs Revision"]))
        )
        or 0,
        "performance_rows": db.scalar(select(func.count()).select_from(Performance)) or 0,
    }
    return {
        "business": settings.BUSINESS_NAME,
        "ai_enabled": ai_client.enabled,
        "model": settings.CLAUDE_MODEL if ai_client.enabled else None,
        "mode": "live_research" if ai_client.enabled else "inferred (offline heuristic)",
        "counts": counts,
        "today": dt.date.today().isoformat(),
    }


# --------------------------------------------------------------------------- #
# Research / briefing
# --------------------------------------------------------------------------- #
@router.post("/research/run")
def run_research(db: Session = Depends(get_db)):
    """Manual research refresh — runs the full daily workflow now."""
    brief = briefing_svc.run_daily_workflow(db, run_type="manual")
    db.commit()
    return _assemble_briefing(db, brief)


# --------------------------------------------------------------------------- #
# Employee: standup / tasks, weekly plan, and chat
# --------------------------------------------------------------------------- #
@router.get("/tasks")
def tasks(db: Session = Depends(get_db)):
    return tasks_svc.build_tasks(db)


@router.post("/plan/week")
def plan_week(body: PlanWeek, db: Session = Depends(get_db)):
    plan = planner_svc.plan_week(db, start_date=body.start_date, posts=body.posts)
    db.commit()
    return plan


@router.get("/chat")
def chat_history(db: Session = Depends(get_db)):
    return {"messages": employee_ai.history(db), "ai_enabled": ai_client.enabled}


@router.post("/chat")
def chat_send(body: ChatSend, db: Session = Depends(get_db)):
    result = employee_ai.chat(db, body.message)
    db.commit()
    return result


@router.delete("/chat")
def chat_clear(db: Session = Depends(get_db)):
    employee_ai.clear_history(db)
    db.commit()
    return {"ok": True}


@router.get("/briefing/today")
def briefing_today(db: Session = Depends(get_db)):
    today = dt.date.today()
    brief = db.scalar(select(Briefing).where(Briefing.date == today))
    if not brief:
        return {"exists": False, "date": today.isoformat()}
    return _assemble_briefing(db, brief)


@router.get("/briefing/{date}")
def briefing_by_date(date: str, db: Session = Depends(get_db)):
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "Invalid date")
    brief = db.scalar(select(Briefing).where(Briefing.date == d))
    if not brief:
        raise HTTPException(404, "No briefing for that date")
    return _assemble_briefing(db, brief)


@router.get("/briefings")
def list_briefings(db: Session = Depends(get_db)):
    rows = db.scalars(select(Briefing).order_by(Briefing.date.desc()).limit(60)).all()
    return [{"date": r.date.isoformat(), "headline": r.headline, "source": r.source} for r in rows]


def _assemble_briefing(db: Session, brief: Briefing) -> dict:
    data = brief.data or {}
    primary = db.get(Idea, brief.primary_idea_id) if brief.primary_idea_id else None
    idea_ids = data.get("idea_ids", [])
    ideas = [db.get(Idea, i) for i in idea_ids]
    ideas = [i for i in ideas if i is not None]
    return {
        "exists": True,
        "briefing": ser.briefing_dict(brief),
        "primary_idea": ser.idea_dict(primary, full=True) if primary else None,
        "trends_worth_using": data.get("trends_worth_using", []),
        "additional_ideas": [
            ser.idea_dict(i)
            for i in sorted(ideas, key=lambda x: x.priority_score, reverse=True)
            if not primary or i.id != primary.id
        ][:5],
        "community_engagement": data.get("community_engagement", []),
        "repurpose_ideas": data.get("repurpose_ideas", []),
    }


# --------------------------------------------------------------------------- #
# Trends
# --------------------------------------------------------------------------- #
@router.get("/trends")
def list_trends(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Trend).order_by(Trend.date_discovered.desc(), Trend.id.desc())
    if status:
        stmt = stmt.where(Trend.status == status)
    rows = db.scalars(stmt.limit(200)).all()
    return [ser.trend_dict(t) for t in rows]


# --------------------------------------------------------------------------- #
# Ideas (content database)
# --------------------------------------------------------------------------- #
@router.get("/ideas")
def list_ideas(
    status: str | None = None,
    category: str | None = None,
    platform: str | None = None,
    content_type: str | None = None,
    q: str | None = Query(None, description="search titles / hooks / concepts"),
    db: Session = Depends(get_db),
):
    stmt = select(Idea).order_by(Idea.priority_score.desc(), Idea.created_at.desc())
    if status:
        stmt = stmt.where(Idea.status == status)
    if category:
        stmt = stmt.where(Idea.category == category)
    if platform:
        stmt = stmt.where(Idea.platform == platform)
    if content_type:
        stmt = stmt.where(Idea.content_type == content_type)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Idea.title).like(like),
                func.lower(Idea.hook).like(like),
                func.lower(Idea.concept).like(like),
                func.lower(Idea.breed).like(like),
            )
        )
    rows = db.scalars(stmt.limit(500)).all()
    return [ser.idea_dict(i) for i in rows]


@router.get("/ideas/{idea_id}")
def get_idea(idea_id: int, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    return ser.idea_dict(idea, full=True)


@router.post("/ideas")
def create_idea(body: IdeaCreate, db: Session = Depends(get_db)):
    brand = brand_rules_dict(db)
    weights = brand.get("priority_weights", {})
    fp = dedup.fingerprint(body.title, body.hook, body.category, body.breed)
    series = None
    if body.series_name:
        series = db.scalar(select(Series).where(Series.name == body.series_name))
    idea = Idea(
        title=body.title,
        category=body.category,
        content_type=body.content_type,
        breed=body.breed,
        platform=body.platform,
        concept=body.concept,
        hook=body.hook,
        business_objective=body.business_objective,
        requirements=body.requirements,
        virality_score=body.virality_score,
        conversion_value=body.conversion_value,
        difficulty=body.difficulty,
        priority_score=compute_priority(
            body.virality_score, body.conversion_value, body.difficulty, weights
        ),
        series_id=series.id if series else None,
        notes=body.notes,
        status="New",
        fingerprint=fp,
    )
    db.add(idea)
    db.commit()
    return ser.idea_dict(idea, full=True)


@router.patch("/ideas/{idea_id}")
def update_idea(idea_id: int, body: IdeaUpdate, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(idea, field, value)
    db.commit()
    return ser.idea_dict(idea, full=True)


@router.post("/ideas/{idea_id}/package")
def build_package(idea_id: int, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    result = ideas_svc.build_filming_package(db, idea)
    db.commit()
    return {"idea": ser.idea_dict(idea, full=True), **result}


@router.post("/ideas/{idea_id}/action")
def idea_action(idea_id: int, body: IdeaAction, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")

    action = body.action
    value = body.value

    if action == "approve":
        idea.status = "Approved"
    elif action == "reject":
        idea.status = "Archived"
        idea.notes = (idea.notes + f" | Rejected: {value}").strip(" |")
    elif action == "archive":
        idea.status = "Archived"
    elif action == "ready":
        idea.status = "Ready to Film"
    elif action == "mark_filmed":
        idea.status = "Filmed"
        idea.recording_date = idea.recording_date or dt.date.today()
    elif action == "mark_published":
        idea.status = "Published"
        idea.publishing_date = idea.publishing_date or dt.date.today()
    elif action == "retest":
        idea.status = "Retest"
        idea.reusable = True
    elif action == "change_breed":
        idea.breed = value
        ideas_svc.regenerate_variant(db, idea, f"change the featured breed to {value}")
    elif action == "change_platform":
        idea.platform = value
        ideas_svc.regenerate_variant(db, idea, f"adapt this for {value}")
    elif action in {"revise", "regenerate"}:
        idea.status = "Needs Revision" if action == "revise" else idea.status
        ideas_svc.regenerate_variant(
            db, idea, value or "produce a fresh alternative version"
        )
    elif action == "shorter":
        ideas_svc.regenerate_variant(db, idea, "make the script noticeably shorter and punchier")
    elif action == "funnier":
        ideas_svc.regenerate_variant(db, idea, "make it funnier and more playful")
    elif action == "more_educational":
        ideas_svc.regenerate_variant(db, idea, "make it more educational and informative")
    else:
        raise HTTPException(400, f"Unknown action: {action}")

    db.commit()
    return ser.idea_dict(idea, full=True)


@router.post("/ideas/{idea_id}/feedback")
def add_feedback(idea_id: int, body: FeedbackCreate, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    stamp = dt.date.today().isoformat()
    idea.notes = (idea.notes + f"\n[{stamp}] {body.note}").strip()
    db.commit()
    return ser.idea_dict(idea, full=True)


# --------------------------------------------------------------------------- #
# Performance
# --------------------------------------------------------------------------- #
@router.post("/ideas/{idea_id}/performance")
def add_performance(idea_id: int, body: PerformanceCreate, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    data = body.model_dump()
    data["date"] = data.get("date") or dt.date.today()
    # Default context from the idea where the owner left blanks.
    data["platform"] = data["platform"] or idea.platform
    data["category"] = data["category"] or idea.category
    data["hook"] = data["hook"] or idea.hook
    data["video_format"] = data["video_format"] or idea.content_type
    perf = Performance(idea_id=idea.id, **data)
    db.add(perf)
    if idea.status not in {"Published", "Repurpose", "Retest", "Archived"}:
        idea.status = "Published"
        idea.publishing_date = idea.publishing_date or data["date"]
    db.commit()
    return ser.performance_dict(perf)


@router.get("/performance")
def list_performance(db: Session = Depends(get_db)):
    rows = db.scalars(select(Performance).order_by(Performance.date.desc()).limit(300)).all()
    return [ser.performance_dict(p) for p in rows]


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
@router.get("/calendar")
def calendar(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Idea).where(
            or_(Idea.recording_date.is_not(None), Idea.publishing_date.is_not(None))
        )
    ).all()
    events = []
    for i in rows:
        if i.recording_date:
            events.append(
                {"date": i.recording_date.isoformat(), "type": "record", "idea_id": i.id, "title": i.title}
            )
        if i.publishing_date:
            events.append(
                {"date": i.publishing_date.isoformat(), "type": "publish", "idea_id": i.id, "title": i.title}
            )
    events.sort(key=lambda e: e["date"])
    return events


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
@router.get("/analytics")
def analytics_view(db: Session = Depends(get_db)):
    result, source = analytics.run_analysis(db)
    result["source"] = source
    return result


# --------------------------------------------------------------------------- #
# Series
# --------------------------------------------------------------------------- #
@router.get("/series")
def list_series(db: Session = Depends(get_db)):
    rows = db.scalars(select(Series).order_by(Series.name)).all()
    return [ser.series_dict(s) for s in rows]


@router.post("/series")
def upsert_series(body: SeriesUpsert, db: Session = Depends(get_db)):
    existing = db.scalar(select(Series).where(Series.name == body.name))
    if existing:
        for field, value in body.model_dump().items():
            setattr(existing, field, value)
        db.commit()
        return ser.series_dict(existing)
    s = Series(**body.model_dump())
    db.add(s)
    db.commit()
    return ser.series_dict(s)


# --------------------------------------------------------------------------- #
# Competitors / inspiration
# --------------------------------------------------------------------------- #
@router.get("/competitors")
def list_competitors(db: Session = Depends(get_db)):
    rows = db.scalars(select(Competitor).order_by(Competitor.id)).all()
    return [ser.competitor_dict(c) for c in rows]


# --------------------------------------------------------------------------- #
# Brand rules
# --------------------------------------------------------------------------- #
@router.get("/brand-rules")
def get_brand_rules(db: Session = Depends(get_db)):
    return brand_rules_dict(db)


@router.put("/brand-rules")
def update_brand_rule(body: BrandRuleUpdate, db: Session = Depends(get_db)):
    from ..models import BrandRule

    row = db.scalar(select(BrandRule).where(BrandRule.key == body.key))
    if not row:
        row = BrandRule(key=body.key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    return {"key": body.key, "value": body.value}


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
@router.get("/logs")
def list_logs(db: Session = Depends(get_db)):
    rows = db.scalars(select(ResearchLog).order_by(ResearchLog.created_at.desc()).limit(50)).all()
    return [ser.log_dict(r) for r in rows]
