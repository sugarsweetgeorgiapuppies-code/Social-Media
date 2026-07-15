"""Thin wrapper around the Anthropic Claude API.

One code path for every specialist agent:
  * `call_json`  — a normal generation call that must return JSON
  * `research_json` — same, but with the server-side web_search tool enabled so
    the trend researcher can look up what is current.

If no API key is configured the client raises `AIUnavailable`, and callers fall
back to a clearly-labelled offline heuristic (see `app/ai/offline.py`). We never
present offline output as confirmed live research.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from ..logging_config import get_logger

log = get_logger(__name__)


class AIUnavailable(RuntimeError):
    """Raised when no Claude key is configured, or the API call fails."""


class AIClient:
    def __init__(self) -> None:
        self._client = None
        if settings.ANTHROPIC_API_KEY:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            except Exception as exc:  # pragma: no cover - import/init guard
                log.warning("Could not initialise Anthropic client: %s", exc)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # -- public API ---------------------------------------------------------
    def call_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 8000,
        effort: str | None = None,
    ) -> dict[str, Any]:
        return self._invoke(system, user, max_tokens=max_tokens, effort=effort, web_search=False)

    def research_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 8000,
        effort: str | None = None,
    ) -> dict[str, Any]:
        return self._invoke(system, user, max_tokens=max_tokens, effort=effort, web_search=True)

    # -- internals ----------------------------------------------------------
    def _invoke(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        effort: str | None,
        web_search: bool,
    ) -> dict[str, Any]:
        if not self._client:
            raise AIUnavailable("No ANTHROPIC_API_KEY configured.")

        effort = effort or settings.CLAUDE_EFFORT
        kwargs: dict[str, Any] = {
            "model": settings.CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
            "messages": [{"role": "user", "content": user}],
        }
        if web_search:
            kwargs["tools"] = [
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": settings.TREND_SEARCH_MAX_USES,
                }
            ]

        try:
            text = self._stream_text(kwargs)
        except Exception as exc:
            log.error("Claude call failed: %s", exc)
            raise AIUnavailable(str(exc)) from exc

        data = _extract_json(text)
        if data is None:
            log.error("Could not parse JSON from model output (first 400 chars): %s", text[:400])
            raise AIUnavailable("Model did not return parseable JSON.")
        return data

    def _stream_text(self, kwargs: dict[str, Any]) -> str:
        """Stream the response and return concatenated text blocks.

        Streaming avoids HTTP timeouts on longer generations and web-search
        turns (which can pause and resume server-side).
        """
        parts: list[str] = []
        with self._client.messages.stream(**kwargs) as stream:
            final = stream.get_final_message()
        for block in final.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip()


# --------------------------------------------------------------------------- #
# JSON extraction — tolerant of code fences and surrounding prose.
# --------------------------------------------------------------------------- #
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidates: list[str] = []

    # 1) fenced block(s)
    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1).strip())

    # 2) the raw text
    candidates.append(text.strip())

    # 3) first balanced { ... } object
    balanced = _first_balanced_object(text)
    if balanced:
        candidates.append(balanced)

    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# Module-level singleton.
ai_client = AIClient()
