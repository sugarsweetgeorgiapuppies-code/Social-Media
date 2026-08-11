"""Direct GoHighLevel feed builder for the Lead & Appointment Board.

This lets the board's own backend fetch from GoHighLevel and assemble the feed,
so the browser polls this local server instead of an n8n webhook. That means
n8n runs ZERO executions for the board (important on metered n8n plans).

The GoHighLevel Private Integration token lives only in this server's
environment (never in the browser). Configure via:
    BOARD_GHL_TOKEN,  BOARD_GHL_LOCATION_ID,  BOARD_GHL_CALENDAR_ID

This mirrors what the reference n8n workflow (n8n/board-feed.ghl.json) did:
pipelines + opportunities + users + calendar events -> the board feed shape.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from .config import settings
from .logging_config import get_logger

log = get_logger(__name__)

_API = "https://services.leadconnectorhq.com"
_HEADERS = {"Version": "2021-07-28", "Accept": "application/json"}

# Small in-process cache so rapid polls / multiple tabs don't multiply API calls.
_cache: dict = {"at": 0.0, "data": None}

# "Inquiries Today" must be a true daily total that only ever climbs from
# midnight (store time) until midnight the next day. We can't recompute it
# fresh each poll from a single search call: GoHighLevel returns opportunities
# in recently-updated order capped at a page size, so a lead created earlier
# today can slip out of that window and the count would drop, then reappear.
# Instead we remember every lead id we've seen created today and count the set
# — it grows as new leads arrive and resets when the date rolls over.
_daily = {"date": None, "ids": set()}


def _get(path: str, params: dict) -> dict:
    url = f"{_API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        **_HEADERS,
        "Authorization": f"Bearer {settings.BOARD_GHL_TOKEN}",
        "User-Agent": "lead-floor-board/1.0",
    })
    with urllib.request.urlopen(req, timeout=settings.BOARD_FEED_TIMEOUT) as resp:
        return json.loads(resp.read())


def _short_name(full: str | None) -> str:
    parts = (full or "").strip().split()
    if not parts:
        return "Lead"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def _iso(value) -> str:
    """Pass through an ISO string, or convert epoch ms -> ISO."""
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).isoformat()
    return str(value or "")


def _parse_dt(value) -> dt.datetime | None:
    """Parse an ISO string or epoch ms into an aware datetime, or None."""
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc)
    try:
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def build_feed() -> dict:
    """Assemble the board feed from live GoHighLevel data (cached briefly)."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < settings.BOARD_GHL_CACHE_SECONDS:
        return _cache["data"]

    loc = settings.BOARD_GHL_LOCATION_ID

    # --- Pipeline + stage names ---------------------------------------------
    pipelines = _get("/opportunities/pipelines", {"locationId": loc}).get("pipelines", [])
    want = settings.BOARD_GHL_PIPELINE.lower()
    gi = next((p for p in pipelines if want in (p.get("name") or "").lower()),
              pipelines[0] if pipelines else {"id": None, "stages": []})
    stage_name = {s.get("id"): (s.get("name") or "").lower() for s in gi.get("stages", [])}

    # --- Users (id -> display name) -----------------------------------------
    name_by_user: dict = {}
    try:
        for u in _get("/users/", {"locationId": loc}).get("users", []):
            nm = (u.get("name") or " ".join(
                x for x in [u.get("firstName"), u.get("lastName")] if x)).strip()
            if nm:
                name_by_user[u.get("id")] = nm
    except Exception as exc:  # users are a nicety; don't fail the whole feed
        log.warning("GHL users fetch failed: %s", exc)

    # --- New Inquiries (General Inquiry pipeline, not Appointment Booked) ----
    # status=all so leads already handled today (won/lost/booked) still count
    # toward the daily total, which should only ever climb. Fall back if the
    # API doesn't accept the param.
    try:
        opp_resp = _get("/opportunities/search",
                        {"location_id": loc, "limit": 100, "status": "all"})
    except Exception:
        opp_resp = _get("/opportunities/search", {"location_id": loc, "limit": 100})
    try:
        tz = ZoneInfo(settings.TIMEZONE)
    except Exception:
        tz = dt.timezone.utc
    today = dt.datetime.now(tz).date()

    # Roll the daily counter over at midnight (store time), then only ever add.
    if _daily["date"] != today:
        _daily["date"] = today
        _daily["ids"] = set()

    inquiries = []
    for o in opp_resp.get("opportunities", []):
        if o.get("pipelineId") != gi.get("id"):
            continue
        created = _parse_dt(o.get("createdAt"))
        if created and created.astimezone(tz).date() == today and o.get("id"):
            # Seen once today => counted for the rest of the day. Because this is
            # a set of ids, it never double-counts and never decreases, even if a
            # lead drops out of a later search window.
            _daily["ids"].add(o.get("id"))
        # The board only lists leads still awaiting a call: open, pre-appointment.
        if "appointment" in stage_name.get(o.get("pipelineStageId"), ""):
            continue
        if (o.get("status") or "open") != "open":
            continue
        contact = o.get("contact") or {}
        assigned = o.get("assignedTo")
        inquiries.append({
            "id": o.get("id"),
            "name": _short_name(contact.get("name") or o.get("name")),
            "source": o.get("source") or "",
            "receivedAt": _iso(o.get("createdAt")),
            "assignedTo": (name_by_user.get(assigned, "Assigned") if assigned else None),
            "attempts": 0,
        })

    # --- Appointments (calendar events, today + tomorrow window) ------------
    appointments = []
    if settings.BOARD_GHL_CALENDAR_ID:
        try:
            now_dt = dt.datetime.now(dt.timezone.utc)
            start_ms = int((now_dt - dt.timedelta(hours=24)).timestamp() * 1000)
            end_ms = int((now_dt + dt.timedelta(hours=48)).timestamp() * 1000)
            events = _get("/calendars/events", {
                "locationId": loc,
                "calendarId": settings.BOARD_GHL_CALENDAR_ID,
                "startTime": start_ms,
                "endTime": end_ms,
            }).get("events", [])
            for e in events:
                st = (e.get("appointmentStatus") or "").lower()
                if st in ("cancelled", "invalid"):
                    continue
                contact = e.get("contact") or {}
                assigned = e.get("assignedUserId")
                appointments.append({
                    "id": e.get("id"),
                    "name": _short_name(e.get("contactName") or contact.get("name") or e.get("title")),
                    "appointmentAt": _iso(e.get("startTime")),
                    "interest": "",
                    "assignedTo": (name_by_user.get(assigned, "Assigned") if assigned else None),
                    "confirmed": st == "confirmed",
                    "arrived": st == "showed",
                })
        except Exception as exc:
            log.warning("GHL calendar fetch failed: %s", exc)

    feed = {
        "inquiries": inquiries,
        "appointments": appointments,
        "floor": [],
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"),
        "stats": {"inquiriesToday": len(_daily["ids"])},
    }
    _cache["at"] = now
    _cache["data"] = feed
    return feed
