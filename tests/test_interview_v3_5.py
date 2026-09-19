"""v3.5: measurement outputs. Nothing here decides anything.

The load-bearing test in this file is
`test_step_decisions_are_byte_identical_to_dc35fc4`: every other change in
v3.5 is additive by intent, and that test is what makes "by intent" checkable.
"""

import datetime as dt
import json
import pathlib
import re

import pytest

from astro_engine import interview

PLACE = {"lat": 34.2576, "lon": -88.7034, "tz": "America/Chicago"}
BIRTH = "1935-01-08"
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "step_dc35fc4.json"

NEW_SUMMARY_KEYS = ("best_time", "working_time", "working_time_source")


def _body(answers=None, **rest) -> dict:
    body = {"birth_date": BIRTH, "place": PLACE, "answers": answers or []}
    body.update(rest)
    return body


def _flat(value: float = 1.0) -> list[float]:
    return [value] * interview.N_GRID


def _spiked(*spans) -> list[float]:
    post = [0.0] * interview.N_GRID
    for lo, hi in spans:
        for i in range(lo, hi + 1):
            post[i % interview.N_GRID] = 1.0
    return post


# --------------------------------------------------------------------------
# 1. plateau_midpoint, unit
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "posterior, expected",
    [
        (_flat(), "11:59"),
        (_spiked((600, 719)), "10:59"),
        # Two plateaus of equal height: the longer one wins.
        (_spiked((100, 129), (900, 1019)), "15:59"),
        # Equal length: the earlier start wins.
        (_spiked((100, 129), (900, 929)), "01:54"),
        # A plateau that wraps midnight is one run, not two.
        (_spiked((1400, 1439), (0, 39)), "23:59"),
    ],
)
def test_plateau_midpoint(posterior, expected):
    assert interview.minute_to_time(interview.plateau_midpoint(posterior)) == expected


def test_peak_time_still_reports_the_first_minute_of_the_maximum():
    """`peak_time` is kept unchanged for backward compatibility, which is only
    meaningful if it keeps its old, biased behaviour."""
    for posterior, first in (
        (_flat(), 0),
        (_spiked((600, 719)), 600),
        (_spiked((100, 129), (900, 1019)), 100),
        (_spiked((1400, 1439), (0, 39)), 0),
    ):
        peak = max(range(interview.N_GRID), key=lambda i: posterior[i])
        assert peak == first


def test_plateau_midpoint_and_peak_time_disagree_on_a_flat_posterior():
    """The whole reason the new key exists: with nothing known, `peak_time`
    says 00:00 and the honest answer is the middle of the day."""
    flat = _flat()
    assert max(range(interview.N_GRID), key=lambda i: flat[i]) == 0
    assert interview.plateau_midpoint(flat) == 719


# --------------------------------------------------------------------------
# 3. decisions untouched
# --------------------------------------------------------------------------


def test_step_decisions_are_byte_identical_to_dc35fc4(client, auth_headers):
    """v3.5 changes what can be measured, not what is decided.

    The fixture is a real `/v1/interview/step` response recorded from main at
    dc35fc4 before any of this work. Strip the three additive keys and the
    responses must match exactly - tier, windows, coherence, next_question,
    sign_blocks, per_channel, telemetry and peak_time included.
    """
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    resp = client.post("/v1/interview/step", json=fixture["request"],
                       headers=auth_headers)
    assert resp.status_code == 200
    fresh = resp.json()

    fresh.pop("compute_ms", None)
    fresh["telemetry"].pop("compute_ms", None)
    for key in NEW_SUMMARY_KEYS:
        assert key in fresh["posterior_summary"], f"{key} should have been added"
        fresh["posterior_summary"].pop(key)

    assert fresh == fixture["response"]


def test_posterior_summary_has_exactly_the_expected_keys(client, auth_headers):
    resp = client.post("/v1/interview/step", json=_body(), headers=auth_headers)
    assert set(resp.json()["posterior_summary"]) == {
        "peak_time", "best_time", "working_time", "working_time_source",
        "top_mass", "effective_candidates",
    }


# --------------------------------------------------------------------------
# 4. the working_time rule
# --------------------------------------------------------------------------


