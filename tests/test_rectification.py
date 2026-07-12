"""Rectification behavior: known-case recovery and performance smoke."""

import datetime as dt
import time

import swisseph as swe

from astro_engine import core
from astro_engine.core import to_julian_day

PLACE = {"lat": 52.52, "lon": 13.405, "tz": "Europe/Berlin"}
BIRTH_DATE = dt.date(1988, 4, 10)
TRUE_TIME = "14:30"


def _asc_at(time_str: str) -> float:
    hh, mm = map(int, time_str.split(":"))
    when = core.localize_to_utc(
        dt.datetime(BIRTH_DATE.year, BIRTH_DATE.month, BIRTH_DATE.day, hh, mm),
        PLACE["tz"],
    )
    _, asc, _ = core.houses_and_angles(
        to_julian_day(when), PLACE["lat"], PLACE["lon"], "whole_sign"
    )
    return asc


def _find_aspect_date(planet: int, target_deg: float, aspect_deg: float) -> dt.date:
    """Scan 1995-2026 for the date the planet hits target_deg + aspect_deg."""
    goal = (target_deg + aspect_deg) % 360.0
    best_date, best_orb = None, 999.0
    day = dt.date(1995, 1, 1)
    while day < dt.date(2026, 1, 1):
        jd = to_julian_day(dt.datetime(day.year, day.month, day.day, 12, 0))
        lon, _ = core.planet_position(jd, planet)
        orb = core.angle_diff(lon, goal)
        if orb < best_orb:
            best_orb, best_date = orb, day
        day += dt.timedelta(days=1)
    assert best_orb < 0.3, "no transit hit found in scan range"
    return best_date


def test_known_case_true_time_within_residual_window(client, auth_headers):
    asc = _asc_at(TRUE_TIME)
    # Three independent event dates, each anchored to the true-time Asc:
    # their hits stack only at the true time, drowning out stray exact
    # aspects elsewhere in the window.
    event_dates = [
        _find_aspect_date(swe.SATURN, asc, 0.0),
        _find_aspect_date(swe.SATURN, asc, 180.0),
        _find_aspect_date(swe.JUPITER, asc, 0.0),
    ]
    body = {
        "birth_date": BIRTH_DATE.isoformat(),
        "place": PLACE,
        "candidate_window": {
            "start_time": "13:30",
            "end_time": "15:30",
            "step_minutes": 4,
        },
        "events": [
            {
                "id": f"e{i}",
                "date": d.isoformat(),
                "date_precision": "day",
                "type": "other",
                "weight": 1.0,
            }
            for i, d in enumerate(event_dates)
        ],
        "config": {
            "house_system": "whole_sign",
            "techniques": ["transits_to_angles"],
        },
    }
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()
    best = result["suggested_best"]
    assert best["score"] > 0

    def to_min(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m

    margin = best["residual_window_minutes"] + 4  # + one step of quantization
    assert abs(to_min(best["time"]) - to_min(TRUE_TIME)) <= max(margin, 8)


def test_performance_360_candidates_5_events(client, auth_headers):
    body = {
        "birth_date": "1990-07-01",
        "place": PLACE,
        "candidate_window": {
            "start_time": "00:00",
            "end_time": "23:59",
            "step_minutes": 4,
        },
        "events": [
            {"id": f"e{i}", "date": d, "date_precision": "day", "type": t, "weight": 1.0}
            for i, (d, t) in enumerate(
                [
                    ("2010-05-01", "marriage"),
                    ("2013-09-15", "relocation"),
                    ("2016-02-20", "career_break"),
                    ("2019-11-11", "child_birth"),
                    ("2022-06-30", "other"),
                ]
            )
        ],
        "config": {"house_system": "whole_sign"},
    }
    t0 = time.perf_counter()
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    result = resp.json()
    assert len(result["candidates"]) == 360
    assert elapsed < 10.0, f"rectification took {elapsed:.1f}s"
    assert result["compute_ms"] >= 0


def test_config_echo_and_hit_shape(client, auth_headers):
    body = {
        "birth_date": "1990-07-01",
        "place": PLACE,
        "candidate_window": {"start_time": "10:00", "end_time": "11:00", "step_minutes": 15},
        "events": [
            {"id": "e1", "date": "2015-01-01", "date_precision": "year", "type": "marriage", "weight": 2.0}
        ],
        "config": {"house_system": "placidus", "plateau_ratio": 0.8},
    }
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()
    assert result["config_echo"]["plateau_ratio"] == 0.8
    for cand in result["candidates"]:
        for hit in cand["hits"]:
            assert set(hit) == {"event_id", "technique", "factor", "orb_deg", "score"}
