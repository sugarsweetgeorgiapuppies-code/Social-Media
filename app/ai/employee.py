"""The conversational employee.

A chat interface where the owner talks in plain English and the employee
actually does the work via tools (research, plan the week, create ideas, write
scripts, check performance) or answers directly (captions, comment replies,
customer questions, advice).

Falls back to lightweight keyword routing when no Claude key is configured, so
the action verbs ('plan my week', 'research today') still work offline.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..logging_config import get_logger
from ..models import ConversationMessage, Idea
from ..seed import brand_rules_dict
from ..services import analytics, dedup
from ..services import briefing as briefing_svc
from ..services import ideas as ideas_svc
from ..services import planner as planner_svc
from ..services import tasks as tasks_svc
from .client import ai_client
from .prompts import build_system_prompt

log = get_logger(__name__)

TOOLS = [
    {
        "name": "research_today",
        "description": "Research today's social media trends and build today's plan, including the single best video to film today.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "plan_week",
        "description": "Create a posting schedule for the coming days and put it on the owner's calendar (creates the posts with film/post dates).",
        "input_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "integer", "description": "How many posts to schedule, 1-7 (default 5)."},
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD (default today)."},
            },
            "required": [],
        },
    },
    {
        "name": "create_idea",
        "description": "Add one specific new content idea the owner asked for.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "concept": {"type": "string", "description": "What happens in the video."},
                "platform": {"type": "string"},
                "breed": {"type": "string"},
                "category": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "write_script",
        "description": "Write the complete filming package (script, shot list, caption, hashtags, titles) for an existing idea, referenced by its id.",
        "input_schema": {
            "type": "object",
            "properties": {"idea_id": {"type": "integer"}},
            "required": ["idea_id"],
        },
    },
    {
        "name": "list_ideas",
        "description": "Look up existing ideas, optionally filtered by status (e.g. New, Approved, Published).",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "performance_summary",
        "description": "Summarize how recent posts have performed.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def _tool_research_today(db: Session, _inp: dict):
    brief = briefing_svc.run_daily_workflow(db, run_type="manual")
    return (
        f"Built today's plan. Headline: {brief.headline}. Summary: {brief.summary}",
        "Researched today's trends and built today's plan",
    )


def _tool_plan_week(db: Session, inp: dict):
    start = None
    if inp.get("start_date"):
        try:
            start = dt.date.fromisoformat(inp["start_date"])
        except ValueError:
            start = None
    plan = planner_svc.plan_week(db, start_date=start, posts=int(inp.get("posts", 5) or 5))
    lines = [f"- {p['post_on']}: {p['title']} ({p['platform']})" for p in plan["posts"]]
    return (
        f"Scheduled {plan['count']} posts starting {plan['start_date']}:\n" + "\n".join(lines),
        f"Planned {plan['count']} posts for the week (on the calendar)",
    )


def _tool_create_idea(db: Session, inp: dict):
    brand = brand_rules_dict(db)
    weights = brand.get("priority_weights", {})
    title = (inp.get("title") or "").strip()
    if not title:
        return ("No title provided.", None)
    fp = dedup.fingerprint(title, "", inp.get("category", ""), inp.get("breed", ""))
    idea = Idea(
        title=title,
        category=inp.get("category") or "Viral Entertainment",
        platform=inp.get("platform") or "Instagram",
        breed=inp.get("breed", ""),
        concept=inp.get("concept", ""),
        content_type="evergreen",
        priority_score=ideas_svc.compute_priority(6, 5, "Medium", weights),
        status="New",
        fingerprint=fp,
    )
    db.add(idea)
    db.flush()
    return (f"Created idea #{idea.id}: {idea.title}.", f"Created idea “{idea.title}”")


def _tool_write_script(db: Session, inp: dict):
    idea = db.get(Idea, int(inp.get("idea_id", 0) or 0))
    if not idea:
        return ("No idea with that id.", None)
    ideas_svc.build_filming_package(db, idea)
    return (
        f"Wrote the full script for #{idea.id} ({idea.title}). Hook: {idea.hook}",
        f"Wrote the script for “{idea.title}”",
    )


def _tool_list_ideas(db: Session, inp: dict):
    stmt = select(Idea).order_by(Idea.priority_score.desc())
    if inp.get("status"):
        stmt = stmt.where(Idea.status == inp["status"])
    rows = db.scalars(stmt.limit(int(inp.get("limit", 10) or 10))).all()
    if not rows:
        return ("No matching ideas.", None)
    lines = [f"#{i.id} [{i.status}] {i.title} ({i.platform})" for i in rows]
    return ("\n".join(lines), None)


def _tool_performance_summary(db: Session, _inp: dict):
    return (analytics.summarise_for_strategist(db), None)


_DISPATCH = {
    "research_today": _tool_research_today,
    "plan_week": _tool_plan_week,
    "create_idea": _tool_create_idea,
    "write_script": _tool_write_script,
    "list_ideas": _tool_list_ideas,
    "performance_summary": _tool_performance_summary,
}


# --------------------------------------------------------------------------- #
# State snapshot injected into the system prompt each turn
# --------------------------------------------------------------------------- #
def _state_snapshot(db: Session) -> str:
    t = tasks_svc.build_tasks(db)
    total_ideas = db.scalar(select(func.count()).select_from(Idea)) or 0
    today = dt.date.today().isoformat()
    return (
        f"CURRENT STATE (for your awareness):\n"
        f"- Date: {today}\n"
        f"- Ideas in the library: {total_ideas}\n"
        f"- Waiting for approval: {t['counts']['waiting_approval']}\n"
        f"- Ready/scheduled to film: {t['counts']['to_film']}\n"
        f"- Posts needing numbers logged: {t['counts']['need_numbers']}\n"
    )


# --------------------------------------------------------------------------- #
# Public: chat
# --------------------------------------------------------------------------- #
def chat(db: Session, user_message: str) -> dict:
    user_message = (user_message or "").strip()
    if not user_message:
        return {"reply": "What can I help with?", "actions": []}

    # Save the user's message.
    db.add(ConversationMessage(role="user", content=user_message))
    db.flush()

    if ai_client.enabled:
        reply, actions = _chat_live(db, user_message)
    else:
        reply, actions = _chat_offline(db, user_message)

    db.add(ConversationMessage(role="assistant", content=reply, actions=actions))
    db.flush()
    return {"reply": reply, "actions": actions}


def _history_messages(db: Session, limit: int = 20) -> list[dict]:
    rows = db.scalars(
        select(ConversationMessage).order_by(ConversationMessage.created_at.desc()).limit(limit)
    ).all()
    rows = list(reversed(rows))
    return [{"role": r.role, "content": r.content} for r in rows if r.content]


def _chat_live(db: Session, _user_message: str) -> tuple[str, list]:
    client = ai_client._client
    brand = brand_rules_dict(db)
    system = build_system_prompt("employee", brand) + "\n\n---\n\n" + _state_snapshot(db)
    messages = _history_messages(db)  # includes the just-saved user turn

    actions: list[str] = []
    reply_parts: list[str] = []

    try:
        for _ in range(6):  # cap the tool loop
            resp = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=2000,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                tools=TOOLS,
                messages=messages,
            )
            # Collect any assistant text.
            for block in resp.content:
                if getattr(block, "type", None) == "text" and block.text.strip():
                    reply_parts.append(block.text.strip())

            if resp.stop_reason != "tool_use":
                break

            # Execute tool calls and feed results back.
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                fn = _DISPATCH.get(block.name)
                if not fn:
                    result_text = f"Unknown tool {block.name}."
                else:
                    try:
                        result_text, action = fn(db, block.input or {})
                        if action:
                            actions.append(action)
                    except Exception as exc:  # keep chat resilient
                        log.exception("Tool %s failed", block.name)
                        result_text = f"That didn't work: {exc}"
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                )
            messages.append({"role": "user", "content": tool_results})

        reply = "\n\n".join(reply_parts).strip() or "Done."
        return reply, actions
    except Exception as exc:
        log.exception("Live chat failed")
        return (
            "Sorry — I hit a snag reaching my brain just now. Try again in a moment. "
            f"({exc})",
            actions,
        )


def _chat_offline(db: Session, user_message: str) -> tuple[str, list]:
    """Keyword routing so core actions still work without a Claude key."""
    m = user_message.lower()
    actions: list[str] = []

    if "plan" in m and ("week" in m or "schedule" in m):
        text, action = _tool_plan_week(db, {"posts": 5})
        actions.append(action)
        return (
            "Done — I planned your week and added the posts to your Plan/Calendar.\n\n" + text,
            actions,
        )
    if ("research" in m or "today" in m or "what should i post" in m) and "week" not in m:
        text, action = _tool_research_today(db, {})
        actions.append(action)
        return ("Here's today's plan — the best video is on your Today tab.\n\n" + text, actions)
    if "how" in m and "perform" in m or "numbers" in m or "results" in m:
        text, _ = _tool_performance_summary(db, {})
        return (text, actions)

    return (
        "I can take real actions even without a live connection — try:\n"
        "• “Plan my week”\n"
        "• “Get today's plan”\n"
        "• “How are my posts doing?”\n\n"
        "For full back-and-forth chat (writing captions on the spot, drafting "
        "comment replies, answering customer questions), add an Anthropic API key "
        "to your .env and restart — then I can really talk things through with you.",
        actions,
    )


def history(db: Session, limit: int = 50) -> list[dict]:
    rows = db.scalars(
        select(ConversationMessage).order_by(ConversationMessage.created_at.desc()).limit(limit)
    ).all()
    rows = list(reversed(rows))
    return [
        {"role": r.role, "content": r.content, "actions": r.actions or [], "at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


def clear_history(db: Session) -> None:
    db.query(ConversationMessage).delete()
    db.flush()