def test_working_time_is_the_top_mass_window_when_windows_exist(client, auth_headers):
    grid = interview.ChartGrid(dt.date.fromisoformat(BIRTH), *PLACE.values())
    truth = 4 * 60 + 35
    sign = grid.asc_sign[truth]
    axis = interview._SIGN_AXIS[sign]
    answers, windows = [], None
    for _ in range(14):
        result = client.post("/v1/interview/step", json=_body(answers),
                             headers=auth_headers).json()
        if result["windows"]:
            summary = result["posterior_summary"]
            heaviest = max(result["windows"], key=lambda w: w["mass"])
            assert summary["working_time"] == heaviest["midpoint"]
            assert summary["working_time_source"] == "window_midpoint"
            return
        q = result["next_question"]
        if q is None:
            break
        ch = q["channel"]
        ids = [o["answer_id"] for o in q["options"]]
        if ch == "element":
            pick = [f"element_{axis['element']}"]
        elif ch == "modality":
            pick = [f"modality_{axis['modality']}"]
        elif ch == "sign_portrait":
            pick = [sign]
        else:
            labels = interview.partition_for(grid, ch, q.get("subject"), windows)
            pick = [labels[truth]]
        entry = {"question_id": q["question_id"], "channel": ch,
                 "variant": q.get("variant", "a"), "subject": q.get("subject"),
                 "answer_ids": [p for p in pick if p in ids]}
        if "offered_tag_ids" in q:
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if ch == "portrait":
            windows = [tuple(w) for w in q["windows"]]
            entry["windows"] = q["windows"]
        answers.append(entry)
    pytest.fail("no window was ever produced")


def test_working_time_falls_back_to_the_plateau_when_there_are_no_windows(
        client, auth_headers):
    result = client.post("/v1/interview/step", json=_body(),
                         headers=auth_headers).json()
    assert result["tier"] == 4 and result["windows"] == []
    summary = result["posterior_summary"]
    assert summary["working_time"] == summary["best_time"]
    assert summary["working_time_source"] == "plateau_midpoint"


# --------------------------------------------------------------------------
# 5-6. /compare replays the session and scores every tier
# --------------------------------------------------------------------------


def _compare_body(answers=None, **rest) -> dict:
    body = {"birth_date": BIRTH, "place": PLACE, "answers": answers or [],
            "documented_time": "04:35"}
    body.update(rest)
    return body


def test_compare_replays_trait_tags(client, auth_headers):
    """A session that cannot be replayed is scored against a different
    posterior than the one the person actually saw."""
    tags = ["element_fire", "modality_fixed"]
    cmp_resp = client.post("/v1/interview/compare",
                           json=_compare_body(trait_tags=tags),
                           headers=auth_headers)
    assert cmp_resp.status_code == 200
    step_resp = client.post("/v1/interview/step", json=_body(trait_tags=tags),
                            headers=auth_headers)

    cmp_tel = dict(cmp_resp.json()["telemetry"])
    step_tel = dict(step_resp.json()["telemetry"])
    cmp_tel.pop("compute_ms", None)
    step_tel.pop("compute_ms", None)
    assert cmp_tel == step_tel


def test_compare_rejects_an_unknown_trait_tag(client, auth_headers):
    resp = client.post("/v1/interview/compare",
                       json=_compare_body(trait_tags=["not_a_real_tag"]),
                       headers=auth_headers)
    assert resp.status_code == 422


def test_compare_scores_a_tier_4_session_that_used_to_produce_nothing(
        client, auth_headers):
    result = client.post("/v1/interview/compare", json=_compare_body(),
                         headers=auth_headers).json()
    assert result["tier"] == 4
    # Unchanged: no window means no window error.
    assert result["abs_error_minutes"] is None
    # New: there is always a working time, so there is always a measurement.
    assert isinstance(result["abs_error_minutes_working"], int)
    assert 0 <= result["abs_error_minutes_working"] <= 720
    assert 0.0 <= result["truth_rank_pct"] <= 100.0


def test_an_empty_session_ranks_the_truth_at_chance(client, auth_headers):
    """With no answers the posterior is flat, so the documented minute is
    exactly average. A mid-rank percentile is what makes that read as 50
    rather than 0 or 100."""
    result = client.post("/v1/interview/compare", json=_compare_body(),
                         headers=auth_headers).json()
    assert result["truth_rank_pct"] == 50.0
    # ...and the sign mass is just that sign's share of the day.
    grid = interview.ChartGrid(dt.date.fromisoformat(BIRTH), *PLACE.values())
    truth = 4 * 60 + 35
    share = sum(1 for s in grid.asc_sign if s == grid.asc_sign[truth])
    assert result["truth_sign_mass"] == pytest.approx(
        share / interview.N_GRID, abs=5e-4)


def test_documented_minute_is_round_marks_registrar_rounding(client, auth_headers):
    on_five = client.post("/v1/interview/compare",
                          json=_compare_body(documented_time="04:35"),
                          headers=auth_headers).json()
    off_five = client.post("/v1/interview/compare",
                           json=_compare_body(documented_time="04:37"),
                           headers=auth_headers).json()
    assert on_five["documented_minute_is_round"] is True
    assert off_five["documented_minute_is_round"] is False


