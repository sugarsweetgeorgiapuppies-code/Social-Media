"""The specialist agents.

Each function is one hat the AI employee wears. They share a single Claude
client and each load their own editable prompt file. When Claude is
unavailable they fall back to the labelled offline heuristics so the whole
system keeps working end-to-end.

Callers get back plain dicts plus a `source` marker ('live_research' or
'inferred') so the UI can be honest about where a recommendation came from.
"""
from __future__ import annotations

import json
from typing import Any

from ..logging_config import get_logger
from . import offline
from .client import AIUnavailable, ai_client
from .prompts import build_system_prompt

log = get_logger(__name__)


def research_trends(brand_rules: dict, extra_context: str = "") -> tuple[dict, str]:
    """Trend researcher. Returns (payload, source)."""
    system = build_system_prompt("trend_researcher", brand_rules)
    user = (
        "Research what is working right now and return the JSON described in "
        "your instructions. "
        + (f"\n\nExtra context:\n{extra_context}" if extra_context else "")
    )
    try:
        data = ai_client.research_json(system, user, max_tokens=9000)
        data.setdefault("source", "live_research")
        return data, data.get("source", "live_research")
    except AIUnavailable as exc:
        log.info("Trend research falling back to offline heuristic: %s", exc)
        return offline.offline_trends(), "inferred"


def strategise_ideas(
    brand_rules: dict,
    trends: list[dict],
    series: list[dict],
    performance_summary: str,
    avoid_titles: list[str],
) -> tuple[dict, str]:
    """Content strategist. Returns (payload, source)."""
    system = build_system_prompt("content_strategist", brand_rules)
    user = json.dumps(
        {
            "todays_trends": trends,
            "recurring_series": [
                {"name": s.get("name"), "format": s.get("repeatable_format")}
                for s in series
            ],
            "performance_summary": performance_summary or "No performance data yet.",
            "avoid_duplicating": avoid_titles,
        },
        ensure_ascii=False,
    )
    try:
        data = ai_client.call_json(system, user, max_tokens=9000)
        return data, "live_research"
    except AIUnavailable as exc:
        log.info("Strategy falling back to offline heuristic: %s", exc)
        return offline.offline_ideas(trends, series), "inferred"


def write_filming_package(brand_rules: dict, idea: dict) -> tuple[dict, str]:
    """Scriptwriter/producer. Returns (package, source)."""
    system = build_system_prompt("scriptwriter", brand_rules)
    user = "Produce the full filming package for this approved idea:\n" + json.dumps(
        idea, ensure_ascii=False
    )
    try:
        data = ai_client.call_json(system, user, max_tokens=6000)
        return data, "live_research"
    except AIUnavailable as exc:
        log.info("Scriptwriter falling back to offline heuristic: %s", exc)
        return offline.offline_filming_package(idea), "inferred"


def rewrite_captions(brand_rules: dict, context: dict) -> dict:
    """Caption & hashtag specialist. Returns a partial package dict."""
    system = build_system_prompt("caption_hashtag_writer", brand_rules)
    user = "Refine captions and hashtags for:\n" + json.dumps(context, ensure_ascii=False)
    try:
        return ai_client.call_json(system, user, max_tokens=1500)
    except AIUnavailable as exc:
        log.info("Caption writer falling back to offline heuristic: %s", exc)
        breed = context.get("breed") or "puppy"
        return {
            "caption": context.get("caption", "")
            or f"Come meet this little {breed} in Lawrenceville.",
            "backup_caption": f"This {breed} has opinions. Say hi in Lawrenceville.",
            "hashtags": offline._offline_hashtags(breed),
            "pinned_comment": "Which one would you take home? 🐶",
        }


def review_compliance(brand_rules: dict, package: dict) -> dict:
    """Brand compliance reviewer. Returns a verdict dict (never raises)."""
    system = build_system_prompt("brand_compliance_reviewer", brand_rules)
    user = "Review this content package:\n" + json.dumps(package, ensure_ascii=False)
    try:
        verdict = ai_client.call_json(system, user, max_tokens=1500)
        verdict.setdefault("passed", True)
        return verdict
    except AIUnavailable:
        return _offline_compliance(brand_rules, package)


