"""Offline heuristic fallback.

When no Claude key is configured (or the API is temporarily unavailable) the
app still runs the full end-to-end workflow so the owner can try it and so
scheduled jobs never crash. Everything produced here is explicitly labelled
`source="inferred"` and surfaced in the UI as *inferred from evergreen puppy
best-practices, not confirmed live research* — it is never presented as a real
platform-wide trend.

The heuristics draw on durable short-form puppy formats and the store's own
recurring series, so the output is realistic and filmable rather than random.
"""
from __future__ import annotations

import datetime as dt
import random

INFERRED_NOTE = (
    "Inferred from durable short-form puppy best-practices — not confirmed live "
    "research. Add an ANTHROPIC_API_KEY for daily live trend research."
)

_EVERGREEN_TRENDS = [
    {
        "name": "Two-choice 'let the puppy decide'",
        "platform": "TikTok",
        "description": "Creators give a pet two labeled options and film the pick; comments argue the outcome.",
        "why_working": "Unpredictable outcome + built-in comment bait ('mine would pick left').",
        "brand_fit": "Perfect for showing puppy personalities without any script.",
        "expected_lifespan": "Evergreen format",
        "adaptation": "Offer a puppy two toys or two beds and let it choose on camera.",
        "filming_needs": "One puppy, two clearly different labeled options, one clean take.",
        "best_platform": "TikTok",
        "reusable_across_platforms": True,
        "risks": "None noted — keep options safe and puppy comfortable.",
        "difficulty": "Easy",
        "est_filming_time": "8 min",
        "requirements": "1 employee, 1 puppy, 2 props",
        "business_objective": "shares",
        "virality_score": 7,
        "conversion_value": 5,
    },
    {
        "name": "'Guess the breed' reveal",
        "platform": "Instagram",
        "description": "Show a pet, ask viewers to guess the breed, reveal after a beat.",
        "why_working": "Interactive game format reliably drives comments.",
        "brand_fit": "Showcases the store's small breeds and expertise.",
        "expected_lifespan": "Evergreen format",
        "adaptation": "Close-up of a Maltipoo or Yorkie, on-screen 'Guess?', reveal + one fact.",
        "filming_needs": "One clear close-up, a reveal card overlay.",
        "best_platform": "Instagram Reels",
        "reusable_across_platforms": True,
        "risks": "Avoid any health claims in the fact.",
        "difficulty": "Easy",
        "est_filming_time": "6 min",
        "requirements": "1 employee, 1 puppy",
        "business_objective": "comments",
        "virality_score": 6,
        "conversion_value": 5,
    },
    {
        "name": "Tiny-puppy-big-personality moment",
        "platform": "YouTube Shorts",
        "description": "Short clips of the smallest pet acting boldly; strong watch-time.",
        "why_working": "Cuteness + surprise + a relatable 'runs the whole house' story.",
        "brand_fit": "Small breeds are the store's entire catalog.",
        "expected_lifespan": "Evergreen format",
        "adaptation": "Film the smallest puppy 'bossing' a bigger toy or a calmer puppy.",
        "filming_needs": "One candid clip of bold behavior, on-screen caption.",
        "best_platform": "YouTube Shorts",
        "reusable_across_platforms": True,
        "risks": "Only genuine behavior — never provoke the puppy.",
        "difficulty": "Easy",
        "est_filming_time": "10 min",
        "requirements": "1 employee, 1-2 puppies",
        "business_objective": "reach",
        "virality_score": 7,
        "conversion_value": 4,
    },
    {
        "name": "Morning puppy routine (calm BTS)",
        "platform": "Instagram",
        "description": "Quiet, satisfying behind-the-scenes of opening/prep routines.",
        "why_working": "Calming BTS builds trust and parasocial connection with a small business.",
        "brand_fit": "Shows the store cares for the puppies — reputation + warmth.",
        "expected_lifespan": "Evergreen format",
        "adaptation": "Film the morning feeding/play prep as a soft, wordless routine.",
        "filming_needs": "A few steady clips of the routine, gentle captions.",
        "best_platform": "Instagram Reels",
        "reusable_across_platforms": True,
        "risks": "None noted.",
        "difficulty": "Medium",
        "est_filming_time": "15 min",
        "requirements": "1 employee, several puppies, normal setup",
        "business_objective": "follows",
        "virality_score": 5,
        "conversion_value": 6,
    },
    {
        "name": "'Which one would you take home?'",
        "platform": "TikTok",
        "description": "Line up a few pets and ask viewers to pick a favorite in the comments.",
        "why_working": "Direct question format is pure comment fuel and drives saves.",
        "brand_fit": "Turns browsing into a decision and a store visit.",
        "expected_lifespan": "Evergreen format",
        "adaptation": "Pan across 3 available puppies, on-screen 'Which one?', soft visit CTA.",
        "filming_needs": "One clean pan, numbered overlays, a visit CTA.",
        "best_platform": "TikTok",
        "reusable_across_platforms": True,
        "risks": "No prices on screen unless approved.",
        "difficulty": "Easy",
        "est_filming_time": "7 min",
        "requirements": "1 employee, 3 puppies",
        "business_objective": "visits",
        "virality_score": 7,
        "conversion_value": 8,
    },
]