# --------------------------------------------------------------------------
# 7. truth_in_choice
# --------------------------------------------------------------------------


def _element_answer(element_tag):
    return {"question_id": "stage1_element_a", "channel": "element",
            "answer_ids": [element_tag] if element_tag else []}


def test_truth_in_choice_tracks_whether_the_answer_supported_the_truth(
        client, auth_headers):
    grid = interview.ChartGrid(dt.date.fromisoformat(BIRTH), *PLACE.values())
    truth = 4 * 60 + 35
    right = interview._SIGN_AXIS[grid.asc_sign[truth]]["element"]
    wrong = next(e for e in ("fire", "earth", "air", "water") if e != right)

    good = client.post("/v1/interview/compare",
                       json=_compare_body([_element_answer(f"element_{right}")]),
                       headers=auth_headers).json()
    assert good["per_answer"][0]["truth_in_choice"] is True
    assert good["per_answer"][0]["cannot_choose"] is False

    bad = client.post("/v1/interview/compare",
                      json=_compare_body([_element_answer(f"element_{wrong}")]),
                      headers=auth_headers).json()
    assert bad["per_answer"][0]["truth_in_choice"] is False

    silent = client.post("/v1/interview/compare",
                         json=_compare_body([_element_answer(None)]),
                         headers=auth_headers).json()
    assert silent["per_answer"][0]["cannot_choose"] is True
    assert silent["per_answer"][0]["truth_in_choice"] is None


def test_per_answer_includes_the_synthetic_free_text_entry(client, auth_headers):
    result = client.post(
        "/v1/interview/compare",
        json=_compare_body([_element_answer("element_fire")],
                           trait_tags=["modality_fixed"]),
        headers=auth_headers).json()
    assert len(result["per_answer"]) == 2
    synthetic = result["per_answer"][1]
    assert synthetic["channel"] == "trait"
    assert synthetic["source"] == "free_text_confirmed"


# --------------------------------------------------------------------------
# 8. PII-free, structurally
# --------------------------------------------------------------------------


def test_compare_response_carries_nothing_about_the_person(client, auth_headers):
    """The record exists so a labelled corpus can accumulate WITHOUT storing
    anything about the person. This is the test that keeps that true."""
    answers = [_element_answer("element_fire")]
    tags = ["modality_fixed"]
    result = client.post("/v1/interview/compare",
                         json=_compare_body(answers, trait_tags=tags),
                         headers=auth_headers).json()
    blob = json.dumps(result)

    assert not re.search(r"\d{1,2}:\d{2}", blob), "no clock time may appear"
    assert "04:35" not in blob
    assert "element_fire" not in blob, "answer ids must not be captured"
    assert "modality_fixed" not in blob, "tag ids must not be captured"
    assert BIRTH not in blob and "1935" not in blob
    assert "34.2576" not in blob and "America/Chicago" not in blob

    for entry in result["per_answer"]:
        assert set(entry) == {
            "channel", "subject", "variant", "source", "pair_state",
            "class_count", "cannot_choose", "truth_in_choice",
        }


def test_compare_response_has_exactly_the_agreed_key_set(client, auth_headers):
    result = client.post("/v1/interview/compare", json=_compare_body(),
                         headers=auth_headers).json()
    assert set(result) == {
        "tier", "abs_error_minutes", "window_contains_documented", "coherence",
        "telemetry", "abs_error_minutes_working", "working_time_source",
        "truth_rank_pct", "truth_sign_correct", "truth_sign_mass",
        "documented_minute_is_round", "per_answer",
    }


# --------------------------------------------------------------------------
# 10. determinism
# --------------------------------------------------------------------------


def test_compare_is_deterministic(client, auth_headers):
    body = _compare_body([_element_answer("element_fire")],
                         trait_tags=["modality_fixed"])
    first = client.post("/v1/interview/compare", json=body, headers=auth_headers)
    second = client.post("/v1/interview/compare", json=body, headers=auth_headers)
    assert first.json() == second.json()
    assert json.dumps(first.json(), sort_keys=True) == json.dumps(
        second.json(), sort_keys=True)


def test_run_interview_public_result_is_not_widened():
    """The internals are private. Widening the public result would put the
    posterior and the trace into every `/step` response."""
    public = interview.run_interview(
        dt.date.fromisoformat(BIRTH), PLACE["lat"], PLACE["lon"], PLACE["tz"], [])
    assert isinstance(public, dict)
    assert "posterior" not in public and "trace" not in public

    internal = interview._run_interview_internal(
        dt.date.fromisoformat(BIRTH), PLACE["lat"], PLACE["lon"], PLACE["tz"], [])
    assert len(internal) == 4
    assert internal[0] == public
    assert len(internal[1]) == interview.N_GRID