def analyse_performance(brand_rules: dict, rows: list[dict]) -> tuple[dict, str]:
    """Performance analyst. Returns (payload, source)."""
    system = build_system_prompt("performance_analyst", brand_rules)
    user = "Analyse these published posts:\n" + json.dumps(rows, ensure_ascii=False)
    try:
        data = ai_client.call_json(system, user, max_tokens=4000)
        return data, "live_research"
    except AIUnavailable as exc:
        log.info("Analyst falling back to offline heuristic: %s", exc)
        return offline.offline_analysis(rows), "inferred"


def generate_briefing(brand_rules: dict, payload: dict) -> tuple[dict, str]:
    """Daily briefing generator. Returns (payload, source)."""
    system = build_system_prompt("daily_briefing_generator", brand_rules)
    user = "Assemble today's briefing from:\n" + json.dumps(payload, ensure_ascii=False)
    try:
        data = ai_client.call_json(system, user, max_tokens=3000)
        return data, "live_research"
    except AIUnavailable as exc:
        log.info("Briefing generator falling back to offline heuristic: %s", exc)
        return _offline_briefing(payload), "inferred"


# --------------------------------------------------------------------------- #
# Offline helpers for the non-JSON-schema agents.
# --------------------------------------------------------------------------- #
def _offline_compliance(brand_rules: dict, package: dict) -> dict:
    """Deterministic rule check when Claude is unavailable."""
    text = " ".join(str(v) for v in package.values()).lower()
    issues: list[str] = []
    fixes: list[str] = []

    if "hypoallergenic" in text:
        issues.append("Uses 'hypoallergenic' — cannot claim a breed is completely hypoallergenic.")
        fixes.append("Say 'lower-shedding' or 'often better for some allergy sufferers' instead.")
    if "$" in text or "price" in text:
        issues.append("References price — do not post specific prices unless approved.")
        fixes.append("Remove the price; invite a call/visit for pricing.")
    if "guaranteed" in text and "viral" in text:
        issues.append("Implies guaranteed virality.")
        fixes.append("Remove the guarantee; results cannot be promised.")
    for opener in brand_rules.get("banned_openers", []):
        if package.get("spoken_hook", "").strip().lower().startswith(opener.lower()):
            issues.append(f"Hook starts with a banned opener: '{opener}'.")
            fixes.append("Rewrite the hook to create instant curiosity or surprise.")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "risk_level": "none" if passed else "medium",
        "issues": issues,
        "fixes": fixes,
        "summary": "Passed automated brand check."
        if passed
        else "Needs a small revision before filming.",
        "_offline": True,
    }


def _offline_briefing(payload: dict) -> dict:
    trends = payload.get("trends", [])
    ideas = payload.get("ideas", [])
    top = ideas[0] if ideas else {}
    standout = trends[0]["name"] if trends else "evergreen puppy formats"
    return {
        "headline": f"Today: film '{top.get('title', 'a puppy of the day clip')}'.",
        "summary": (
            f"The strongest angle today is {standout}. Recommended video: "
            f"{top.get('title', 'a quick puppy personality clip')} on "
            f"{top.get('platform', 'Instagram')}. These trends were inferred from "
            "durable puppy best-practices rather than confirmed live research — "
            "add an ANTHROPIC_API_KEY for daily live trend research. Keep it short, "
            "keep the puppies comfortable, and end with a soft visit invitation."
        ),
        "why_film_this_today": (
            "It is the easiest to film with the highest combined reach and "
            "conversion potential on today's slate."
        ),
        "community_engagement": [
            "Ask followers in a Story: 'Which breed should be tomorrow's Puppy of the Day?'",
            "Reply to every comment on your last post within the first hour.",
            "Turn the most common customer question this week into a short video.",
        ],
        "repurpose_ideas": [
            "Cut your three best puppy clips this week into a Friday compilation Reel.",
            "Turn a popular TikTok into a YouTube Short and a Facebook post.",
        ],
        "_offline": True,
    }
