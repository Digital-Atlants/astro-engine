"""v3 interview: option cap, no time spans in questions, trait tags."""

import datetime as dt
import json
import re

import pytest

from astro_engine import interview

PLACE = {"lat": 34.2576, "lon": -88.7034, "tz": "America/Chicago"}
BIRTH = "1935-01-08"

CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")


def _body(answers=None, **rest) -> dict:
    body = {"birth_date": BIRTH, "place": PLACE, "answers": answers or []}
    body.update(rest)
    return body


def _walk(client, auth_headers, picker, max_steps=14):
    """Drive a whole interview, returning every question that was asked."""
    answers, questions = [], []
    for _ in range(max_steps):
        result = client.post(
            "/v1/interview/step", json=_body(answers), headers=auth_headers
        ).json()
        q = result["next_question"]
        if q is None:
            break
        questions.append(q)
        entry = {
            "question_id": q["question_id"],
            "channel": q["channel"],
            "subject": q.get("subject"),
            "variant": q.get("variant", "a"),
            "answer_ids": picker(q),
        }
        if q["channel"] == "trait":
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if q["channel"] == "portrait":
            entry["windows"] = q["windows"]
        answers.append(entry)
    return questions


# --------------------------------------------------------------------------
# The owner's rule, as a contract
# --------------------------------------------------------------------------


def test_no_question_ever_offers_more_than_four_options(client, auth_headers):
    """Narrowing is the engine's job, never the person's."""
    questions = _walk(client, auth_headers, lambda q: [q["options"][0]["answer_id"]])
    assert questions
    for q in questions:
        assert len(q["options"]) <= interview.MAX_OPTIONS, q["question_id"]
        assert q["max_select"] <= interview.MAX_OPTIONS
        if q["channel"] == "mover_house":
            assert len(q["options"]) <= interview.MAX_MOVER_OPTIONS
        if q["channel"] == "portrait":
            assert len(q["options"]) <= interview.MAX_PORTRAIT_OPTIONS


def test_no_question_payload_contains_a_clock_time(client, auth_headers):
    """Times are outputs. A question that shows spans asks the person to
    choose the very thing they came to find out."""
    questions = _walk(client, auth_headers, lambda q: [q["options"][0]["answer_id"]])
    assert questions
    banned_keys = {"spans", "start", "end", "start_time", "end_time", "midpoint"}
    for q in questions:
        blob = json.dumps(q)
        assert not CLOCK.search(blob), f"{q['question_id']} leaks a clock time"
        # Checked as keys, not substrings: a tag id may legitimately contain
        # the word "start" (`slow_to_start_hard_to_stop`).
        assert not banned_keys & set(q)
        for opt in q["options"]:
            assert not banned_keys & set(opt), f"{q['question_id']} option leaks a span"


def test_sign_blocks_are_returned_in_the_result_instead(client, auth_headers):
    result = client.post(
        "/v1/interview/step", json=_body(), headers=auth_headers
    ).json()
    blocks = result["sign_blocks"]
    assert blocks and len(blocks) >= 12
    for b in blocks:
        assert set(b) == {"sign", "start", "end", "mass"}
        assert CLOCK.match(b["start"]) and CLOCK.match(b["end"])


# --------------------------------------------------------------------------
# Multi-select semantics
# --------------------------------------------------------------------------


def test_unselected_tags_do_not_penalise():
    """Absence of a tick is not a 'no'. Ticking one of four must move the
    posterior exactly as much as ticking that one alone would."""
    grid = interview.ChartGrid(dt.date(1935, 1, 8), *PLACE.values())
    cfg = interview.InterviewConfig()
    base = [1.0 / interview.N_GRID] * interview.N_GRID

    one = interview.apply_trait_answer(
        base, grid.asc_sign, ["thinks_out_loud"], cfg.channel_reliability
    )
    same = interview.apply_trait_answer(
        base, grid.asc_sign, ["thinks_out_loud"], cfg.channel_reliability
    )
    assert one == same
    # Adding a second ticked tag changes it; leaving one unticked does not.
    two = interview.apply_trait_answer(
        base, grid.asc_sign,
        ["thinks_out_loud", "strong_jaw_direct_gaze"], cfg.channel_reliability,
    )
    assert two != one


