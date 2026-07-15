"""Seed default brand rules, recurring series, and competitor inspiration.

These are the AI employee's standing instructions and starting playbook.
Everything here is editable in the dashboard after first run — it is a
starting point, not a hardcoded personality.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import BrandRule, Competitor, Series

# ---------------------------------------------------------------------------
# Brand rules (voice, avoid-list, breeds, business facts). Stored key -> value.
# ---------------------------------------------------------------------------
DEFAULT_BRAND_RULES: dict[str, object] = {
    "business": {
        "name": settings.BUSINESS_NAME,
        "type": settings.BUSINESS_TYPE,
        "address": settings.BUSINESS_ADDRESS,
        "service_area": settings.SERVICE_AREA,
        "website": settings.WEBSITE,
    },
    "voice": [
        "Friendly",
        "Natural",
        "Warm",
        "Knowledgeable",
        "Fun",
        "Family-friendly",
        "Helpful",
        "Confident without sounding pushy",
    ],
    "breeds": [
        "Maltipoo",
        "Yorkie",
        "Pomeranian",
        "Poodle",
        "Cavapoo",
        "Chorkie",
        "Miniature Schnauzer",
        "Chihuahua",
        "Shih Tzu",
        "Bichon",
    ],
    "avoid": [
        "Corporate language",
        "Excessive emojis",
        "Fake urgency",
        "Misleading claims",
        "Guaranteed virality",
        "Invented facts",
        "Fake testimonials",
        "Fake customer stories",
        "Making puppies uncomfortable for content",
        "Unsafe handling",
        "Encouraging impulsive puppy purchases",
        "Publicly posting specific puppy prices unless explicitly approved",
        "Claiming a breed is completely hypoallergenic",
        "Treating puppies like disposable products",
        "Large-breed content or breeds the store does not carry",
        "Medical advice or unsupported health claims",
    ],
    "banned_openers": [
        "Did you know?",
        "Are you looking for?",
        "Here at Sugar Sweet Georgia Puppies",
        "Welcome back",
        "In today's video",
    ],
    "video_length_target": "10-45 seconds unless a longer story is justified",
    "priority_weights": {
        # Used to rank ideas: score = w_v*virality + w_c*conversion - w_e*effort
        "virality": 1.0,
        "conversion": 1.0,
        "effort": 0.6,
    },
    "safety_note": "Puppy safety and wellbeing always come before content performance.",
}

# ---------------------------------------------------------------------------
# Recurring series (spec: Recurring Series Development)
# ---------------------------------------------------------------------------
DEFAULT_SERIES = [
    {
        "name": "Puppy of the Day",
        "repeatable_format": "Introduce one puppy, show its personality in one quick beat, end on a question.",
        "opening_hook": "The smallest one in the room today has the biggest opinion.",
        "recording_process": "Film one puppy for 20-30s, capture a signature quirk, add name + breed on screen.",
        "publishing_frequency": "Daily",
        "why_return": "Viewers come back to meet a new puppy and check if their favorite is still available.",
        "evolution": "Add 'where are they now' follow-ups when families give permission.",
        "business_goal": "Drives showroom visits and inquiries about specific puppies.",
    },
    {
        "name": "Let the Puppy Decide",
        "repeatable_format": "Offer the puppy two choices (toys, beds, employees) and let it pick.",
        "opening_hook": "We let the puppy settle a debate the whole store had.",
        "recording_process": "Set up two clearly-labeled options, film the choice in one take, react.",
        "publishing_frequency": "2-3x per week",
        "why_return": "Unpredictable outcomes and easy comment bait ('mine would pick the left one').",
        "evolution": "Bracket-style tournaments across a week.",
        "business_goal": "High shares + saves; keeps personalities memorable before a visit.",
    },
    {
        "name": "Guess the Breed",
        "repeatable_format": "Show a puppy, reveal the breed after a beat; invite guesses.",
        "opening_hook": "Most people guess this one wrong.",
        "recording_process": "Close-up of the puppy, on-screen 'Guess?', reveal card, one fact.",
        "publishing_frequency": "2x per week",
        "why_return": "Interactive game format trains the audience to comment their guess.",
        "evolution": "Compare two similar breeds side by side.",
        "business_goal": "Educational + comments; positions the store as breed experts.",
    },
    {
        "name": "Employee Picks",
        "repeatable_format": "An employee names the puppy with the biggest personality and why.",
        "opening_hook": "We asked our team which puppy runs the whole store.",
        "recording_process": "Quick employee interview, cut to the puppy doing the thing.",
        "publishing_frequency": "Weekly",
        "why_return": "Human + puppy pairing builds a cast the audience recognizes.",
        "evolution": "Let followers vote against the employee pick.",
        "business_goal": "Warmth + trust; humanizes the store.",
    },
    {
        "name": "Small Dog Myth or Fact",
        "repeatable_format": "State a common small-dog belief, then myth or fact with a short reason.",
        "opening_hook": "Half of what people believe about small dogs is wrong.",
        "recording_process": "On-screen claim, employee verdict, one supporting sentence (no medical claims).",
        "publishing_frequency": "Weekly",
        "why_return": "Useful, save-worthy education people share with fellow small-dog lovers.",
        "evolution": "Take myths from the comments.",
        "business_goal": "Saves + authority; helps buyers self-qualify.",
    },
    {
        "name": "Questions Customers Ask Us",
        "repeatable_format": "Answer one real, common question from visitors in under 30s.",
        "opening_hook": "The question we get every single day.",
        "recording_process": "Employee reads the question card, answers naturally, ends with a soft CTA.",
        "publishing_frequency": "2x per week",
        "why_return": "Directly answers buyer hesitations; predictable value.",
        "evolution": "Turn the best answers into a pinned highlight.",
        "business_goal": "Removes friction before a visit or call.",
    },
    {
        "name": "Puppies React to New Things",
        "repeatable_format": "Introduce a puppy to something new; capture the honest reaction.",
        "opening_hook": "Nobody warned us this puppy would react like this.",
        "recording_process": "Safe, gentle new object; film the reaction; keep it short and kind.",
        "publishing_frequency": "2x per week",
        "why_return": "Reliable cuteness + surprise; strong watch-time.",
        "evolution": "Compare two puppies reacting to the same thing.",
        "business_goal": "Reach + follows from pure entertainment.",
    },
]

# ---------------------------------------------------------------------------
# Competitor / format inspiration (studied, never copied)
# ---------------------------------------------------------------------------
DEFAULT_COMPETITORS = [
    {
        "name": "Street-interview / 'ask a stranger' creators (School of Hard Knocks style)",
        "platform": "TikTok / YouTube Shorts",
        "what_works": "Fast hook, one clear question, real unscripted answers, high tension/curiosity.",
        "format_type": "Interview / street content",
        "adaptation_idea": "Ask showroom visitors 'Which puppy would you take home and why?' with permission.",
    },
    {
        "name": "Pet personality accounts",
        "platform": "Instagram / TikTok",
        "what_works": "Consistent recurring characters; captions written as the pet's inner monologue.",
        "format_type": "Character-driven entertainment",
        "adaptation_idea": "Give recurring store puppies a recognizable voice in captions (honest, not invented facts).",
    },
    {
        "name": "Small-business 'day in the life' creators",
        "platform": "Instagram Reels / TikTok",
        "what_works": "Behind-the-scenes routine content builds trust and parasocial connection.",
        "format_type": "Behind-the-scenes",
        "adaptation_idea": "Morning puppy routine and store setup as a calming recurring format.",
    },
]


def seed_defaults(db: Session) -> None:
    """Insert defaults only when the tables are empty (idempotent)."""
    if not db.scalar(select(BrandRule).limit(1)):
        for key, value in DEFAULT_BRAND_RULES.items():
            db.add(BrandRule(key=key, value=value))

    if not db.scalar(select(Series).limit(1)):
        for s in DEFAULT_SERIES:
            db.add(Series(**s))

    if not db.scalar(select(Competitor).limit(1)):
        for c in DEFAULT_COMPETITORS:
            db.add(Competitor(**c))


def brand_rules_dict(db: Session) -> dict[str, object]:
    """Return all brand rules as a plain dict."""
    rows = db.scalars(select(BrandRule)).all()
    return {r.key: r.value for r in rows}
