"""Convert ORM rows to plain JSON-serialisable dicts for the API."""
from __future__ import annotations

from ..models import Briefing, Competitor, Idea, Performance, ResearchLog, Series, Trend


def _iso(d):
    return d.isoformat() if d else None


def trend_dict(t: Trend) -> dict:
    return {
        "id": t.id,
        "date_discovered": _iso(t.date_discovered),
        "name": t.name,
        "platform": t.platform,
        "description": t.description,
        "why_working": t.why_working,
        "brand_fit": t.brand_fit,
        "expected_lifespan": t.expected_lifespan,
        "adaptation": t.adaptation,
        "filming_needs": t.filming_needs,
        "best_platform": t.best_platform,
        "reusable_across_platforms": t.reusable_across_platforms,
        "risks": t.risks,
        "difficulty": t.difficulty,
        "est_filming_time": t.est_filming_time,
        "requirements": t.requirements,
        "business_objective": t.business_objective,
        "virality_score": t.virality_score,
        "conversion_value": t.conversion_value,
        "source": t.source,
        "status": t.status,
    }


def idea_dict(i: Idea, *, full: bool = False) -> dict:
    base = {
        "id": i.id,
        "date_created": _iso(i.date_created),
        "title": i.title,
        "category": i.category,
        "content_type": i.content_type,
        "breed": i.breed,
        "platform": i.platform,
        "trend_source": i.trend_source,
        "series": i.series.name if i.series else "",
        "series_id": i.series_id,
        "virality_score": i.virality_score,
        "conversion_value": i.conversion_value,
        "difficulty": i.difficulty,
        "est_filming_time": i.est_filming_time,
        "priority_score": i.priority_score,
        "hook": i.hook,
        "concept": i.concept,
        "status": i.status,
        "assigned_employee": i.assigned_employee,
        "recording_date": _iso(i.recording_date),
        "publishing_date": _iso(i.publishing_date),
        "reusable": i.reusable,
        "suggested_reuse_date": _iso(i.suggested_reuse_date),
        "business_objective": i.business_objective,
        "compliance": i.compliance or {},
        "has_package": bool(i.script),
    }
    if not full:
        return base
    base.update(
        {
            "first_second_visual": i.first_second_visual,
            "script": i.script,
            "filming_instructions": i.filming_instructions,
            "on_screen_text": i.on_screen_text,
            "suggested_length": i.suggested_length,
            "editing_instructions": i.editing_instructions,
            "audio_direction": i.audio_direction,
            "caption": i.caption,
            "platform_title": i.platform_title,
            "youtube_title": i.youtube_title,
            "hashtags": i.hashtags,
            "cover_text": i.cover_text,
            "pinned_comment": i.pinned_comment,
            "call_to_action": i.call_to_action,
            "backup_hook": i.backup_hook,
            "backup_caption": i.backup_caption,
            "no_speak_version": i.no_speak_version,
            "requirements": i.requirements,
            "notes": i.notes,
            "performances": [performance_dict(p) for p in i.performances],
        }
    )
    return base


def performance_dict(p: Performance) -> dict:
    return {
        "id": p.id,
        "idea_id": p.idea_id,
        "date": _iso(p.date),
        "platform": p.platform,
        "category": p.category,
        "video_format": p.video_format,
        "hook": p.hook,
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


def series_dict(s: Series) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "repeatable_format": s.repeatable_format,
        "opening_hook": s.opening_hook,
        "recording_process": s.recording_process,
        "publishing_frequency": s.publishing_frequency,
        "why_return": s.why_return,
        "evolution": s.evolution,
        "business_goal": s.business_goal,
        "active": s.active,
    }


def competitor_dict(c: Competitor) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "platform": c.platform,
        "what_works": c.what_works,
        "format_type": c.format_type,
        "adaptation_idea": c.adaptation_idea,
        "date_noted": _iso(c.date_noted),
    }


def briefing_dict(b: Briefing) -> dict:
    return {
        "id": b.id,
        "date": _iso(b.date),
        "headline": b.headline,
        "summary": b.summary,
        "primary_idea_id": b.primary_idea_id,
        "source": b.source,
        "data": b.data or {},
    }


def log_dict(row: ResearchLog) -> dict:
    return {
        "id": row.id,
        "run_type": row.run_type,
        "status": row.status,
        "source": row.source,
        "message": row.message,
        "trends_found": row.trends_found,
        "ideas_created": row.ideas_created,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
