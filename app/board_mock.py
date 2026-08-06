"""Seeded, self-aging mock feed for the Lead & Floor Board.

This exists so you can point the board at nothing and still watch cards move
through every urgency state — including an appointment sliding from "prep" to
"arriving" to a red "NO SHOW — CALL" — before an n8n workflow is connected.

How it stays lively without a database:

* Count-up slots (inquiries, floor): a customer arrives fresh, ages through
  amber/orange/red, then that id disappears (fades out, as if resolved) and a
  new id arrives in its place (slides in).
* Countdown slots (appointments): an appointment appears far in the future and
  counts down through neutral -> blue (prep) -> green (arriving) -> amber
  (late?) -> red (no-show), then recycles to a fresh future appointment.
* Slots are phase-staggered so at any instant the board shows the full spread
  of states, not one synchronized wave.

The output matches the documented feed shape exactly (inquiries / appointments
/ floor / generatedAt), plus an optional ``stats`` block the board uses for the
"today's total inquiries" counter. The n8n workflow is what decides, from the
GoHighLevel pipeline stage, which array a record lands in — this mock just
imitates a plausible mix.
"""
from __future__ import annotations

import datetime as dt

# Anchor the whole simulation to import time so ages/countdowns advance in real
# wall-clock time across successive polls (rather than resetting each request).
_ANCHOR = dt.datetime.now(dt.timezone.utc)

_INQUIRY_NAMES = [
    "Sarah M.", "David R.", "Priya K.", "Marcus T.", "Emily W.",
    "Jordan P.", "Aisha B.", "Tyler G.", "Nina L.", "Omar F.",
    "Grace H.", "Leo V.",
]
_INQUIRY_SOURCES = ["Web Form", "Facebook", "Google", "Phone", "Walk-in"]
_REPS = ["Jenna", "Marcus", "Sophia", "Dana", None]  # None => UNASSIGNED

_APPT_NAMES = [
    "Chen Family", "The Bakers", "Ramirez Family", "Ms. Whitfield",
    "The Okafors", "Patel Family", "Jordan & Kim", "The Nguyens",
]
_INTERESTS = [
    "Cavapoo - Pepper", "Goldendoodle - Biscuit", "Mini Bernedoodle - Bear",
    "Maltipoo - Coconut", "Pomsky - Luna", "Frenchie - Pickle",
    "Yorkie - Mango", "Cavapoo - Waffles",
]
_ASSOCIATES = ["Kayla", "Ben", "Rosa", "Marcus", None]

_PARTY_NAMES = [
    "Rodriguez", "Chen", "Patel", "Johnson", "Nguyen",
    "Williams", "Garcia", "Kim", "Brooks", "Adams",
]
_FLOOR_ASSOC = ["Kayla", "Ben", "Rosa", None, None]  # None => NEEDS GREETER


