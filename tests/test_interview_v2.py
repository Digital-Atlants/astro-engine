"""v2 interview: pair logic, source trust, document bounds, hypothesis."""

import datetime as dt
import json
import pathlib

import pytest

from astro_engine import interview

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "benchmarks" / "corpus"
PLACE = {"lat": 34.2576, "lon": -88.7034, "tz": "America/Chicago"}
BIRTH = "1935-01-08"


def _sign(variant: str, ids: list[str], **extra) -> dict:
    return {
        "question_id": f"stage1_rising_sign_{variant}",
        "channel": "rising_sign",
        "variant": variant,
        "answer_ids": ids,
        **extra,
    }


def _body(answers=None, **rest) -> dict:
    body = {"birth_date": BIRTH, "place": PLACE, "answers": answers or []}
    body.update(rest)
    return body


# --------------------------------------------------------------------------
# Pair logic
# --------------------------------------------------------------------------


def test_agreeing_pair_counts_once_at_full_trust():
    cfg = interview.InterviewConfig()
    pairs = interview.combine_pairs([_sign("a", ["leo"]), _sign("b", ["leo"])], cfg)
    assert pairs["agreeing_pairs"] == 1
    assert pairs["disagreeing_pairs"] == 0
    assert pairs["session_reliability"] == cfg.channel_reliability
    assert [e["answer_ids"] for e in pairs["effective"]] == [["leo"]]


def test_disagreeing_pair_voids_the_question_and_costs_trust():
    cfg = interview.InterviewConfig()
    pairs = interview.combine_pairs([_sign("a", ["leo"]), _sign("b", ["virgo"])], cfg)
    assert pairs["agreeing_pairs"] == 0
    assert pairs["disagreeing_pairs"] == 1
    assert pairs["effective"][0]["answer_ids"] == [], "the question must be voided"
    assert pairs["session_reliability"] == pytest.approx(
        cfg.channel_reliability - cfg.disagreement_penalty
    )


def test_disagreement_penalty_accumulates_but_never_reaches_zero():
    cfg = interview.InterviewConfig()
    answers = []
    for i, planet in enumerate(["sun", "moon", "mars", "venus", "jupiter"]):
        answers.append({"question_id": f"q{i}a", "channel": "mover_house",
                        "subject": planet, "variant": "a", "answer_ids": ["1"]})
        answers.append({"question_id": f"q{i}b", "channel": "mover_house",
                        "subject": planet, "variant": "b", "answer_ids": ["7"]})
    pairs = interview.combine_pairs(answers, cfg)
    assert pairs["disagreeing_pairs"] == 5
    assert pairs["session_reliability"] == cfg.min_session_reliability
    assert pairs["session_reliability"] > 0


def test_cannot_choose_on_one_phrasing_is_not_a_disagreement():
    """Declining to answer must never cost more than the information that
    answer would have carried."""
    cfg = interview.InterviewConfig()
    pairs = interview.combine_pairs([_sign("a", ["leo"]), _sign("b", [])], cfg)
    assert pairs["disagreeing_pairs"] == 0
    assert pairs["session_reliability"] == cfg.channel_reliability
    assert [e["answer_ids"] for e in pairs["effective"]] == [["leo"]]


def test_tier1_requires_two_agreeing_pairs_and_no_disagreement():
    case = json.loads((CORPUS / "train" / "presley_elvis.json").read_text(encoding="utf-8"))
    grid = interview.ChartGrid(
        dt.date.fromisoformat(case["birth_date"]),
        case["place"]["lat"], case["place"]["lon"], case["place"]["tz"],
    )
    cfg = interview.InterviewConfig()
    hh, mm = map(int, case["known_time"].split(":"))
    truth = hh * 60 + mm

    # One agreeing pair only: cannot be Tier 1 however sharp the posterior.
    answers = [
        _sign("a", [grid.asc_sign[truth]]),
        _sign("b", [grid.asc_sign[truth]]),
    ]
    posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
    assert pairs["agreeing_pairs"] == 1
    assert interview.assign_tier(posterior, trace, cfg, pairs)["tier"] != 1


def test_single_pass_mode_does_not_require_pairs():
    cfg = interview.InterviewConfig(repeat=False)
    pairs = interview.combine_pairs([_sign("a", ["leo"])], cfg)
    assert pairs["agreeing_pairs"] == 0
    # In single-pass mode the pair requirement is waived; the tier is then
    # decided by mass and agreement alone.
    posterior = [1.0 / interview.N_GRID] * interview.N_GRID
    tier = interview.assign_tier(posterior, [], cfg, pairs)
    assert tier["tier"] in (1, 2, 3, 4)


# --------------------------------------------------------------------------
# Source trust
# --------------------------------------------------------------------------


def test_source_sets_the_reliability_used():
    cfg = interview.InterviewConfig()
    assert interview.answer_reliability({"source": "document"}, 0.6) == 0.90
    assert interview.answer_reliability({"source": "observed"}, 0.6) == 0.80
    assert interview.answer_reliability({"source": "inferred"}, 0.6) == 0.50
    # client_report defers to whatever the session earned.
    assert interview.answer_reliability({"source": "client_report"}, 0.45) == 0.45
    assert interview.answer_reliability({}, 0.45) == 0.45


