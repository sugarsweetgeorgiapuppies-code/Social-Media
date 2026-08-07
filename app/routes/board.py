"""Lead & Floor Board — page, runtime config, and feed proxy.

The board is a full-screen wall display. It polls a single JSON endpoint
(``/board/feed``) every few seconds. That endpoint either:

* returns a seeded, self-aging mock feed (dev mode), or
* proxies the configured ``BOARD_FEED_URL`` (an n8n workflow) server-side.

Proxying on the server keeps the feed URL out of the browser, avoids CORS,
and means the board holds no credentials — n8n is the only thing that talks
to GoHighLevel.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from .. import board_ghl
from ..board_mock import generate_mock_feed
from ..config import STATIC_DIR, settings
from ..logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/board", tags=["board"])


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def board_page():
    """Serve the full-screen board."""
    return FileResponse(STATIC_DIR / "board.html")


@router.get("/config")
def board_config():
    """Runtime config the browser needs (nothing secret here)."""
    return {
        "storeName": settings.BOARD_STORE_NAME,
        "pollSeconds": settings.BOARD_POLL_SECONDS,
        "staleSeconds": settings.BOARD_STALE_SECONDS,
        "devMode": settings.BOARD_DEV_MODE and not settings.board_ghl_enabled,
    }


@router.get("/feed")
def board_feed():
    """Return the current board data.

    Dev mode returns generated mock data. Otherwise the configured upstream
    feed is fetched server-side and passed straight through. On any upstream
    failure we return HTTP 502 with a small error body — the frontend treats
    that as a failed poll (and, after ``BOARD_STALE_SECONDS``, shows the
    "connection lost" indicator) rather than blanking the screen.

    Priority: direct GoHighLevel (no n8n) > dev/mock > proxied BOARD_FEED_URL.
    """
    # Direct GoHighLevel: this server fetches GHL itself, so n8n runs nothing.
    if settings.board_ghl_enabled:
        try:
            return board_ghl.build_feed()
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            log.warning("Board GHL feed failed: %s", exc)
            return JSONResponse(status_code=502, content={"error": "GoHighLevel unavailable"})

    if settings.BOARD_DEV_MODE:
        return generate_mock_feed()

    if not settings.BOARD_FEED_URL:
        return JSONResponse(
            status_code=503,
            content={"error": "BOARD_FEED_URL is not configured and dev mode is off."},
        )

    try:
        req = urllib.request.Request(
            settings.BOARD_FEED_URL,
            headers={"Accept": "application/json", "User-Agent": "lead-floor-board/1.0"},
        )
        with urllib.request.urlopen(req, timeout=settings.BOARD_FEED_TIMEOUT) as resp:
            raw = resp.read()
        data = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        log.warning("Board feed fetch failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": "upstream feed unavailable"},
        )

    return JSONResponse(content=data)
