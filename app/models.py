"""SQLAlchemy models — the persistent memory of the AI employee.

The `Idea` table is the searchable content database described in the spec.
Trends, briefings, performance rows, recurring series, brand rules and a
research log round out the system so the agent can (a) avoid repeating
itself, (b) learn from results, and (c) be fully audited by the owner.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- Content database status values (spec: Statuses) ---
IDEA_STATUSES = [
    "New",
    "Approved",
    "Needs Revision",
    "Ready to Film",
    "Filmed",
    "Editing",
    "Scheduled",
    "Published",
    "Repurpose",
    "Retest",
    "Archived",
]

# --- Content classification the agent must distinguish between ---
CONTENT_TYPES = [
    "current_trend",
    "evergreen",
    "conversion",
    "experimental",
    "recurring_series",
    "community_engagement",
]

CONTENT_CATEGORIES = [
    "Viral Entertainment",
    "Emotional",
    "Educational",
    "Local",
    "Behind-the-Scenes",
    "Conversion",
]

# --- Video presentation formats (balance the mix; cap talking-head) ---
# puppy_focus is the default and should dominate the slate: a puppy on screen
# first with on-screen text carrying the story, rather than a person talking.
CONTENT_FORMATS = [
    "puppy_focus",   # puppies on screen + on-screen text, no one talking to camera
    "voiceover",     # puppy footage with an off-camera human voiceover
    "talking_head",  # a person talking to the camera or to the dogs (use sparingly)
    "skit",          # a short staged scene with people and puppies
    "text_only",     # on-screen text over silent footage
]

DEFAULT_FORMAT = "puppy_focus"


class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(primary_key=True)
    date_discovered: Mapped[dt.date] = mapped_column(Date, default=lambda: _now().date(), index=True)
    name: Mapped[str] = mapped_column(String(300))
    platform: Mapped[str] = mapped_column(String(60), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    why_working: Mapped[str] = mapped_column(Text, default="")
    brand_fit: Mapped[str] = mapped_column(Text, default="")
    expected_lifespan: Mapped[str] = mapped_column(String(120), default="")
    adaptation: Mapped[str] = mapped_column(Text, default="")
    filming_needs: Mapped[str] = mapped_column(Text, default="")
    best_platform: Mapped[str] = mapped_column(String(60), default="")
    reusable_across_platforms: Mapped[bool] = mapped_column(Boolean, default=True)
    risks: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str] = mapped_column(String(40), default="Medium")
    est_filming_time: Mapped[str] = mapped_column(String(60), default="")
    requirements: Mapped[str] = mapped_column(Text, default="")
    business_objective: Mapped[str] = mapped_column(String(200), default="")
    virality_score: Mapped[int] = mapped_column(Integer, default=5)
    conversion_value: Mapped[int] = mapped_column(Integer, default=5)
    source: Mapped[str] = mapped_column(String(60), default="live_research")  # or "inferred"
    status: Mapped[str] = mapped_column(String(40), default="active")  # active | expired | rejected
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Idea(Base):
    """A single content idea + its full filming package (content database)."""

    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    date_created: Mapped[dt.date] = mapped_column(Date, default=lambda: _now().date(), index=True)

    # Identity / classification
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60), default="Viral Entertainment", index=True)
    content_type: Mapped[str] = mapped_column(String(40), default="evergreen", index=True)
    format: Mapped[str] = mapped_column(String(40), default="puppy_focus")
    breed: Mapped[str] = mapped_column(String(80), default="")
    platform: Mapped[str] = mapped_column(String(60), default="Instagram")
    trend_source: Mapped[str] = mapped_column(String(300), default="")
    trend_id: Mapped[int | None] = mapped_column(ForeignKey("trends.id"), nullable=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), nullable=True)

    # Scoring / prioritisation
    virality_score: Mapped[int] = mapped_column(Integer, default=5)
    conversion_value: Mapped[int] = mapped_column(Integer, default=5)
    difficulty: Mapped[str] = mapped_column(String(40), default="Medium")
    est_filming_time: Mapped[str] = mapped_column(String(60), default="")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # The filming package
    concept: Mapped[str] = mapped_column(Text, default="")
    why_today: Mapped[str] = mapped_column(Text, default="")
    first_second_visual: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    script: Mapped[str] = mapped_column(Text, default="")
    filming_instructions: Mapped[str] = mapped_column(Text, default="")
    on_screen_text: Mapped[str] = mapped_column(Text, default="")
    suggested_length: Mapped[str] = mapped_column(String(60), default="")
    editing_instructions: Mapped[str] = mapped_column(Text, default="")
    audio_direction: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    platform_title: Mapped[str] = mapped_column(String(300), default="")
    youtube_title: Mapped[str] = mapped_column(String(300), default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")
    cover_text: Mapped[str] = mapped_column(String(300), default="")
    pinned_comment: Mapped[str] = mapped_column(Text, default="")
    call_to_action: Mapped[str] = mapped_column(Text, default="")
    backup_hook: Mapped[str] = mapped_column(Text, default="")
    backup_caption: Mapped[str] = mapped_column(Text, default="")
    no_speak_version: Mapped[str] = mapped_column(Text, default="")

    # Requirements
    requirements: Mapped[str] = mapped_column(Text, default="")
    business_objective: Mapped[str] = mapped_column(String(200), default="")

    # Compliance review (brand safety)
    compliance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Workflow
    status: Mapped[str] = mapped_column(String(40), default="New", index=True)
    assigned_employee: Mapped[str] = mapped_column(String(120), default="")
    recording_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    publishing_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    # Reuse / dedup
    reusable: Mapped[bool] = mapped_column(Boolean, default=True)
    suggested_reuse_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    performances: Mapped[list["Performance"]] = relationship(
        back_populates="idea", cascade="all, delete-orphan"
    )
    series: Mapped["Series | None"] = relationship(back_populates="ideas")


class Briefing(Base):
    """A daily social media briefing (the employee's morning report)."""

    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, default=lambda: _now().date(), unique=True, index=True)
    headline: Mapped[str] = mapped_column(String(400), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    primary_idea_id: Mapped[int | None] = mapped_column(ForeignKey("ideas.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(60), default="live_research")  # or "inferred"
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # full briefing payload
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Performance(Base):
    """Recorded results for a published post (drives the analyst)."""

    __tablename__ = "performance"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, default=lambda: _now().date(), index=True)
    platform: Mapped[str] = mapped_column(String(60), default="")
    category: Mapped[str] = mapped_column(String(60), default="")
    video_format: Mapped[str] = mapped_column(String(120), default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    video_length_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    views: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    avg_watch_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    follower_growth: Mapped[int] = mapped_column(Integer, default=0)
    profile_visits: Mapped[int] = mapped_column(Integer, default=0)
    website_clicks: Mapped[int] = mapped_column(Integer, default=0)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    messages: Mapped[int] = mapped_column(Integer, default=0)
    appointments: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    idea: Mapped["Idea"] = relationship(back_populates="performances")


class Series(Base):
    """A recurring, recognisable content series."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    repeatable_format: Mapped[str] = mapped_column(Text, default="")
    opening_hook: Mapped[str] = mapped_column(Text, default="")
    recording_process: Mapped[str] = mapped_column(Text, default="")
    publishing_frequency: Mapped[str] = mapped_column(String(120), default="")
    why_return: Mapped[str] = mapped_column(Text, default="")
    evolution: Mapped[str] = mapped_column(Text, default="")
    business_goal: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    ideas: Mapped[list["Idea"]] = relationship(back_populates="series")


class BrandRule(Base):
    """Editable brand configuration (voice, avoid-list, breeds, etc.).

    Stored as key -> JSON value so the owner can edit any rule in the UI
    without a code change.
    """

    __tablename__ = "brand_rules"
    __table_args__ = (UniqueConstraint("key", name="uq_brand_rule_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResearchLog(Base):
    """Audit trail for research + generation runs (errors, timing, source)."""

    __tablename__ = "research_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(60), default="daily")  # daily | manual | generate
    status: Mapped[str] = mapped_column(String(40), default="ok")  # ok | error | partial
    source: Mapped[str] = mapped_column(String(60), default="live_research")
    message: Mapped[str] = mapped_column(Text, default="")
    trends_found: Mapped[int] = mapped_column(Integer, default=0)
    ideas_created: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class ConversationMessage(Base):
    """Chat history between the owner and the AI employee."""

    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list] = mapped_column(JSON, default=list)  # things the employee did
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class Competitor(Base):
    """Creators / businesses whose formats inspire adaptations."""

    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(60), default="")
    what_works: Mapped[str] = mapped_column(Text, default="")
    format_type: Mapped[str] = mapped_column(String(120), default="")
    adaptation_idea: Mapped[str] = mapped_column(Text, default="")
    date_noted: Mapped[dt.date] = mapped_column(Date, default=lambda: _now().date())
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
