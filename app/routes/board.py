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

import hashlib
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from .. import board_ghl
from ..board_mock import generate_mock_feed
from ..config import STATIC_DIR, settings
from ..logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/board", tags=["board"])

# ---------------------------------------------------------------- access gate
# When BOARD_PIN is set, the board page and its feed require the PIN. A device
# enters it once; we drop a cookie holding a hash of the PIN (never the PIN
# itself) so the wall TV stays logged in. Blank PIN => board is open to anyone.
_COOKIE = "board_auth"


def _pin_enabled() -> bool:
    return bool(settings.BOARD_PIN)


def _token() -> str:
    """Opaque cookie value derived from the PIN (so the raw PIN isn't stored)."""
    return hashlib.sha256(f"ssgp-board::{settings.BOARD_PIN}".encode()).hexdigest()


def _authed(request: Request) -> bool:
    return not _pin_enabled() or request.cookies.get(_COOKIE) == _token()


class _PinIn(BaseModel):
    pin: str = ""


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def board_page(request: Request):
    """Serve the full-screen board (or the PIN screen if not unlocked)."""
    if not _authed(request):
        return FileResponse(STATIC_DIR / "board_login.html")
    return FileResponse(STATIC_DIR / "board.html")


@router.get("/login", include_in_schema=False)
def board_login_page(request: Request):
    """The PIN entry screen (redirect straight in if already unlocked)."""
    if _authed(request):
        return RedirectResponse(url="/board/", status_code=302)
    return FileResponse(STATIC_DIR / "board_login.html")


@router.post("/login", include_in_schema=False)
def board_login_submit(body: _PinIn):
    """Check the PIN; on success set the remember-me cookie."""
    if _pin_enabled() and body.pin.strip() == settings.BOARD_PIN:
        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            _COOKIE, _token(),
            max_age=60 * 60 * 24 * 365,  # remember this device for a year
            httponly=True, samesite="lax",
        )
        return resp
    return JSONResponse(status_code=401, content={"ok": False})


@router.get("/config")
def board_config(request: Request):
    """Runtime config the browser needs (nothing secret here)."""
    if not _authed(request):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return {
        "storeName": settings.BOARD_STORE_NAME,
        "pollSeconds": settings.BOARD_POLL_SECONDS,
        "staleSeconds": settings.BOARD_STALE_SECONDS,
        "devMode": settings.BOARD_DEV_MODE and not settings.board_ghl_enabled,
    }


@router.get("/feed")
def board_feed(request: Request):
    """Return the current board data.

    Dev mode returns generated mock data. Otherwise the configured upstream
    feed is fetched server-side and passed straight through. On any upstream
    failure we return HTTP 502 with a small error body — the frontend treats
    that as a failed poll (and, after ``BOARD_STALE_SECONDS``, shows the
    "connection lost" indicator) rather than blanking the screen.

    Priority: direct GoHighLevel (no n8n) > dev/mock > proxied BOARD_FEED_URL.
    """
    if not _authed(request):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

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
