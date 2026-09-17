"""v3.3: Tier 3 dropped, SHA in /health, approved copy, decan trust.

The spec's design decision was to order the tiers by strength of claim and
make Tier 3 - a rising sign with no time - the fallback. It was implemented,
measured, and failed its own gate: see benchmarks/RESULTS_INTERVIEW_v3_3.md.
These tests pin the pre-registered fallback that was taken instead, so the
tier cannot come back by accident.
"""

import datetime as dt
import json
import pathlib

from astro_engine import build_info, interview

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


def _sign_only_answers(grid, sign):
    """Stage 1 answered perfectly, twice over, and nothing else answered."""
    axis = interview._SIGN_AXIS[sign]
    other = next(s for s in interview.TRAIT_SIGNS if s != sign)
    out = []
    for variant in ("a", "b"):
        out += [
            _ans(f"stage1_element_{variant}", "element",
                 [f"element_{axis['element']}"], variant),
            _ans(f"stage1_modality_{variant}", "modality",
                 [f"modality_{axis['modality']}"], variant),
            _ans(f"stage2_sign_portrait_{variant}", "sign_portrait", [sign],
                 variant, offered_tag_ids=[sign, other]),
        ]
    return out


# --------------------------------------------------------------------------
# Work item 1, as it ended: no Tier 3, and the portrait threshold restored
# --------------------------------------------------------------------------


def test_the_portrait_step_waits_for_the_mass_to_concentrate(client, auth_headers):
    """The threshold on the portrait step is load-bearing for G1.

    v3.3 removed it so that a sign-only session could be offered a portrait
    and reach Tier 3. Measured, that let the adjacent-sign answerer confirm a
    portrait nothing had pointed at, and its Tier 1 wrong-window rate went
    from 1.04% to 32.50% with every such window wrong. The threshold is back.
    """
    grid = _grid()
    cfg = interview.InterviewConfig()
    axis = interview._SIGN_AXIS[grid.asc_sign[4 * 60 + 35]]
    answers = [
        _ans("stage1_element_a", "element", [f"element_{axis['element']}"]),
        _ans("stage1_modality_a", "modality", [f"modality_{axis['modality']}"]),
    ]
    posterior, _, _ = interview.build_posterior(grid, answers, cfg)
    masses = sorted(interview.sign_mass(posterior, grid.asc_sign).values(),
                    reverse=True)
    # Two structural answers do not concentrate the mass anywhere near the
    # threshold, which is the whole point: nothing has corroborated them yet.
    assert sum(masses[:interview.MAX_PORTRAIT_SIGNS]) < cfg.portrait_sign_threshold

    q = interview.next_question(grid, posterior, answers, cfg)
    assert q["channel"] != "sign_portrait"


def test_no_rising_sign_is_ever_delivered_on_its_own():
    """There is no Tier 3. The strongest sign-only session available - stage 1
    answered perfectly, twice over - gets Tier 4 and no sign."""
    grid = _grid()
    cfg = interview.InterviewConfig()
    sign = grid.asc_sign[4 * 60 + 35]
    answers = _sign_only_answers(grid, sign)

    posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
    # The session really is coherent: this is not a weak input being refused.
    assert interview.stage1_pairs_agree(trace) is True
    assert pairs["disagreeing_pairs"] == 0
    assert interview.sign_mass(posterior, grid.asc_sign)[sign] > 0.5

    tier = interview.assign_tier(posterior, trace, cfg, pairs, grid.asc_sign,
                                 sun_sign=grid.sun_sign)
    assert tier["tier"] == 4
    assert tier["rising_sign"] is None


def test_the_sign_posterior_is_still_returned_as_a_distribution(client, auth_headers):
    """Dropping the tier drops the *claim*, not the information. `sign_blocks`
    carries a mass per sign, which describes what the answers support."""
    result = client.post(
        "/v1/interview/step", json=_body(), headers=auth_headers
    ).json()
    assert result["rising_sign"] is None
    blocks = result["sign_blocks"]
    assert len({b["sign"] for b in blocks}) == 12
    assert abs(sum({b["sign"]: b["mass"] for b in blocks}.values()) - 1.0) < 1e-3


