"""Arm E: constant-guess baselines.

Arm C asks whether an engine beats itself on random dates. Arm E asks a
blunter question: does it beat a scorer that does not look at the events, the
chart, or the case at all - one that returns the same clock time every time?

Two constants are run:

* **noon** - a fixed 12:00, chosen before looking at the corpus.
* **corpus median** - the median of the twelve known birth times. This one is
  fitted to the answers it is scored against, so it is an *oracle* baseline
  and not a strategy any engine could use in production. It is here as an
  upper bound on what a constant can achieve on this corpus, and any arm that
  fails to beat it has not demonstrated it is reading the events.
"""

from __future__ import annotations

import statistics
import time

from . import protocol

NOON_MINUTE = 12 * 60


def corpus_median_minute(cases: list[dict]) -> int:
    """Median known birth time, snapped to the candidate grid.

    A plain linear median of minutes-past-midnight, not a circular one. The
    corpus has no cluster straddling midnight, so the two agree here; the
    linear form is used because it is the one a reader will reproduce by hand.
    """
    minutes = sorted(
        int(c["known_time"].split(":")[0]) * 60 + int(c["known_time"].split(":")[1])
        for c in cases
    )
    median = statistics.median(minutes)
    snapped = round(median / protocol.STEP_MINUTES) * protocol.STEP_MINUTES
    return int(snapped) % 1440


def run(case: dict, constant_minute: int) -> dict:
    """One Arm-E 'run'. Ignores the case entirely, which is the point."""
    t0 = time.perf_counter()
    time_str = protocol.minute_to_time(constant_minute)
    return {
        "engine": "constant",
        "returned_time": time_str,
        "returned_minute": constant_minute % 1440,
        "peak_score": None,
        "mean_score": None,
        # A constant has no score distribution, so peak/mean and the true-time
        # percentile are undefined rather than zero. They are left out of the
        # signal-versus-null tables for that reason.
        "peak_over_mean": None,
        "own_confidence": {},
        "candidate_count": 0,
        "wall_ms": (time.perf_counter() - t0) * 1000.0,
        "score_by_minute": {},
    }
