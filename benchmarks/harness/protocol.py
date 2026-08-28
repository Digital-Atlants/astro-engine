"""The one protocol every arm runs.

Window, step and event set are identical across Arm A, Arm B and Arm C.
Changing any of these for one arm only invalidates the comparison, so they
live here as module constants rather than as per-arm arguments.
"""

from __future__ import annotations

import datetime as dt
import random

WINDOW_START = "00:00"
WINDOW_END = "23:59"
STEP_MINUTES = 4
GRID_MINUTES = list(range(0, 24 * 60, STEP_MINUTES))

# The vendor caps a search at 720 minutes, so a full day is two requests.
# Both anchors are fixed for every case and every arm, so nothing about the
# known birth time leaks into the request.
VENDOR_HALVES = (
    {"label": "am", "anchor_hour": 6, "delta_minutes": 360},
    {"label": "pm", "anchor_hour": 18, "delta_minutes": 360},
)

NULL_SHUFFLES_ARM_A = 5


def circular_error_minutes(a_minute: int, b_minute: int) -> int:
    """Absolute distance on the 24-hour clock, in minutes."""
    d = abs(a_minute - b_minute) % 1440
    return min(d, 1440 - d)


def time_to_minute(hhmm: str) -> int:
    hh, mm = map(int, hhmm.split(":")[:2])
    return (hh * 60 + mm) % 1440  # the vendor emits "24:00" for the pm endpoint


def minute_to_time(minute: int) -> str:
    hh, mm = divmod(minute % 1440, 60)
    return f"{hh:02d}:{mm:02d}"


def known_time_on_grid(known_minute: int) -> bool:
    return known_minute % STEP_MINUTES == 0


def grid_floor_error(known_minute: int) -> int:
    """Best |err| any engine on this grid could achieve for this known time."""
    return min(circular_error_minutes(known_minute, m) for m in GRID_MINUTES)


def shuffled_events(events: list[dict], lo: dt.date, hi: dt.date, seed: int) -> list[dict]:
    """Arm C: same count, same category mix, dates redrawn uniformly.

    Only `date` changes. `date_precision`, `type` and the event count are held
    fixed so the null differs from the real run in exactly one respect.
    """
    rng = random.Random(seed)
    span = (hi - lo).days
    out = []
    for e in events:
        drawn = lo + dt.timedelta(days=rng.randint(0, max(span, 1)))
        if e["date_precision"] == "month":
            drawn = drawn.replace(day=1)
        elif e["date_precision"] == "year":
            drawn = drawn.replace(month=1, day=1)
        out.append({**e, "date": drawn.isoformat()})
    return out
