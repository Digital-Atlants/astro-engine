"""Ascendant-speed profile, and whether returned times track it.

A slow-moving Ascendant means many consecutive candidate times share nearly the
same angles, so any scorer that rewards planets aspecting the angles has more
chances to score in those hours. That is a property of the grid, not of the
subject's life, which is why the returned-hour histogram has to be read against
this profile rather than against a flat 1/24 expectation.
"""

from __future__ import annotations

import datetime as dt

from astro_engine import core

from . import protocol


def ascendant_speed_by_minute(case: dict) -> dict[int, float]:
    """Degrees of Ascendant travelled per protocol step, keyed by grid minute."""
    place = case["place"]
    birth = dt.date.fromisoformat(case["birth_date"])
    asc_at = {}
    for minute in protocol.GRID_MINUTES:
        hh, mm = divmod(minute, 60)
        jd = core.to_julian_day(
            core.localize_to_utc(dt.datetime(birth.year, birth.month, birth.day, hh, mm), place["tz"])
        )
        _, asc, _ = core.houses_and_angles(jd, place["lat"], place["lon"], "whole_sign")
        asc_at[minute] = asc

    speeds = {}
    for i, minute in enumerate(protocol.GRID_MINUTES):
        nxt = protocol.GRID_MINUTES[(i + 1) % len(protocol.GRID_MINUTES)]
        speeds[minute] = core.angle_diff(asc_at[nxt], asc_at[minute])
    return speeds


def hour_speed_profile(case: dict) -> dict[int, float]:
    """Mean Ascendant degrees per step, aggregated to the 24 clock hours."""
    speeds = ascendant_speed_by_minute(case)
    per_hour: dict[int, list[float]] = {h: [] for h in range(24)}
    for minute, speed in speeds.items():
        per_hour[minute // 60].append(speed)
    return {h: sum(v) / len(v) for h, v in per_hour.items()}


def slowest_hours(case: dict, count: int = 8) -> set[int]:
    profile = hour_speed_profile(case)
    return set(sorted(profile, key=profile.__getitem__)[:count])


def bias_report(records: list[dict], cases_by_id: dict[str, dict], count: int = 8) -> dict:
    """Share of returned times landing in each case's slowest Ascendant hours.

    Uniform expectation is count/24. A share well above that is the scorer
    following the grid rather than the events.
    """
    cache: dict[str, set[int]] = {}
    in_slow = 0
    for r in records:
        case = cases_by_id[r["case_id"]]
        slow = cache.setdefault(r["case_id"], slowest_hours(case, count))
        if r["returned_minute"] // 60 in slow:
            in_slow += 1
    n = len(records)
    return {
        "n": n,
        "slow_hours_per_case": count,
        "in_slowest_hours": in_slow,
        "observed_share": in_slow / n if n else None,
        "uniform_expectation": count / 24,
    }
