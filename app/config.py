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

    # --- Lead & Floor Board (wall-mounted showroom TV display) ---
    # The board polls a single JSON feed. An n8n workflow serves this feed;
    # the board never talks to GoHighLevel directly and holds no credentials.
    # The URL is proxied server-side (see routes/board.py) so the browser
    # never sees it and there are no CORS headaches.
    BOARD_FEED_URL = os.getenv("BOARD_FEED_URL", "").strip()
    # Dev mode: run entirely off a seeded, self-aging mock feed so you can
    # watch cards move through every urgency color before wiring up n8n.
    # Defaults to ON whenever no BOARD_FEED_URL is configured.
    BOARD_DEV_MODE = _bool("BOARD_DEV_MODE", not BOARD_FEED_URL)
    # Name shown in the board header.
    BOARD_STORE_NAME = os.getenv("BOARD_STORE_NAME", BUSINESS_NAME).strip()
    # How often the browser re-polls the feed (seconds).
    BOARD_POLL_SECONDS = int(os.getenv("BOARD_POLL_SECONDS", "15"))
    # No successful poll within this window => show "connection lost".
    BOARD_STALE_SECONDS = int(os.getenv("BOARD_STALE_SECONDS", "90"))
    # Seconds to wait on the upstream feed before treating it as failed.
    BOARD_FEED_TIMEOUT = int(os.getenv("BOARD_FEED_TIMEOUT", "10"))

    @property
    def ai_enabled(self) -> bool:
        """True when a real Claude key is configured (live research path)."""
        return bool(self.ANTHROPIC_API_KEY)


settings = Settings()
