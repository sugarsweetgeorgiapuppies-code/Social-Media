"""Pydantic request bodies for the API (responses are serialised as dicts)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class IdeaCreate(BaseModel):
    title: str
    category: str = "Viral Entertainment"
    content_type: str = "evergreen"
    breed: str = ""
    platform: str = "Instagram"
    concept: str = ""
    hook: str = ""
    business_objective: str = ""
    requirements: str = ""
    virality_score: int = 5
    conversion_value: int = 5
    difficulty: str = "Medium"
    series_name: str = ""
    notes: str = ""


class IdeaUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    content_type: str | None = None
    breed: str | None = None
    platform: str | None = None
    concept: str | None = None
    hook: str | None = None
    script: str | None = None
    caption: str | None = None
    hashtags: str | None = None
    status: str | None = None
    assigned_employee: str | None = None
    recording_date: dt.date | None = None
    publishing_date: dt.date | None = None
    notes: str | None = None
    reusable: bool | None = None
    suggested_reuse_date: dt.date | None = None


class IdeaAction(BaseModel):
    action: str  # approve | reject | revise | regenerate | shorter | funnier |
    #             more_educational | change_breed | change_platform |
    #             mark_filmed | mark_published | archive | retest
    value: str = ""  # optional payload (new breed, platform, revision note)


class PerformanceCreate(BaseModel):
    platform: str = ""
    category: str = ""
    video_format: str = ""
    hook: str = ""
    video_length_seconds: int | None = None
    views: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    avg_watch_time_seconds: float | None = None
    completion_rate: float | None = None
    follower_growth: int = 0
    profile_visits: int = 0
    website_clicks: int = 0
    calls: int = 0
    messages: int = 0
    appointments: int = 0
    notes: str = ""
    date: dt.date | None = None


class SeriesUpsert(BaseModel):
    name: str
    repeatable_format: str = ""
    opening_hook: str = ""
    recording_process: str = ""
    publishing_frequency: str = ""
    why_return: str = ""
    evolution: str = ""
    business_goal: str = ""
    active: bool = True


class BrandRuleUpdate(BaseModel):
    key: str
    value: object


class FeedbackCreate(BaseModel):
    note: str
