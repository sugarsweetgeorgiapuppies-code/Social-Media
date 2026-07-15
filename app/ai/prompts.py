"""Load editable prompt files and inject shared brand context.

Prompts live as separate Markdown files in `prompts/` so the owner can tune the
AI employee's behaviour without touching code. The `_brand.md` file is prepended
to every agent prompt and formatted with live brand rules.
"""
from __future__ import annotations

import datetime as dt
import functools

from ..config import PROMPTS_DIR


@functools.lru_cache(maxsize=32)
def _read(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def _bullets(items) -> str:
    if isinstance(items, (list, tuple)):
        return "\n".join(f"- {i}" for i in items)
    return str(items)


def build_system_prompt(agent_name: str, brand_rules: dict) -> str:
    """Return the shared brand context + the agent-specific prompt.

    `agent_name` is the prompt filename without extension, e.g.
    'trend_researcher'.
    """
    today = dt.date.today().isoformat()
    brand_tpl = _read("_brand")
    brand = brand_tpl.format(
        breeds=_bullets(brand_rules.get("breeds", [])),
        voice=_bullets(brand_rules.get("voice", [])),
        avoid=_bullets(brand_rules.get("avoid", [])),
        banned_openers=_bullets(brand_rules.get("banned_openers", [])),
        video_length_target=brand_rules.get(
            "video_length_target", "10-45 seconds"
        ),
        today=today,
    )

    agent_tpl = _read(agent_name)
    # Agent templates may reference {today} and {video_length_target}.
    agent = agent_tpl.format(
        today=today,
        video_length_target=brand_rules.get(
            "video_length_target", "10-45 seconds"
        ),
    )
    return f"{brand}\n\n---\n\n{agent}"


def clear_cache() -> None:
    """Drop cached prompt files (call after the owner edits a prompt)."""
    _read.cache_clear()
