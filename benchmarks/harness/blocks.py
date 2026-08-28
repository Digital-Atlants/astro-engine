"""Rising-sign blocks: the stage-2 search space.

Stage 1 of the shipped product narrows the birth time to a rising-sign block by
asking the client questions. Everything in this task is about resolving *inside*
that block, so every measurement here is restricted to the contiguous run of
candidate minutes whose Ascendant falls in the same sign as the Ascendant at the
known birth time.
"""

from __future__ import annotations

import datetime as dt

from astro_engine import core

from . import protocol


def ascendant_by_minute(case: dict, house_system: str = "whole_sign") -> dict[int, float]:
    place = case["place"]
    birth = dt.date.fromisoformat(case["birth_date"])
    out = {}
    for minute in protocol.GRID_MINUTES:
        hh, mm = divmod(minute, 60)
        jd = core.to_julian_day(
            core.localize_to_utc(
                dt.datetime(birth.year, birth.month, birth.day, hh, mm), place["tz"]
            )
        )
        _, asc, _ = core.houses_and_angles(jd, place["lat"], place["lon"], house_system)
        out[minute] = asc
    return out


def sign_by_minute(case: dict) -> dict[int, str]:
    return {m: core.sign_of(a) for m, a in ascendant_by_minute(case).items()}


def true_ascendant_sign(case: dict) -> str:
    place = case["place"]
    birth = dt.date.fromisoformat(case["birth_date"])
    hh, mm = map(int, case["known_time"].split(":"))
    jd = core.to_julian_day(
        core.localize_to_utc(
            dt.datetime(birth.year, birth.month, birth.day, hh, mm), place["tz"]
        )
    )
    _, asc, _ = core.houses_and_angles(jd, place["lat"], place["lon"], "whole_sign")
    return core.sign_of(asc)


def correct_block_minutes(case: dict) -> list[int]:
    """The contiguous run of grid minutes sharing the true rising sign.

    Contiguous, not merely same-signed: a sign can recur at the far end of the
    day, and that far run is a different block a client would never be in.
    The run containing the known time is the one returned.
    """
    signs = sign_by_minute(case)
    target = true_ascendant_sign(case)
    known = case_known_minute(case)
    anchor = min(
        protocol.GRID_MINUTES,
        key=lambda m: protocol.circular_error_minutes(m, known),
    )
    if signs[anchor] != target:
        # The known time sits within a step of a cusp and its nearest grid
        # point fell the other side of it. Walk to the nearest matching point.
        anchor = min(
            (m for m in protocol.GRID_MINUTES if signs[m] == target),
            key=lambda m: protocol.circular_error_minutes(m, known),
        )

    grid = protocol.GRID_MINUTES
    n = len(grid)
    i = grid.index(anchor)
    lo = i
    while signs[grid[(lo - 1) % n]] == target and (lo - 1) % n != i:
        lo = (lo - 1) % n
    hi = i
    while signs[grid[(hi + 1) % n]] == target and (hi + 1) % n != i:
        hi = (hi + 1) % n

    out, j = [], lo
    while True:
        out.append(grid[j])
        if j == hi:
            break
        j = (j + 1) % n
    return out


def case_known_minute(case: dict) -> int:
    hh, mm = map(int, case["known_time"].split(":"))
    return hh * 60 + mm


def block_width_minutes(case: dict) -> int:
    return len(correct_block_minutes(case)) * protocol.STEP_MINUTES


def best_in_block(scores: dict[int, float], block: list[int]) -> int:
    """Argmax restricted to the block. Ties break to the earliest minute,
    matching the shipped engine's tie-break so the two are comparable."""
    return max(block, key=lambda m: (scores.get(m, 0.0), -m))


def error_in_block(scores: dict[int, float], case: dict) -> int:
    block = correct_block_minutes(case)
    return protocol.circular_error_minutes(
        best_in_block(scores, block), case_known_minute(case)
    )