def offline_trends(count: int = 4) -> dict:
    picks = random.sample(_EVERGREEN_TRENDS, k=min(count, len(_EVERGREEN_TRENDS)))
    trends = []
    for t in picks:
        t = dict(t)
        t["source"] = "inferred"
        trends.append(t)
    return {"source": "inferred", "notes": INFERRED_NOTE, "trends": trends}


# Puppy-first rotation: lead with puppy_focus, never talking_head (the offline
# evergreen formats are all puppy-driven), so the offline slate models the same
# balanced content mix the live strategist is instructed to produce.
_FORMAT_ROTATION = ["puppy_focus", "puppy_focus", "text_only", "voiceover", "puppy_focus"]


def offline_ideas(trends: list[dict], series: list[dict]) -> dict:
    """Turn inferred trends + recurring series into idea skeletons."""
    ideas = []
    breeds = ["Maltipoo", "Yorkie", "Pomeranian", "Cavapoo", "Shih Tzu", "Bichon"]

    for idx, t in enumerate(trends):
        ideas.append(
            {
                "title": t["adaptation"][:80],
                "category": "Viral Entertainment"
                if t["business_objective"] in {"shares", "reach", "comments"}
                else "Conversion",
                "content_type": "current_trend",
                "format": _FORMAT_ROTATION[idx % len(_FORMAT_ROTATION)],
                "breed": random.choice(breeds),
                "platform": t.get("best_platform", "Instagram"),
                "series_name": "",
                "concept": t["adaptation"],
                "hook_idea": _hook_for(t),
                "business_objective": t["business_objective"],
                "difficulty": t["difficulty"],
                "est_filming_time": t["est_filming_time"],
                "requirements": t["requirements"],
                "virality_score": t["virality_score"],
                "conversion_value": t["conversion_value"],
                "trend_name": t["name"],
                "notes": "Inferred idea from an evergreen format.",
            }
        )

    # Add a couple of recurring-series installments for balance.
    for s in series[:2]:
        ideas.append(
            {
                "title": f"{s['name']}: today's pick",
                "category": "Viral Entertainment",
                "content_type": "recurring_series",
                "format": "puppy_focus",
                "breed": random.choice(breeds),
                "platform": "Instagram",
                "series_name": s["name"],
                "concept": s.get("repeatable_format", ""),
                "hook_idea": s.get("opening_hook", ""),
                "business_objective": "follows",
                "difficulty": "Easy",
                "est_filming_time": "10 min",
                "requirements": "1 employee, 1 puppy",
                "virality_score": 6,
                "conversion_value": 5,
                "trend_name": "",
                "notes": "Installment of a recurring series.",
            }
        )
    return {"ideas": ideas}


def _hook_for(trend: dict) -> str:
    obj = trend.get("business_objective")
    options = {
        "shares": "The whole store argued about this — the puppy settled it.",
        "comments": "Most people guess this little one wrong.",
        "reach": "The smallest puppy here runs the entire room.",
        "visits": "You get about three seconds to pick a favorite.",
        "follows": "This is what the first ten minutes here actually look like.",
    }
    return options.get(obj, "Watch what this puppy does next.")


