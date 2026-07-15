"""Central configuration, loaded from environment / .env.

Every tunable lives here so a single business owner can see and change
behaviour in one place. Nothing about the AI persona is hardcoded in the
application logic — brand voice and rules live in the database (see
`seed.py`) and the prompt files live in `prompts/`.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

# Load .env if present (real deployments may inject env vars directly).
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # --- Business identity (used to seed brand rules; editable in the UI) ---
    BUSINESS_NAME = "Sugar Sweet Georgia Puppies"
    BUSINESS_TYPE = "Small-breed puppy boutique"
    BUSINESS_ADDRESS = "1848 Old Norcross Rd, Lawrenceville, Georgia"
    SERVICE_AREA = (
        "Lawrenceville, Gwinnett County, Atlanta, and surrounding Georgia communities"
    )
    WEBSITE = "https://georgiapuppiesfromheaven.com/"

    # --- AI model ---
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8").strip()
    CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "high").strip()
    TREND_SEARCH_MAX_USES = int(os.getenv("TREND_SEARCH_MAX_USES", "6"))

    # --- Database ---
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/sugarsweet.db")

    # --- Web server ---
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    # --- Scheduler ---
    DAILY_RUN_ENABLED = _bool("DAILY_RUN_ENABLED", True)
    DAILY_RUN_TIME = os.getenv("DAILY_RUN_TIME", "07:00").strip()
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York").strip()

    # --- Logging ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    @property
    def ai_enabled(self) -> bool:
        """True when a real Claude key is configured (live research path)."""
        return bool(self.ANTHROPIC_API_KEY)


settings = Settings()