def _iso(now: dt.datetime, age_seconds: float) -> str:
    ts = now - dt.timedelta(seconds=age_seconds)
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_at(ts: dt.datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cycle(cycle_len: int, phase: int, elapsed: float):
    """Return (cycle_index, position_seconds) for a recycling slot."""
    t = elapsed + phase
    return int(t // cycle_len), t % cycle_len


def generate_mock_feed(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    elapsed = (now - _ANCHOR).total_seconds()

    # --- Inquiries (count-up) -----------------------------------------------
    # Cycle a touch over the 30-min red threshold; phases seed every color.
    inquiry_slots = [
        (38 * 60, 0),          # fresh (calm green)
        (40 * 60, 9 * 60),     # ~9 min (amber)
        (42 * 60, 20 * 60),    # ~20 min (orange)
        (44 * 60, 33 * 60),    # ~33 min (red, pulsing)
        (36 * 60, 3 * 60),     # ~3 min (calm green)
    ]
    inquiries = []
    for i, (cycle_len, phase) in enumerate(inquiry_slots):
        cyc, age = _cycle(cycle_len, phase, elapsed)
        pick = i + cyc
        inquiries.append(
            {
                "id": f"inq-{i}-{cyc}",
                "name": _INQUIRY_NAMES[pick % len(_INQUIRY_NAMES)],
                "source": _INQUIRY_SOURCES[pick % len(_INQUIRY_SOURCES)],
                "receivedAt": _iso(now, age),
                "assignedTo": _REPS[pick % len(_REPS)],
                "attempts": min(4, int(age // (7 * 60))),
            }
        )

    # --- Appointments (countdown) -------------------------------------------
    # Each slot recycles on a long cycle. Within a cycle the appointment occurs
    # APPT_POS seconds in; before that we're counting down (far-out -> arriving),
    # after that we're late -> no-show, then it recycles to a fresh future appt.
    C = 200 * 60          # full cycle length
    APPT_POS = 160 * 60   # appointment happens 160 min into the cycle
    # phase = where each slot sits in its cycle at t=0 (seeds each state).
    appt_slots = [
        # (phase_seconds, confirmed)
        (10 * 60, True),    # remaining ~150 min -> neutral / dim
        (120 * 60, True),   # remaining ~40 min  -> blue "prep"
        (152 * 60, True),   # remaining ~8 min   -> green "arriving"
        (173 * 60, False),  # ~13 min late       -> amber "late?" (also UNCONFIRMED)
        (185 * 60, True),   # ~25 min late       -> red "NO SHOW — CALL"
    ]
    appointments = []
    for i, (phase, confirmed) in enumerate(appt_slots):
        cyc, pos = _cycle(C, phase, elapsed)
        pick = i + cyc
        remaining = APPT_POS - pos  # seconds until appointment (negative => late)
        appt_at = now + dt.timedelta(seconds=remaining)
        appointments.append(
            {
                "id": f"appt-{i}-{cyc}",
                "name": _APPT_NAMES[pick % len(_APPT_NAMES)],
                "appointmentAt": _iso_at(appt_at),
                "interest": _INTERESTS[pick % len(_INTERESTS)],
                "assignedTo": _ASSOCIATES[pick % len(_ASSOCIATES)],
                "confirmed": confirmed,
                "arrived": False,
            }
        )

    # A couple of appointments for tomorrow so the "Tomorrow: N" header chip has
    # something to show. These are never rendered as cards (only today's are).
    tomorrow = (now + dt.timedelta(days=1)).replace(
        hour=14, minute=30, second=0, microsecond=0
    )
    for k, hour in enumerate((14, 16)):  # 2:30-ish and 4:30-ish tomorrow
        appointments.append(
            {
                "id": f"appt-tom-{k}",
                "name": _APPT_NAMES[(k + 3) % len(_APPT_NAMES)],
                "appointmentAt": _iso_at(tomorrow.replace(hour=hour)),
                "interest": _INTERESTS[(k + 2) % len(_INTERESTS)],
                "assignedTo": _ASSOCIATES[k % len(_ASSOCIATES)],
                "confirmed": bool(k % 2),
                "arrived": False,
            }
        )

    # --- Floor (count-up) ----------------------------------------------------
    floor_slots = [
        (48 * 60, 2 * 60),     # ~2 min (neutral)
        (50 * 60, 14 * 60),    # ~14 min (amber - check in)
        (52 * 60, 27 * 60),    # ~27 min (orange - needs attention)
        (54 * 60, 43 * 60),    # ~43 min (red, pulsing)
    ]
    floor = []
    for i, (cycle_len, phase) in enumerate(floor_slots):
        cyc, age = _cycle(cycle_len, phase, elapsed)
        pick = i + cyc
        floor.append(
            {
                "id": f"flr-{i}-{cyc}",
                "party": _PARTY_NAMES[pick % len(_PARTY_NAMES)],
                "headcount": 1 + (pick * 2 + i) % 5,
                "checkedInAt": _iso(now, age),
                "interest": _INTERESTS[pick % len(_INTERESTS)],
                "assignedTo": _FLOOR_ASSOC[pick % len(_FLOOR_ASSOC)],
            }
        )

    # --- Daily total for the header stat ------------------------------------
    resolved = sum(int((elapsed + phase) // cycle_len)
                   for cycle_len, phase in inquiry_slots)
    inquiries_today = 18 + resolved + len(inquiries)

    return {
        "inquiries": inquiries,
        "appointments": appointments,
        "floor": floor,
        "generatedAt": _iso_at(now),
        "stats": {"inquiriesToday": inquiries_today},
    }
