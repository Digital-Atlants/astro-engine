"""Interview core: contract, reweighting invariants, tiers, calibration."""

import datetime as dt
import json
import pathlib
import time

import pytest

from astro_engine import interview

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "benchmarks" / "corpus"

PLACE = {"lat": 34.2576, "lon": -88.7034, "tz": "America/Chicago"}
BIRTH = "1935-01-08"


def _load_case(case_id: str) -> dict:
    for split in ("train", "holdout"):
        path = CORPUS / split / f"{case_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError(f"corpus case {case_id!r} not found")


def _body(answers=None, **config) -> dict:
    body = {"birth_date": BIRTH, "place": PLACE, "answers": answers or []}
    if config:
        body["config"] = config
    return body


# --------------------------------------------------------------------------
# The answer contract: enum ids only, no numeric decisions from the caller
# --------------------------------------------------------------------------


def test_answer_ids_must_be_enum_tokens(client, auth_headers):
    """A caller must not be able to smuggle a time, a number or a window
    through an answer field. Every numeric decision belongs to the engine."""
    for bad in ["09:08", "13:45:00", "minute 512", "SAGITTARIUS", "sign;drop"]:
        body = _body([
            {
                "question_id": "stage1_rising_sign",
                "channel": "rising_sign",
                "answer_ids": [bad],
            }
        ])
        resp = client.post("/v1/interview/step", json=body, headers=auth_headers)
        assert resp.status_code == 422, f"{bad!r} should be rejected"


def test_unknown_fields_are_rejected(client, auth_headers):
    """`extra: forbid` is what stops a documented birth time or a hand-picked
    candidate window arriving through a field nobody declared."""
    body = _body()
    body["documented_time"] = "04:35"
    resp = client.post("/v1/interview/step", json=body, headers=auth_headers)
    assert resp.status_code == 422

    body = _body()
    body["candidate_window"] = {"start_time": "04:00", "end_time": "05:00"}
    resp = client.post("/v1/interview/step", json=body, headers=auth_headers)
    assert resp.status_code == 422