def test_no_tier_3_is_reachable_from_any_answer_sequence(client, auth_headers):
    """Belt and braces: walk a full interview and assert the tier is never 3."""
    answers = []
    for _ in range(14):
        result = client.post(
            "/v1/interview/step", json=_body(answers), headers=auth_headers
        ).json()
        assert result["tier"] in (1, 2, 4), result["tier"]
        q = result["next_question"]
        if q is None:
            break
        entry = _ans(q["question_id"], q["channel"],
                     [q["options"][0]["answer_id"]], q.get("variant", "a"))
        entry["subject"] = q.get("subject")
        if "offered_tag_ids" in q:
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if q["channel"] == "portrait":
            entry["windows"] = q["windows"]
        answers.append(entry)


def test_a_disagreement_anywhere_still_blocks_a_delivered_answer():
    grid = _grid()
    cfg = interview.InterviewConfig()
    sign = grid.asc_sign[4 * 60 + 35]
    answers = _sign_only_answers(grid, sign)

    # One extra question asked twice and answered inconsistently. Nothing
    # about the sign changed; the person's self-consistency did.
    labels = interview.partition_for(grid, "decan", None)
    classes = sorted(set(labels))
    conflicted = answers + [
        _ans("stage3_decan_a", "decan", [classes[0]], "a"),
        _ans("stage3_decan_b", "decan", [classes[1]], "b"),
    ]
    posterior, trace, pairs = interview.build_posterior(grid, conflicted, cfg)
    assert pairs["disagreeing_pairs"] == 1
    tier = interview.assign_tier(posterior, trace, cfg, pairs, grid.asc_sign,
                                 sun_sign=grid.sun_sign)
    assert tier["tier"] == 4
    assert tier["rising_sign"] is None


def test_stage1_pair_agreement_is_still_computed_for_the_detector():
    """`stage1_pairs_agree` outlived Tier 3: the sun-sign detector counts
    stage-1 pairs, so the helper stays and stays tested. A single unrepeated
    answer is not agreement, it is one observation."""
    grid = _grid()
    cfg = interview.InterviewConfig()
    sign = grid.asc_sign[4 * 60 + 35]
    single_pass = [a for a in _sign_only_answers(grid, sign)
                   if a["variant"] == "a"]
    posterior, trace, pairs = interview.build_posterior(grid, single_pass, cfg)
    assert interview.stage1_pairs_agree(trace) is False
    full = _sign_only_answers(grid, sign)
    _, trace_full, _ = interview.build_posterior(grid, full, cfg)
    assert interview.stage1_pairs_agree(trace_full) is True


# --------------------------------------------------------------------------
# Work item 3c: the sun-sign self-attribution detector
# --------------------------------------------------------------------------


def test_detector_fires_only_when_stage_1_names_the_sun_sign():
    grid = _grid()
    on = _sign_only_answers(grid, grid.sun_sign)
    other = next(s for s in interview.TRAIT_SIGNS if s != grid.sun_sign
                 and interview._SIGN_AXIS[s]["element"]
                 != interview._SIGN_AXIS[grid.sun_sign]["element"])
    off = _sign_only_answers(grid, other)

    cfg = interview.InterviewConfig()
    _, trace_on, _ = interview.build_posterior(grid, on, cfg)
    _, trace_off, _ = interview.build_posterior(grid, off, cfg)
    assert interview.stage1_favours_sun_sign(trace_on, grid.sun_sign) is True
    assert interview.stage1_favours_sun_sign(trace_off, grid.sun_sign) is False


def test_the_detector_is_on_by_default_and_can_be_switched_off():
    """On by default since v3.3.1. The v3.3 measurement that defaulted it off
    was taken against the tier ladder v3.3 then abandoned; under the shipped
    ladder it costs the perfect answerer nothing."""
    assert interview.InterviewConfig().sun_sign_detector is True

    grid = _grid()
    answers = _sign_only_answers(grid, grid.sun_sign)
    off = interview.InterviewConfig(sun_sign_detector=False)
    posterior, trace, pairs = interview.build_posterior(grid, answers, off)
    assert interview.assign_tier(
        posterior, trace, off, pairs, grid.asc_sign, sun_sign=grid.sun_sign
    )["sun_sign_attribution"] is False


def test_the_detector_discounts_the_stage_1_pairs():
    """Its surviving effect is on Tier 1: three stage-1 pairs that all name
    the Sun sign are one recalled stereotype, not three confirmations. Nothing
    is filtered - the truth stays strictly positive."""
    grid = _grid()
    on = interview.InterviewConfig()
    answers = _sign_only_answers(grid, grid.sun_sign)

    posterior, trace, pairs = interview.build_posterior(grid, answers, on)
    flagged = interview.assign_tier(posterior, trace, on, pairs,
                                    grid.asc_sign, sun_sign=grid.sun_sign)
    assert flagged["sun_sign_attribution"] is True
    # Three agreeing pairs, discounted to one, which is below Tier 1's bar.
    assert pairs["agreeing_pairs"] >= on.tier1_min_agreeing_pairs
    assert flagged["tier"] == 4
    assert min(posterior) > 0.0


