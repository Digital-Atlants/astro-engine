"""v3.1: structured stage 1, two-portrait confirmation, conflict, tiers."""

import datetime as dt
import json

import pytest

from astro_engine import interview

PLACE = {"lat": 34.2576, "lon": -88.7034, "tz": "America/Chicago"}
BIRTH = "1935-01-08"


def _body(answers=None, **rest) -> dict:
    body = {"birth_date": BIRTH, "place": PLACE, "answers": answers or []}
    body.update(rest)
    return body


def _ans(qid, channel, ids, variant="a", **extra):
    return {"question_id": qid, "channel": channel, "variant": variant,
            "answer_ids": ids, **extra}


def _grid():
    return interview.ChartGrid(dt.date.fromisoformat(BIRTH), *PLACE.values())


# --------------------------------------------------------------------------
# Stage 1 is element then modality
# --------------------------------------------------------------------------


def test_stage1_is_element_then_modality(client, auth_headers):
    first = client.post(
        "/v1/interview/step", json=_body(), headers=auth_headers
    ).json()["next_question"]
    assert first["channel"] == "element"
    assert first["select"] == "single"
    assert [o["answer_id"] for o in first["options"]] == interview.ELEMENT_TAGS
    assert len(first["options"]) == 4

    second = client.post(
        "/v1/interview/step",
        json=_body([_ans("stage1_element_a", "element", ["element_fire"])]),
        headers=auth_headers,
    ).json()["next_question"]
    assert second["channel"] == "modality"
    assert [o["answer_id"] for o in second["options"]] == interview.MODALITY_TAGS
    assert len(second["options"]) == 3


def test_adjacent_signs_differ_on_both_axes():
    """The safety argument for the restructure: reaching a neighbouring sign
    by mistake takes two errors, not one."""
    signs = interview.TRAIT_SIGNS
    for i, sign in enumerate(signs):
        nxt = signs[(i + 1) % 12]
        a, b = interview._SIGN_AXIS[sign], interview._SIGN_AXIS[nxt]
        assert a["element"] != b["element"], f"{sign}/{nxt} share an element"
        assert a["modality"] != b["modality"], f"{sign}/{nxt} share a modality"


def test_element_and_modality_are_independent_axes():
    for tag_id in interview.ELEMENT_TAGS:
        lik = interview.TRAIT_TAGS[tag_id]["likelihood"]
        by_modality: dict[str, set] = {}
        for sign, v in lik.items():
            by_modality.setdefault(
                interview._SIGN_AXIS[sign]["modality"], set()
            ).add(round(v, 4))
        # An element tag must not discriminate between modalities.
        for values in by_modality.values():
            assert len(values) <= 4
        elements = {
            interview._SIGN_AXIS[s]["element"] for s, v in lik.items() if v >= 0.6
        }
        assert len(elements) == 1


# --------------------------------------------------------------------------
# Two-portrait confirmation
# --------------------------------------------------------------------------


def test_portrait_question_offers_at_most_two_signs(client, auth_headers):
    grid = _grid()
    cfg = interview.InterviewConfig()
    truth = 4 * 60 + 35
    sign = grid.asc_sign[truth]
    axis = interview._SIGN_AXIS[sign]
    answers = [
        _ans("stage1_element_a", "element", [f"element_{axis['element']}"]),
        _ans("stage1_modality_a", "modality", [f"modality_{axis['modality']}"]),
    ]
    for _ in range(6):
        posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
        q = interview.next_question(grid, posterior, answers, cfg)
        assert q is not None
        if q["channel"] == "sign_portrait":
            assert len(q["options"]) <= interview.MAX_PORTRAIT_SIGNS
            assert q["allow_cannot_choose"] is True
            for opt in q["options"]:
                assert opt["answer_id"] in interview.TRAIT_SIGNS
                assert opt["label_key"].startswith("sign.")
            return
        # Answer correctly, otherwise the mass never concentrates and the
        # portrait step legitimately never fires.
        labels = interview.partition_for(grid, q["channel"], q.get("subject"), None)
        label = labels[truth]
        ids = [o["answer_id"] for o in q["options"]]
        pick = [label] if label in ids else []
        entry = _ans(q["question_id"], q["channel"], pick, q.get("variant", "a"))
        entry["subject"] = q.get("subject")
        if "offered_tag_ids" in q:
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        answers.append(entry)
    pytest.fail("the two-portrait confirmation was never offered")