def test_valid_enum_answer_is_accepted(client, auth_headers):
    body = _body([
        {
            "question_id": "stage1_rising_sign",
            "channel": "rising_sign",
            "answer_ids": ["sagittarius"],
        }
    ])
    resp = client.post("/v1/interview/step", json=body, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tier"] in (1, 2, 3, 4)


# --------------------------------------------------------------------------
# Reweighting invariants
# --------------------------------------------------------------------------


def test_reweighting_never_reaches_zero():
    """A wrong answer must degrade the truth, never delete it. Otherwise a
    single mistake makes the right answer unreachable for the rest of the
    interview."""
    weights = [1.0] * 10
    labels = ["a"] * 5 + ["b"] * 5
    out = interview.apply_answer(weights, labels, ["a"], 0.75)
    assert all(w > 0 for w in out)
    assert min(out) < max(out), "a non-matching class must be downweighted"


def test_cannot_choose_multiplies_nothing():
    weights = [0.3, 0.5, 0.2]
    labels = ["a", "b", "c"]
    assert interview.apply_answer(weights, labels, [], 0.75) == weights


def test_many_wrong_answers_still_leave_the_truth_positive():
    grid = interview.ChartGrid(dt.date(1935, 1, 8), *PLACE.values())
    truth = 4 * 60 + 35
    wrong_sign = "aries" if grid.asc_sign[truth] != "aries" else "taurus"
    answers = [
        {"question_id": f"q{i}", "channel": "rising_sign", "answer_ids": [wrong_sign]}
        for i in range(6)
    ]
    posterior, _ = interview.build_posterior(grid, answers, interview.InterviewConfig())
    assert posterior[truth] > 0.0
    assert sum(posterior) == pytest.approx(1.0)


def test_posterior_is_a_normalised_distribution(client, auth_headers):
    resp = client.post("/v1/interview/step", json=_body(), headers=auth_headers)
    assert resp.status_code == 200
    summary = resp.json()["posterior_summary"]
    assert 0 < summary["top_mass"] <= 1


# --------------------------------------------------------------------------
# Determinism and statelessness
# --------------------------------------------------------------------------


def test_same_input_same_output(client, auth_headers):
    body = _body([
        {
            "question_id": "stage1_rising_sign",
            "channel": "rising_sign",
            "answer_ids": ["sagittarius"],
        }
    ])
    a = client.post("/v1/interview/step", json=body, headers=auth_headers).json()
    b = client.post("/v1/interview/step", json=body, headers=auth_headers).json()
    a.pop("compute_ms"), b.pop("compute_ms")
    a["telemetry"].pop("compute_ms"), b["telemetry"].pop("compute_ms")
    assert a == b


# --------------------------------------------------------------------------
# Questions come from geometry
# --------------------------------------------------------------------------


def test_first_question_is_the_rising_sign_with_real_spans(client, auth_headers):
    resp = client.post("/v1/interview/step", json=_body(), headers=auth_headers)
    q = resp.json()["next_question"]
    assert q["channel"] == "rising_sign"
    assert q["stage"] == 1
    assert q["allow_cannot_choose"] is True
    assert len(q["options"]) == 12
    for opt in q["options"]:
        assert opt["spans"], "every sign option must carry its time span"
        assert opt["description_keys"], "descriptions are keys, not prose"
        for key in opt["description_keys"]:
            assert key.startswith("sign."), "structured keys, not sentences"


def test_mover_question_is_selected_by_information_gain(client, auth_headers):
    """The planet asked about is computed per chart, not hardcoded: the
    measured best pair differs across charts."""
    answers = [
        {
            "question_id": "stage1_rising_sign",
            "channel": "rising_sign",
            "answer_ids": ["sagittarius"],
        },
        {"question_id": "stage2_decan", "channel": "decan", "answer_ids": []},
    ]
    resp = client.post("/v1/interview/step", json=_body(answers), headers=auth_headers)
    q = resp.json()["next_question"]
    assert q["channel"] == "mover_house"
    assert q["subject"] in {name for name, _ in __import__(
        "astro_engine.core", fromlist=["core"]
    ).PLANETS}
    assert q["information_bits"] > 0


# --------------------------------------------------------------------------
# Tiers
# --------------------------------------------------------------------------


def test_no_answers_is_tier_4_refusal(client, auth_headers):
    resp = client.post("/v1/interview/step", json=_body(), headers=auth_headers)
    result = resp.json()
    assert result["tier"] == 4
    assert result["windows"] == []
    assert "cannot work" in result["tier_reason"]


def test_tier_1_and_2_always_carry_window_bounds():
    """A Tier 1/2 answer is never a bare time."""
    case = _load_case("presley_elvis")
    grid = interview.ChartGrid(
        dt.date.fromisoformat(case["birth_date"]),
        case["place"]["lat"], case["place"]["lon"], case["place"]["tz"],
    )
    cfg = interview.InterviewConfig()
    hh, mm = map(int, case["known_time"].split(":"))
    truth = hh * 60 + mm
    answers = [
        {
            "question_id": "stage1_rising_sign",
            "channel": "rising_sign",
            "answer_ids": [grid.asc_sign[truth]],
        }
    ]
    posterior, trace = interview.build_posterior(grid, answers, cfg)
    tier = interview.assign_tier(posterior, trace, cfg)
    for window in tier["windows"]:
        assert {"start", "end", "midpoint", "width_minutes", "mass"} <= set(window)


def test_empty_channel_overlap_is_not_scored_as_agreement():
    """Answers that agree nowhere are the absence of evidence, not sharp
    evidence. Scoring an empty intersection as agreement let random answering
    reach Tier 1."""
    trace = [
        {"answer_ids": ["a"], "supported": [0, 1], "labels": ["a", "a"] + ["b"] * (interview.N_GRID - 2), "class_count": 2},
        {"answer_ids": ["c"], "supported": [5, 6], "labels": ["c" if i in (5, 6) else "d" for i in range(interview.N_GRID)], "class_count": 2},
    ]
    p, overlap = interview.chance_agreement(trace)
    assert overlap == 0
    assert p == 1.0


# --------------------------------------------------------------------------
# Calibration compare endpoint
# --------------------------------------------------------------------------


def test_compare_endpoint_returns_error_and_captures_no_pii(client, auth_headers):
    case = _load_case("presley_elvis")
    body = {
        "birth_date": case["birth_date"],
        "place": {
            "lat": case["place"]["lat"],
            "lon": case["place"]["lon"],
            "tz": case["place"]["tz"],
        },
        "answers": [
            {
                "question_id": "stage1_rising_sign",
                "channel": "rising_sign",
                "answer_ids": ["sagittarius"],
            }
        ],
        "documented_time": case["known_time"],
    }
    resp = client.post("/v1/interview/compare", json=body, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()

    assert set(result) == {
        "tier",
        "abs_error_minutes",
        "window_contains_documented",
        "coherence",
        "telemetry",
    }
    blob = json.dumps(result)
    assert case["known_time"] not in blob, "the documented time must not be echoed"
    assert "sagittarius" not in blob, "answers must not be captured"
    assert "answer" not in json.dumps(result["telemetry"]).replace("answers_total", "").replace(
        "answers_informative", ""
    )
    for key in ("tier", "concentration", "chance_agreement_p", "grid_minutes"):
        assert key in result["telemetry"]


def test_interview_step_has_no_field_for_a_documented_time(client, auth_headers):
    """The calibration contract is structural: a blind session cannot leak the
    documented time into the interview because the interview schema has
    nowhere to put it."""
    from astro_engine.schemas import InterviewRequest

    assert "documented_time" not in InterviewRequest.model_fields
    assert InterviewRequest.model_config.get("extra") == "forbid"


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------


def test_interview_step_within_one_second(client, auth_headers):
    body = _body([
        {
            "question_id": "stage1_rising_sign",
            "channel": "rising_sign",
            "answer_ids": ["sagittarius"],
        }
    ])
    t0 = time.perf_counter()
    resp = client.post("/v1/interview/step", json=body, headers=auth_headers)
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert elapsed < 1.0, f"interview step took {elapsed:.2f}s at the 1-minute grid"
    assert resp.json()["telemetry"]["grid_minutes"] == 1440