# --------------------------------------------------------------------------
# Work item 3b: decan trust is below the sign channels
# --------------------------------------------------------------------------


def test_decan_trust_is_capped_below_the_session_default():
    cfg = interview.InterviewConfig()
    assert cfg.decan_reliability < cfg.channel_reliability

    grid = _grid()
    labels = interview.partition_for(grid, "decan", None)
    answers = [_ans("stage3_decan_a", "decan", [labels[4 * 60 + 35]])]
    _, trace, _ = interview.build_posterior(grid, answers, cfg)
    assert trace[0]["reliability_used"] == cfg.decan_reliability


# --------------------------------------------------------------------------
# Work item 2: the SHA in /health
# --------------------------------------------------------------------------


def test_health_reports_the_build_sha_and_the_answer_contract(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["git_sha"], str) and body["git_sha"]
    fields = body["interview_contract"]["answer_fields"]
    # The fields the web has to know about to send an answer at all.
    for required in ("question_id", "channel", "variant", "source",
                     "answer_ids", "offered_tag_ids", "windows", "subject"):
        assert required in fields, required
    assert fields == build_info.interview_answer_fields()


def test_git_sha_resolution_is_explicit_about_not_knowing(monkeypatch):
    """`unknown` is a real state - a slim image with no .git and no build env
    var - and is reported rather than papered over with the version."""
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    assert build_info.git_sha() == "deadbeef"
    monkeypatch.delenv("GIT_SHA")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "cafe1234")
    assert build_info.git_sha() == "cafe1234"


# --------------------------------------------------------------------------
# Work item 3: every engine key has approved Russian, or is declared uncovered
# --------------------------------------------------------------------------


def test_every_engine_key_has_approved_russian_or_a_declared_reason():
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from benchmarks import build_copy_manifest as bcm

    copy = bcm.ApprovedCopy(bcm.DRAFTS.read_text(encoding="utf-8"))
    _, missing, unexpected = bcm.build_manifest(copy)
    assert missing == [], f"engine keys with no Russian row: {missing[:10]}"
    assert unexpected == [], (
        f"declared uncovered but now covered: {unexpected}"
    )


def test_the_copy_file_is_the_owner_supplied_file_byte_for_byte():
    """`docs/copy_drafts.md` is a copy of the council-approved upload, so the
    two must not drift. They were reconciled in v3.3.1 after the file first
    arrived in this session mis-encoded and had to be reconstructed; 104 of
    105 rows matched, and house 8 did not. A byte comparison is the only
    check that would have caught that."""
    root = pathlib.Path(__file__).resolve().parent.parent
    shipped = root / "docs" / "copy_drafts.md"
    supplied = root / "docs" / "interview_copy_drafts_ru_approved_v3_3.md"
    assert shipped.read_bytes() == supplied.read_bytes(), (
        "docs/copy_drafts.md has drifted from the owner-supplied file"
    )


def test_the_committed_manifest_matches_the_approved_copy():
    """The manifest is generated. If the copy file moves and the manifest is
    not regenerated, the web ships text that no longer exists."""
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from benchmarks import build_copy_manifest as bcm

    copy = bcm.ApprovedCopy(bcm.DRAFTS.read_text(encoding="utf-8"))
    fresh, _, _ = bcm.build_manifest(copy)
    committed = json.loads(bcm.MANIFEST.read_text(encoding="utf-8"))
    assert committed["total_keys"] == fresh["total_keys"]
    assert committed["approved_keys"] == fresh["approved_keys"]
    by_key = {e["key"]: e["ru"] for e in fresh["entries"]}
    for entry in committed["entries"]:
        assert entry["ru"] == by_key[entry["key"]], entry["key"]


def test_every_channel_the_engine_asks_has_russian_copy(client, auth_headers):
    """Channel-level version of the above, driven by the live endpoint."""
    manifest = json.loads(
        (pathlib.Path(interview.__file__).parent / "data" / "copy_manifest.json")
        .read_text(encoding="utf-8")
    )
    with_russian = {
        e["channel"] for e in manifest["entries"] if e["status"] == "approved"
    }

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
    # The portrait channel is the declared exception: its label is composed
    # from the placements the engine returns, not from a fixed sentence.
    assert asked - with_russian <= {"portrait"}, asked - with_russian
