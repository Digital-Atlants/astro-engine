"""Rectification behaviour: corpus-backed accuracy, confidence, performance.

The accuracy test here used to generate its event dates from the answer's
Ascendant, search a two-hour window around the answer, and enable a single
technique. That is a self-fulfilling test: it validated the scorer against
data the scorer produced, so it passed regardless of whether the scorer
worked. It is replaced, not deleted, by a check against a real Rodden AA case
from `benchmarks/corpus/` with real dated life events and a full 24-hour
search.

The assertion is deliberately weak - it asserts the engine's *measured*
behaviour, not an aspiration. What the engine can actually do is documented in
`benchmarks/RESULTS_SUBSIGN.md`; this test's job is to fail if that regresses,
not to imply an accuracy the engine does not have.
"""

import datetime as dt
import json
import pathlib
import time

from astro_engine import core
from astro_engine.core import to_julian_day

PLACE = {"lat": 52.52, "lon": 13.405, "tz": "Europe/Berlin"}

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "benchmarks" / "corpus"


def _load_case(case_id: str) -> dict:
    for split in ("train", "holdout"):
        path = CORPUS / split / f"{case_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError(f"corpus case {case_id!r} not found")


def _minutes(time_str: str) -> int:
    hh, mm = map(int, time_str.split(":"))
    return hh * 60 + mm


def _circular_error(a: int, b: int) -> int:
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def _rising_sign_block(case: dict, step: int = 4) -> list[int]:
    """Grid minutes whose Ascendant shares the sign of the known birth time."""
    place = case["place"]
    birth = dt.date.fromisoformat(case["birth_date"])

    def asc_at(minute: int) -> float:
        hh, mm = divmod(minute, 60)
        jd = to_julian_day(
            core.localize_to_utc(
                dt.datetime(birth.year, birth.month, birth.day, hh, mm), place["tz"]
            )
        )
        _, asc, _ = core.houses_and_angles(jd, place["lat"], place["lon"], "whole_sign")
        return asc

    target = core.sign_of(asc_at(_minutes(case["known_time"])))
    return [m for m in range(0, 1440, step) if core.sign_of(asc_at(m)) == target]


def _body_for(case: dict, **config) -> dict:
    return {
        "birth_date": case["birth_date"],
        "place": {
            "lat": case["place"]["lat"],
            "lon": case["place"]["lon"],
            "tz": case["place"]["tz"],
        },
        "candidate_window": {
            "start_time": "00:00",
            "end_time": "23:59",
            "step_minutes": 4,
        },
        "events": [
            {
                "id": e["id"],
                "date": e["date"],
                "date_precision": e["date_precision"],
                "type": e["type"],
                "weight": 1.0,
            }
            for e in case["events"]
        ],
        "config": {"permutation_trials": 0, **config},
    }


def test_corpus_case_scores_and_returns_a_full_density_curve(client, auth_headers):
    case = _load_case("presley_elvis")
    resp = client.post(
        "/v1/rectification/score", json=_body_for(case), headers=auth_headers
    )
    assert resp.status_code == 200
    result = resp.json()

    assert len(result["candidates"]) == 360
    assert len(result["density"]) == 360
    assert result["suggested_best"]["score"] > 0
    for point in result["density"]:
        assert set(point) == {"time", "score", "excluded"}


def test_corpus_case_inside_the_correct_rising_sign_block(client, auth_headers):
    """Within the correct block, the peak lands near the known time.

    The 30-minute bound is the engine's measured behaviour on the corpus, not
    a product promise. `benchmarks/RESULTS_SUBSIGN.md` carries the real
    distribution.
    """
    case = _load_case("presley_elvis")
    resp = client.post(
        "/v1/rectification/score", json=_body_for(case), headers=auth_headers
    )
    assert resp.status_code == 200
    scores = {
        _minutes(c["time"]): c["total_score"] for c in resp.json()["candidates"]
    }
    block = _rising_sign_block(case)
    assert block, "corpus case has no rising-sign block on the grid"

    best = max(block, key=lambda m: (scores[m], -m))
    error = _circular_error(best, _minutes(case["known_time"]))
    assert error <= 30, f"in-block error {error} min exceeds the measured bound"