def test_document_source_outweighs_a_client_report(client, auth_headers):
    strong = _sign("a", ["sagittarius"], source="document")
    weak = _sign("a", ["sagittarius"], source="inferred")
    a = client.post("/v1/interview/step", json=_body([strong]), headers=auth_headers).json()
    b = client.post("/v1/interview/step", json=_body([weak]), headers=auth_headers).json()
    assert a["posterior_summary"]["top_mass"] > b["posterior_summary"]["top_mass"]


# --------------------------------------------------------------------------
# Documentary bounds: never zero
# --------------------------------------------------------------------------


def test_document_bounds_downweight_but_never_delete():
    grid = interview.ChartGrid(dt.date(1935, 1, 8), *PLACE.values())
    cfg = interview.InterviewConfig()
    posterior, _, _ = interview.build_posterior(
        grid, [], cfg, known_bounds={"start": "04:00", "end": "05:00"}
    )
    assert all(p > 0 for p in posterior), "a certificate can be misread"
    inside = posterior[4 * 60 + 30]
    outside = posterior[20 * 60]
    assert inside > outside
    assert outside / inside == pytest.approx(interview.DOCUMENT_BOUND_FACTOR, rel=1e-6)


def test_document_bounds_accepted_over_the_api(client, auth_headers):
    body = _body([], known_bounds={"start": "04:00", "end": "05:00"})
    resp = client.post("/v1/interview/step", json=body, headers=auth_headers)
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# Claimed time is a soft prior
# --------------------------------------------------------------------------


def test_claimed_time_is_soft_and_does_not_dominate():
    """The owner's own confidently held time was 18 minutes out, so a claimed
    time may lean the posterior but must not decide it."""
    grid = interview.ChartGrid(dt.date(1935, 1, 8), *PLACE.values())
    cfg = interview.InterviewConfig()
    posterior, _, _ = interview.build_posterior(grid, [], cfg, claimed_time="04:35")
    assert all(p > 0 for p in posterior)
    near = posterior[4 * 60 + 35]
    far = posterior[20 * 60]
    assert near > far
    assert near / far <= 1.0 + cfg.claimed_time_weight + 1e-9


# --------------------------------------------------------------------------
# Hypothesis is excluded from the posterior
# --------------------------------------------------------------------------


def test_hypothesis_never_enters_the_posterior(client, auth_headers):
    answers = [_sign("a", ["sagittarius"])]
    plain = client.post(
        "/v1/interview/step", json=_body(answers), headers=auth_headers
    ).json()
    with_hyp = client.post(
        "/v1/interview/step",
        json=_body(answers, hypothesis={"start": "09:00", "end": "09:30"}),
        headers=auth_headers,
    ).json()

    assert plain["posterior_summary"] == with_hyp["posterior_summary"]
    assert plain["windows"] == with_hyp["windows"]
    assert "hypothesis_check" not in plain
    check = with_hyp["hypothesis_check"]
    assert check["excluded_from_posterior"] is True
    assert set(check) == {
        "inside_result_window",
        "distance_minutes",
        "excluded_from_posterior",
    }


# --------------------------------------------------------------------------
# Sphere inventory
# --------------------------------------------------------------------------


def test_inventory_answers_a_mover_question_when_it_discriminates():
    options = ["3", "4", "5"]
    inventory = {
        "3": {"status": "absent"},
        "4": {"status": "dominant"},
        "5": {"status": "absent"},
    }
    assert interview._inventory_answer(inventory, options) == ["4"]


def test_inventory_that_says_nothing_does_not_answer():
    options = ["3", "4"]
    assert interview._inventory_answer({}, options) == []
    all_same = {"3": {"status": "dominant"}, "4": {"status": "dominant"}}
    assert interview._inventory_answer(all_same, options) == []


# --------------------------------------------------------------------------
# Contract still in force
# --------------------------------------------------------------------------


def test_extra_fields_still_rejected(client, auth_headers):
    body = _body()
    body["documented_time"] = "04:35"
    assert client.post(
        "/v1/interview/step", json=body, headers=auth_headers
    ).status_code == 422


def test_answer_ids_still_enum_only(client, auth_headers):
    body = _body([_sign("a", ["04:35"])])
    assert client.post(
        "/v1/interview/step", json=body, headers=auth_headers
    ).status_code == 422


def test_variant_must_be_a_or_b(client, auth_headers):
    body = _body([_sign("c", ["leo"])])
    assert client.post(
        "/v1/interview/step", json=body, headers=auth_headers
    ).status_code == 422


def test_repeat_question_uses_a_different_description_key(client, auth_headers):
    first = client.post(
        "/v1/interview/step", json=_body(), headers=auth_headers
    ).json()["next_question"]
    assert first["variant"] == "a"
    facet_a = first["facet"]
    facet_b = interview.VARIANT_FACET["rising_sign"]["b"]
    assert facet_a != facet_b
    for opt in first["options"]:
        assert opt["description_keys"] == [f"sign.{opt['answer_id']}.{facet_a}"]


def test_professional_mode_returns_density_and_decisive_questions(client, auth_headers):
    body = _body([_sign("a", ["sagittarius"])], config={"mode": "professional"})
    result = client.post("/v1/interview/step", json=body, headers=auth_headers).json()
    assert len(result["density"]) == interview.N_GRID
    assert result["decisive_questions"]
    assert "information_bits" in result["decisive_questions"][0]


def test_standard_mode_omits_professional_extras(client, auth_headers):
    result = client.post(
        "/v1/interview/step", json=_body([_sign("a", ["sagittarius"])]),
        headers=auth_headers,
    ).json()
    assert "density" not in result
    assert "decisive_questions" not in result
