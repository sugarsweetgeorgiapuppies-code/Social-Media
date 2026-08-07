"""Tests for the Lead & Floor Board feed + endpoints.

Runs without an API key or database. Verifies:
  * the mock feed matches the documented shape (inquiries/appointments/floor),
  * the seeded data spans every urgency color band the display renders,
  * the /board endpoints (page, config, feed) respond.

Run with:  python -m pytest tests/test_board.py -q
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("DAILY_RUN_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.board_mock import generate_mock_feed  # noqa: E402

UTC = dt.timezone.utc


def test_feed_shape():
    feed = generate_mock_feed()
    for key in ("inquiries", "appointments", "floor", "generatedAt"):
        assert key in feed, f"feed missing '{key}'"

    inq = feed["inquiries"][0]
    for key in ("id", "name", "source", "receivedAt", "assignedTo", "attempts"):
        assert key in inq

    appt = feed["appointments"][0]
    for key in ("id", "name", "appointmentAt", "interest", "assignedTo",
                "confirmed", "arrived"):
        assert key in appt

    flr = feed["floor"][0]
    for key in ("id", "party", "headcount", "checkedInAt", "interest", "assignedTo"):
        assert key in flr


def _inquiry_level(age_min: float) -> str:
    if age_min < 5:
        return "calm"
    if age_min < 15:
        return "amber"
    if age_min < 30:
        return "orange"
    return "red"


def _appt_level(remaining_min: float) -> str:
    if remaining_min > 60:
        return "neutral"
    if remaining_min > 15:
        return "blue"
    if -remaining_min < 10:
        return "green"
    if -remaining_min < 20:
        return "amber"
    return "red"


def test_seed_spans_every_color():
    """The seeded feed should demo every color band at t=0, including a no-show."""
    now = dt.datetime.now(UTC)
    feed = generate_mock_feed(now)

    inq_levels = set()
    for i in feed["inquiries"]:
        age = (now - dt.datetime.fromisoformat(i["receivedAt"].replace("Z", "+00:00"))).total_seconds() / 60
        inq_levels.add(_inquiry_level(age))
    assert {"calm", "amber", "orange", "red"} <= inq_levels

    appt_levels = set()
    for a in feed["appointments"]:
        appt_at = dt.datetime.fromisoformat(a["appointmentAt"].replace("Z", "+00:00"))
        remaining = (appt_at - now).total_seconds() / 60
        # only "today-ish" appointments count toward the on-board states
        if -60 < remaining < 24 * 60:
            appt_levels.add(_appt_level(remaining))
    assert {"neutral", "blue", "green", "amber", "red"} <= appt_levels

    # at least one appointment is unconfirmed (persistent outline demo)
    assert any(not a["confirmed"] for a in feed["appointments"])


def test_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    r = client.get("/board/config")
    assert r.status_code == 200
    cfg = r.json()
    assert "storeName" in cfg and "pollSeconds" in cfg and "staleSeconds" in cfg

    r = client.get("/board/feed")
    assert r.status_code == 200
    data = r.json()
    assert data["inquiries"] and data["appointments"] and data["floor"]

    r = client.get("/board/")
    assert r.status_code == 200
    assert "New Inquiries" in r.text  # the board page


if __name__ == "__main__":
    test_feed_shape()
    test_seed_spans_every_color()
    test_endpoints()
    print("ALL BOARD CHECKS PASSED ✅")