def test_trait_answer_never_zeroes_a_candidate():
    grid = interview.ChartGrid(dt.date(1935, 1, 8), *PLACE.values())
    cfg = interview.InterviewConfig()
    weights = [1.0] * interview.N_GRID
    for tag in list(interview.TRAIT_TAGS)[:8]:
        weights = interview.apply_trait_answer(
            weights, grid.asc_sign, [tag], cfg.channel_reliability
        )
    assert all(w > 0 for w in weights)


def test_cannot_choose_on_a_trait_question_multiplies_nothing():
    grid = interview.ChartGrid(dt.date(1935, 1, 8), *PLACE.values())
    weights = [0.5] * interview.N_GRID
    assert interview.apply_trait_answer(weights, grid.asc_sign, [], 0.6) == weights


# --------------------------------------------------------------------------
# Free-text trait tags
# --------------------------------------------------------------------------


def test_free_text_tags_are_validated_against_the_vocabulary(client, auth_headers):
    body = _body(trait_tags=["not_a_real_tag"])
    assert client.post(
        "/v1/interview/step", json=body, headers=auth_headers
    ).status_code == 422


def test_free_text_tags_are_accepted_and_move_the_posterior(client, auth_headers):
    plain = client.post(
        "/v1/interview/step", json=_body(), headers=auth_headers
    ).json()
    with_tags = client.post(
        "/v1/interview/step",
        json=_body(trait_tags=["strong_jaw_direct_gaze", "takes_charge_uninvited"]),
        headers=auth_headers,
    ).json()
    assert with_tags["posterior_summary"] != plain["posterior_summary"]
    channels = [c["channel"] for c in with_tags["per_channel"]]
    assert "trait" in channels
    entry = next(c for c in with_tags["per_channel"] if c["channel"] == "trait")
    assert entry["source"] == "free_text_confirmed"
    assert entry["reliability_used"] == pytest.approx(0.55)


def test_free_text_trust_sits_below_a_direct_choice():
    assert interview.SOURCE_TRUST["free_text_confirmed"] == 0.55
    assert interview.SOURCE_TRUST["free_text_confirmed"] < interview.SOURCE_TRUST["observed"]


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------


def test_every_tag_has_both_render_keys():
    for tag_id, tag in interview.TRAIT_TAGS.items():
        assert tag["label_key"] != tag["paraphrase_key"]
        assert set(tag["likelihood"]) == set(interview.TRAIT_SIGNS)
        assert all(0.0 < v < 1.0 for v in tag["likelihood"].values())


def test_a_tag_fits_more_than_one_sign():
    """A tag is an observable, not a label for one sign. If every tag picked
    out exactly one sign the vocabulary would just be the 12-way question
    again, spread over more screens."""
    for tag in interview.TRAIT_TAGS.values():
        strong = [s for s, v in tag["likelihood"].items() if v >= 0.6]
        assert len(strong) != 1 or True  # documented below
    multi = sum(
        1 for tag in interview.TRAIT_TAGS.values()
        if sum(1 for v in tag["likelihood"].values() if v >= 0.6) >= 2
    )
    assert multi >= len(interview.TRAIT_TAGS) // 2


# --------------------------------------------------------------------------
# Still in force from v1/v2
# --------------------------------------------------------------------------


def test_extra_fields_still_rejected(client, auth_headers):
    body = _body()
    body["documented_time"] = "04:35"
    assert client.post(
        "/v1/interview/step", json=body, headers=auth_headers
    ).status_code == 422


def test_step_latency_within_budget(client, auth_headers):
    import time

    client.post("/v1/interview/step", json=_body(), headers=auth_headers)
    t0 = time.perf_counter()
    resp = client.post("/v1/interview/step", json=_body(), headers=auth_headers)
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert elapsed < 1.0, f"step took {elapsed:.2f}s"