def test_ascendant_sign_marks_candidates_excluded_without_dropping_them(
    client, auth_headers
):
    case = _load_case("presley_elvis")
    body = _body_for(case)
    body["ascendant_sign"] = "sagittarius"
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()

    assert len(result["candidates"]) == 360, "excluded candidates must not be dropped"
    excluded = [c for c in result["candidates"] if c["excluded"]]
    kept = [c for c in result["candidates"] if not c["excluded"]]
    assert excluded and kept, "the filter should split the window"
    assert all(c["asc_sign"] == "sagittarius" for c in kept)
    if result["suggested_best"]["time"] is not None:
        chosen = next(
            c
            for c in result["candidates"]
            if c["time"] == result["suggested_best"]["time"]
        )
        assert not chosen["excluded"]


def test_confidence_refuses_when_the_peak_does_not_beat_shuffled_dates(
    client, auth_headers
):
    """The API must be able to answer 'cannot determine' instead of a time."""
    case = _load_case("presley_elvis")
    body = _body_for(case)
    body["config"]["permutation_trials"] = 8
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    assert resp.status_code == 200
    conf = resp.json()["confidence"]

    assert set(conf) >= {
        "refused",
        "reasons",
        "permutation_percentile",
        "permutation_trials",
        "separation",
    }
    assert conf["permutation_trials"] == 8
    assert 0.0 <= conf["permutation_percentile"] <= 1.0
    if conf["refused"]:
        assert conf["reasons"], "a refusal must say why"
        assert resp.json()["suggested_best"]["time"] is None


def test_permutation_null_is_deterministic(client, auth_headers):
    case = _load_case("presley_elvis")
    body = _body_for(case)
    body["config"]["permutation_trials"] = 6
    a = client.post("/v1/rectification/score", json=body, headers=auth_headers).json()
    b = client.post("/v1/rectification/score", json=body, headers=auth_headers).json()
    assert a["confidence"] == b["confidence"]


def test_house_system_does_not_affect_rectification_scoring(client, auth_headers):
    """Documents a known no-op rather than leaving it to be rediscovered.

    Every shipped technique reads only `asc` and `mc`, so the cusps are
    computed and never used and `config.house_system` cannot change a
    rectification score. The obvious fix - score the intermediate cusps - was
    built and measured as Work item 3.1: under whole-sign the cusps are
    *exactly* constant inside a rising-sign block (they are sign boundaries),
    so it is a mathematical no-op there, and under Placidus it doubled the
    held-out error. It was reverted. If a future change makes the house system
    matter, this test should fail and be replaced deliberately.
    """
    case = _load_case("presley_elvis")
    whole = client.post(
        "/v1/rectification/score",
        json=_body_for(case, house_system="whole_sign"),
        headers=auth_headers,
    ).json()
    placidus = client.post(
        "/v1/rectification/score",
        json=_body_for(case, house_system="placidus"),
        headers=auth_headers,
    ).json()
    assert [c["total_score"] for c in whole["candidates"]] == [
        c["total_score"] for c in placidus["candidates"]
    ]


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
        "config": {"house_system": "whole_sign", "permutation_trials": 0},
    }
    t0 = time.perf_counter()
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    result = resp.json()
    assert len(result["candidates"]) == 360
    assert elapsed < 10.0, f"rectification took {elapsed:.1f}s"
    assert result["compute_ms"] >= 0


def test_performance_with_permutation_null(client, auth_headers):
    """The permutation null multiplies the work by trials + 1. Guard the
    default so it cannot quietly grow past the documented budget."""
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
    }
    t0 = time.perf_counter()
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert resp.json()["confidence"]["permutation_trials"] == 12
    assert elapsed < 30.0, f"rectification with the null took {elapsed:.1f}s"


def test_config_echo_and_hit_shape(client, auth_headers):
    body = {
        "birth_date": "1990-07-01",
        "place": PLACE,
        "candidate_window": {"start_time": "10:00", "end_time": "11:00", "step_minutes": 15},
        "events": [
            {"id": "e1", "date": "2015-01-01", "date_precision": "year", "type": "marriage", "weight": 2.0}
        ],
        "config": {"house_system": "placidus", "plateau_ratio": 0.8, "permutation_trials": 0},
    }
    resp = client.post("/v1/rectification/score", json=body, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()
    assert result["config_echo"]["plateau_ratio"] == 0.8
    for cand in result["candidates"]:
        for hit in cand["hits"]:
            assert set(hit) == {"event_id", "technique", "factor", "orb_deg", "score"}
