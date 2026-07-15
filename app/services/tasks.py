"""Standup + task list — what the employee did and what needs the owner."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Briefing, Idea, Performance


def _count(db: Session, *conds) -> int:
    return db.scalar(select(func.count()).select_from(Idea).where(*conds)) or 0


def build_tasks(db: Session) -> dict:
    today = dt.date.today()

    waiting = _count(db, Idea.status.in_(["New", "Needs Revision"]))
    to_film = _count(db, Idea.status.in_(["Approved", "Ready to Film", "Scheduled"]))

    # Published posts that have no numbers logged yet.
    published = db.scalars(select(Idea).where(Idea.status == "Published")).all()
    need_numbers = [i for i in published if not i.performances]

    # Anything scheduled to film today or overdue.
    film_today = db.scalars(
        select(Idea).where(
            Idea.recording_date.is_not(None),
            Idea.recording_date <= today,
            Idea.status.in_(["Approved", "Ready to Film", "Scheduled"]),
        )
    ).all()

    brief = db.scalar(select(Briefing).where(Briefing.date == today))
    has_plan_today = brief is not None

    tasks = []
    if not has_plan_today:
        tasks.append({"key": "plan", "label": "Get today's plan", "count": 0, "tab": "today"})
    if waiting:
        tasks.append({"key": "approve", "label": f"Approve {waiting} idea{'s' if waiting != 1 else ''}", "count": waiting, "tab": "ideas", "filter": "New"})
    if film_today:
        tasks.append({"key": "film", "label": f"Film {len(film_today)} video{'s' if len(film_today) != 1 else ''} due", "count": len(film_today), "tab": "calendar"})
    if need_numbers:
        tasks.append({"key": "numbers", "label": f"Add numbers on {len(need_numbers)} post{'s' if len(need_numbers) != 1 else ''}", "count": len(need_numbers), "tab": "results"})

    # A short, human standup line.
    if not has_plan_today:
        message = "Morning! Tap “Get today's plan” and I'll research today's trends and hand you a video to film."
    else:
        parts = []
        if brief and brief.headline:
            parts.append(f"Today's pick is ready — {brief.headline.rstrip('.')}. ")
        if waiting:
            parts.append(f"{waiting} idea{'s' if waiting != 1 else ''} waiting on your OK. ")
        if need_numbers:
            parts.append(f"When you get a sec, add numbers on {len(need_numbers)} post{'s' if len(need_numbers) != 1 else ''} so I can learn. ")
        message = "".join(parts) or "You're all caught up. Want me to plan the rest of your week?"

    return {
        "message": message,
        "tasks": tasks,
        "counts": {
            "waiting_approval": waiting,
            "to_film": to_film,
            "need_numbers": len(need_numbers),
            "film_today": len(film_today),
        },
    }