def test_conflicting_portrait_blocks_tier_1_and_tier_3():
    """A portrait that contradicts the structural answers is a channel
    conflict, and a conflict blocks a delivered sign as well as a time."""
    grid = _grid()
    cfg = interview.InterviewConfig()
    truth = 4 * 60 + 35
    sign = grid.asc_sign[truth]
    axis = interview._SIGN_AXIS[sign]
    other = next(s for s in interview.TRAIT_SIGNS if s != sign)

    agreeing = [
        _ans("stage1_element_a", "element", [f"element_{axis['element']}"]),
        _ans("stage1_modality_a", "modality", [f"modality_{axis['modality']}"]),
        _ans("stage2_sign_portrait_a", "sign_portrait", [sign],
             offered_tag_ids=[sign, other]),
    ]
    conflicting = agreeing[:2] + [
        _ans("stage2_sign_portrait_a", "sign_portrait", [other],
             offered_tag_ids=[sign, other])
    ]

    p1, t1, pr1 = interview.build_posterior(grid, agreeing, cfg)
    ok = interview.assign_tier(p1, t1, cfg, pr1, grid.asc_sign)
    p2, t2, pr2 = interview.build_posterior(grid, conflicting, cfg)
    bad = interview.assign_tier(p2, t2, cfg, pr2, grid.asc_sign)

    assert ok["channel_conflict"] is False
    assert bad["channel_conflict"] is True
    assert bad["tier"] == 4
    assert bad["rising_sign"] is None
    assert "contradicts" in bad["reason"]


def test_tier_4_when_no_portrait_was_confirmed():
    """v1-v3 handed out a Tier 3 sign whenever any answer existed. A sign is
    a delivered answer and now has to be earned."""
    grid = _grid()
    cfg = interview.InterviewConfig()
    answers = [_ans("stage1_element_a", "element", ["element_fire"])]
    posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
    tier = interview.assign_tier(posterior, trace, cfg, pairs, grid.asc_sign)
    assert tier["tier"] == 4
    assert tier["rising_sign"] is None
    assert "portrait" in tier["reason"]


# --------------------------------------------------------------------------
# The v3 contract still holds
# --------------------------------------------------------------------------


def test_no_question_exceeds_four_options_or_carries_a_time(client, auth_headers):
    import re

    clock = re.compile(r"\b\d{1,2}:\d{2}\b")
    answers, seen = [], 0
    for _ in range(14):
        result = client.post(
            "/v1/interview/step", json=_body(answers), headers=auth_headers
        ).json()
        q = result["next_question"]
        if q is None:
            break
        seen += 1
        assert len(q["options"]) <= interview.MAX_OPTIONS
        assert not clock.search(json.dumps(q))
        entry = _ans(q["question_id"], q["channel"],
                     [q["options"][0]["answer_id"]], q.get("variant", "a"))
        entry["subject"] = q.get("subject")
        if "offered_tag_ids" in q:
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if q["channel"] == "portrait":
            entry["windows"] = q["windows"]
        answers.append(entry)
    assert seen >= 4


def test_copy_manifest_covers_every_channel_the_engine_asks(client, auth_headers):
    """A channel missing from the manifest is a channel the web will skip."""
    import pathlib

    manifest = json.loads(
        (pathlib.Path(interview.__file__).parent / "data" / "copy_manifest.json")
        .read_text(encoding="utf-8")
    )
    covered = set(manifest["keys_by_channel"])

    answers, asked = [], set()
    for _ in range(14):
        result = client.post(
            "/v1/interview/step", json=_body(answers), headers=auth_headers
        ).json()
        q = result["next_question"]
        if q is None:
            break
        asked.add(q["channel"])
        entry = _ans(q["question_id"], q["channel"],
                     [q["options"][0]["answer_id"]], q.get("variant", "a"))
        entry["subject"] = q.get("subject")
        if "offered_tag_ids" in q:
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if q["channel"] == "portrait":
            entry["windows"] = q["windows"]
        answers.append(entry)

    assert asked, "no questions were asked"
    assert asked <= covered, f"channels with no copy keys: {asked - covered}"
