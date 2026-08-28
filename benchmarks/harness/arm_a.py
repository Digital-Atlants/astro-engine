"""Arm A: our engine, current main, engine defaults, in-process.

`RectificationConfig()` is constructed with no arguments on purpose: the web
client sends no `config`, so engine defaults are what ships and what must be
measured. Nothing here reaches into `astro_engine` to change behaviour.
"""

from __future__ import annotations

import statistics
import time

from astro_engine.rectification import score_rectification
from astro_engine.schemas import (
    CandidateWindow,
    Place,
    RectificationConfig,
    RectificationEvent,
    RectificationRequest,
)

from . import protocol


def build_request(case: dict, events: list[dict]) -> RectificationRequest:
    return RectificationRequest(
        birth_date=case["birth_date"],
        place=Place(
            lat=case["place"]["lat"],
            lon=case["place"]["lon"],
            tz=case["place"]["tz"],
        ),
        candidate_window=CandidateWindow(
            start_time=protocol.WINDOW_START,
            end_time=protocol.WINDOW_END,
            step_minutes=protocol.STEP_MINUTES,
        ),
        events=[
            RectificationEvent(
                id=e["id"],
                date=e["date"],
                date_precision=e["date_precision"],
                type=e["type"],
            )
            for e in events
        ],
        config=RectificationConfig(),
    )


def run(case: dict, events: list[dict]) -> dict:
    """One Arm-A run. Returns the measurement record for one (case, event set)."""
    req = build_request(case, events)
    t0 = time.perf_counter()
    result = score_rectification(req)
    wall_ms = (time.perf_counter() - t0) * 1000.0

    scores = [c["total_score"] for c in result["candidates"]]
    peak = max(scores)
    mean = statistics.fmean(scores)
    best = result["suggested_best"]

    return {
        "engine": "ours",
        "returned_time": best["time"],
        "returned_minute": protocol.time_to_minute(best["time"]),
        "peak_score": peak,
        "mean_score": mean,
        "peak_over_mean": (peak / mean) if mean > 0 else None,
        "own_confidence": {
            "residual_window_minutes": best["residual_window_minutes"],
        },
        "candidate_count": len(scores),
        "wall_ms": wall_ms,
        "score_by_minute": {
            protocol.time_to_minute(c["time"]): c["total_score"]
            for c in result["candidates"]
        },
    }
