"""Idea persistence: create from strategy output, score, and build packages."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import agents
from ..logging_config import get_logger
from ..models import CONTENT_FORMATS, DEFAULT_FORMAT, Idea, Series, Trend
from ..seed import brand_rules_dict
from . import dedup

log = get_logger(__name__)


def compute_priority(virality: int, conversion: int, difficulty: str, weights: dict) -> float:
    """Prioritise by reach, business value, and effort (difficulty)."""
    w_v = float(weights.get("virality", 1.0))
    w_c = float(weights.get("conversion", 1.0))
    w_e = float(weights.get("effort", 0.6))
    effort_penalty = {"easy": 1, "medium": 2, "hard": 3}.get((difficulty or "medium").lower(), 2)
    return round(w_v * virality + w_c * conversion - w_e * effort_penalty, 2)


def _series_id(db: Session, name: str) -> int | None:
    if not name:
        return None
    s = db.scalar(select(Series).where(Series.name == name).limit(1))
    return s.id if s else None


def create_ideas_from_strategy(
    db: Session,
    strategy: dict,
    trend_map: dict[str, int],
    *,
    source: str,
) -> list[Idea]:
    """Persist strategist output, skipping duplicates unless it's a retest."""
    brand = brand_rules_dict(db)
    weights = brand.get("priority_weights", {})
    created: list[Idea] = []

    for raw in strategy.get("ideas", []):
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        hook = (raw.get("hook_idea") or "").strip()
        category = raw.get("category") or "Viral Entertainment"
        breed = (raw.get("breed") or "").strip()
        fp = dedup.fingerprint(title, hook, category, breed)

        allow_retest = "retest" in (raw.get("notes") or "").lower()
        if dedup.is_duplicate(db, fp, allow_retest=allow_retest):
            log.info("Skipping duplicate idea: %s", title)
            continue

        virality = int(raw.get("virality_score", 5) or 5)
        conversion = int(raw.get("conversion_value", 5) or 5)
        difficulty = raw.get("difficulty", "Medium")
        fmt = (raw.get("format") or "").strip().lower()
        if fmt not in CONTENT_FORMATS:
            fmt = DEFAULT_FORMAT

        idea = Idea(
            title=title,
            category=category,
            content_type=raw.get("content_type", "evergreen"),
            format=fmt,
            breed=breed,
            platform=raw.get("platform", "Instagram"),
            trend_source=raw.get("trend_name", ""),
            trend_id=trend_map.get(raw.get("trend_name", "")),
            series_id=_series_id(db, raw.get("series_name", "")),
            virality_score=virality,
            conversion_value=conversion,
            difficulty=difficulty,
            est_filming_time=raw.get("est_filming_time", ""),
            priority_score=compute_priority(virality, conversion, difficulty, weights),
            concept=raw.get("concept", ""),
            hook=hook,
            requirements=raw.get("requirements", ""),
            business_objective=raw.get("business_objective", ""),
            notes=raw.get("notes", ""),
            status="New",
            fingerprint=fp,
        )
        if source == "inferred":
            idea.notes = (idea.notes + " [inferred idea]").strip()
        db.add(idea)
        db.flush()
        created.append(idea)

    return created


def build_filming_package(db: Session, idea: Idea) -> dict:
    """Run the scriptwriter + compliance reviewer and save onto the idea."""
    brand = brand_rules_dict(db)
    idea_dict = {
        "title": idea.title,
        "category": idea.category,
        "content_type": idea.content_type,
        "format": idea.format,
        "breed": idea.breed,
        "platform": idea.platform,
        "concept": idea.concept,
        "hook_idea": idea.hook,
        "business_objective": idea.business_objective,
        "requirements": idea.requirements,
        "suggested_length": brand.get("video_length_target", "10-45 seconds"),
    }
    package, source = agents.write_filming_package(brand, idea_dict)

    idea.first_second_visual = package.get("first_second_visual", "")
    idea.hook = package.get("spoken_hook", idea.hook)
    idea.script = package.get("script", "")
    idea.filming_instructions = package.get("filming_instructions", "")
    idea.on_screen_text = package.get("on_screen_text", "")
    idea.suggested_length = package.get("suggested_length", "")
    idea.editing_instructions = package.get("editing_instructions", "")
    idea.audio_direction = package.get("audio_direction", "")
    idea.caption = package.get("caption", "")
    idea.platform_title = package.get("platform_title", "")
    idea.youtube_title = package.get("youtube_title", "")
    idea.hashtags = package.get("hashtags", "")
    idea.cover_text = package.get("cover_text", "")
    idea.pinned_comment = package.get("pinned_comment", "")
    idea.call_to_action = package.get("call_to_action", "")
    idea.backup_hook = package.get("backup_hook", "")
    idea.backup_caption = package.get("backup_caption", "")
    idea.no_speak_version = package.get("no_speak_version", "")

    # Brand compliance gate before the owner sees it.
    verdict = agents.review_compliance(brand, package)
    idea.compliance = verdict
    if not verdict.get("passed", True) and idea.status == "New":
        idea.status = "Needs Revision"

    idea.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    return {"package_source": source, "compliance": verdict}


def regenerate_variant(db: Session, idea: Idea, instruction: str) -> dict:
    """Ask the scriptwriter for another version with a tweak.

    `instruction` examples: 'shorter', 'funnier', 'more educational',
    'change breed to Pomeranian', 'switch platform to TikTok'.
    """
    brand = brand_rules_dict(db)
    idea_dict = {
        "title": idea.title,
        "category": idea.category,
        "content_type": idea.content_type,
        "format": idea.format,
        "breed": idea.breed,
        "platform": idea.platform,
        "concept": idea.concept,
        "hook_idea": idea.hook,
        "business_objective": idea.business_objective,
        "requirements": idea.requirements,
        "revision_instruction": instruction,
    }
    package, source = agents.write_filming_package(brand, idea_dict)
    # Apply the new version directly to the existing idea.
    for field in [
        "first_second_visual", "script", "filming_instructions", "on_screen_text",
        "suggested_length", "editing_instructions", "audio_direction", "caption",
        "platform_title", "youtube_title", "hashtags", "cover_text",
        "pinned_comment", "call_to_action", "backup_hook", "backup_caption",
        "no_speak_version",
    ]:
        if field in package:
            setattr(idea, field, package.get(field, getattr(idea, field)))
    if package.get("spoken_hook"):
        idea.hook = package["spoken_hook"]
    idea.compliance = agents.review_compliance(brand, package)
    idea.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    return {"package_source": source, "compliance": idea.compliance}