def offline_filming_package(idea: dict) -> dict:
    breed = idea.get("breed") or "puppy"
    hook = idea.get("hook_idea") or "Watch what this puppy does next."
    concept = idea.get("concept", "")
    fmt = (idea.get("format") or "puppy_focus").strip().lower()

    if fmt == "talking_head":
        script = f"{hook} {concept} Come meet this one in person at the showroom."
        filming = (
            "1) Open on the puppy, then bring a person into frame talking to camera. "
            "2) Keep the puppy on screen the whole time. 3) End on the puppy's face. "
            "Hold the phone steady, film in good light, keep the puppy calm."
        )
    elif fmt == "voiceover":
        script = f"(Voiceover, person off-camera) {hook} {concept}"
        filming = (
            "1) Open on a close-up of the puppy. 2) Record the lines as an "
            "off-camera voiceover over the puppy footage. 3) End on the puppy's "
            "face. Keep the puppy on screen throughout; film in good light."
        )
    elif fmt == "text_only":
        script = "(No talking — on-screen text only.)"
        filming = (
            "1) Open on a close-up of the puppy. 2) Let the on-screen text carry the "
            "hook and the action — no talking. 3) End on the puppy's face. Steady "
            "phone, good light, gentle music."
        )
    else:  # puppy_focus (default) and skit both lead puppy-first with on-screen text
        script = f"{hook} {concept} Come meet this one in person at the showroom."
        filming = (
            "1) Open on a close-up of the puppy. 2) Cut to the action described in "
            "the concept in one clean take, with on-screen text carrying the story. "
            "3) End on the puppy's face. Hold the phone steady, film in good light, "
            "keep the puppy calm and comfortable."
        )

    return {
        "first_second_visual": f"Tight close-up on the {breed} looking right into the camera.",
        "spoken_hook": hook,
        "script": script,
        "filming_instructions": filming,
        "on_screen_text": f"{breed} • Lawrenceville, GA",
        "suggested_length": "20 seconds",
        "editing_instructions": (
            "Quick cuts, captions on every line, keep it under 25 seconds, bright "
            "and clean color."
        ),
        "audio_direction": "Upbeat, gentle trending-style audio; keep the puppy's real sounds audible.",
        "caption": f"{concept} Come say hi in Lawrenceville. Which one's your favorite?",
        "platform_title": idea.get("title", "Puppy of the day"),
        "youtube_title": f"{breed} with a big personality #shorts",
        "hashtags": _offline_hashtags(breed),
        "cover_text": hook[:40],
        "pinned_comment": "Which one would you take home? 🐶",
        "call_to_action": "Come meet the puppies in person in Lawrenceville, or call the store.",
        "backup_hook": "Nobody warned us this puppy would do this.",
        "backup_caption": f"This little {breed} has opinions. Come meet the crew in Lawrenceville.",
        "no_speak_version": (
            "Film the same moment with no talking — let on-screen text carry the hook "
            "and caption the action; add gentle music."
        ),
        "_offline": True,
    }


def _offline_hashtags(breed: str) -> str:
    b = breed.lower().replace(" ", "")
    return (
        f"#{b} #puppiesofinstagram #smalldogsofinstagram #puppylove "
        f"#lawrencevillega #atlantapuppies #gwinnettcounty #georgiapuppies "
        f"#puppyreels #teacuppuppy"
    )


def offline_analysis(rows: list[dict]) -> dict:
    if not rows:
        return {
            "data_confidence": "low",
            "headline": "No performance data yet — publish and log a few posts to unlock insights.",
            "best_hooks": [],
            "best_breeds": [],
            "best_lengths": [],
            "winning_formats": [],
            "topics_driving_comments": [],
            "topics_driving_inquiries": [],
            "best_posting_times": [],
            "series_to_continue": [],
            "series_to_stop": [],
            "ideas_to_retest": [],
            "ideas_to_stop": [],
            "recommendations": [
                "Log metrics for your next 5-10 posts so the analyst can find patterns.",
                "Track saves, shares, watch time, and store inquiries — not just likes.",
            ],
        }
    # Simple deterministic aggregation.
    def top(key, score):
        agg: dict[str, float] = {}
        for r in rows:
            k = (r.get(key) or "").strip()
            if not k:
                continue
            agg[k] = agg.get(k, 0.0) + score(r)
        return [k for k, _ in sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:3]]

    def engagement(r):
        return (
            r.get("shares", 0) * 3
            + r.get("saves", 0) * 3
            + r.get("comments", 0) * 2
            + (r.get("completion_rate") or 0)
        )

    def inquiry(r):
        return r.get("calls", 0) + r.get("messages", 0) + r.get("appointments", 0) * 3

    return {
        "data_confidence": "low" if len(rows) < 5 else "medium",
        "headline": "Early signal — prioritising watch-time, shares, saves and store inquiries.",
        "best_hooks": top("hook", engagement),
        "best_breeds": [],
        "best_lengths": [],
        "winning_formats": top("video_format", engagement),
        "topics_driving_comments": top("category", lambda r: r.get("comments", 0)),
        "topics_driving_inquiries": top("category", inquiry),
        "best_posting_times": [],
        "series_to_continue": [],
        "series_to_stop": [],
        "ideas_to_retest": [],
        "ideas_to_stop": [],
        "recommendations": [
            "Double down on the hooks and formats above; retest weaker ones with a new hook.",
            "Keep logging store inquiries so conversion signal sharpens.",
        ],
    }
