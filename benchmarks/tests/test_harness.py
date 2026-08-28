"""Self-tests for the benchmark harness.

Deliberately NOT under `tests/`: `pytest.ini` sets `testpaths = tests`, and the
shipped suite stays exactly as it was. Run these explicitly:

    pytest benchmarks/tests -q
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from benchmarks.harness import bias, corpus, metrics, protocol, vendor  # noqa: E402

CASES = corpus.load_corpus()


def test_corpus_is_all_aa_and_large_enough():
    assert len(CASES) >= 12
    assert {c["rodden_rating"] for c in CASES} == {"AA"}
    for c in CASES:
        assert c["source_url"].startswith("http")
        assert 6 <= len(c["events"]) <= 12


def test_corpus_spread_rules():
    s = corpus.spread_summary(CASES)
    assert s["night_births"] >= 4, s
    assert s["high_latitude"] >= 4, s
    # Known shortfall, reported in RESULTS.md rather than papered over. This
    # asserts the documented state so a later corpus addition trips the test
    # and forces the report to be updated with it.
    assert s["near_equator"] == 0, s


def test_spread_flags_match_the_data():
    for c in CASES:
        hh = int(c["known_time"].split(":")[0])
        assert c["spread_flags"]["night_birth"] == (0 <= hh < 6)
        assert c["spread_flags"]["high_latitude"] == (abs(c["place"]["lat"]) > 45)
        assert c["spread_flags"]["near_equator"] == (abs(c["place"]["lat"]) <= 10)
        mm = int(c["known_time"].split(":")[1])
        assert c["known_time_is_round"] == (mm in (0, 15, 30, 45))


def test_circular_error_wraps_around_midnight():
    assert protocol.circular_error_minutes(5, 1435) == 10
    assert protocol.circular_error_minutes(0, 720) == 720
    assert protocol.circular_error_minutes(100, 100) == 0


def test_vendor_endpoint_time_2400_folds_to_zero():
    assert protocol.time_to_minute("24:00") == 0
    assert protocol.time_to_minute("00:00") == 0


def test_grid_matches_between_arms():
    # Arm A's window and the union of the vendor's two halves must cover the
    # same 360 candidate times, or the comparison is not like-for-like.
    assert len(protocol.GRID_MINUTES) == 360
    union = set()
    for half in protocol.VENDOR_HALVES:
        anchor = half["anchor_hour"] * 60
        d = half["delta_minutes"]
        union |= {
            m % 1440
            for m in range(anchor - d, anchor + d + 1, protocol.STEP_MINUTES)
        }
    assert union == set(protocol.GRID_MINUTES)


def test_null_shuffle_preserves_everything_but_the_date():
    case = CASES[0]
    lo, hi = case.lifespan_bounds()
    shuffled = protocol.shuffled_events(case["events"], lo, hi, seed=1)
    assert len(shuffled) == len(case["events"])
    assert [e["type"] for e in shuffled] == [e["type"] for e in case["events"]]
    assert [e["date_precision"] for e in shuffled] == [
        e["date_precision"] for e in case["events"]
    ]
    for original, drawn in zip(case["events"], shuffled):
        d = dt.date.fromisoformat(drawn["date"])
        assert lo <= d <= hi
        if original["date_precision"] == "month":
            assert d.day == 1
        if original["date_precision"] == "year":
            assert (d.month, d.day) == (1, 1)


def test_null_shuffle_is_deterministic():
    case = CASES[0]
    lo, hi = case.lifespan_bounds()
    assert protocol.shuffled_events(case["events"], lo, hi, 7) == protocol.shuffled_events(
        case["events"], lo, hi, 7
    )


def test_vendor_request_never_leaks_the_known_time():
    """The anchors are fixed constants; no field may depend on the answer."""
    case = CASES[0]
    for half in protocol.VENDOR_HALVES:
        body = vendor.build_request(case, case["events"], half)
        bd = body["subject"]["birth_data"]
        assert (bd["hour"], bd["minute"], bd["second"]) == (half["anchor_hour"], 0, 0)
        assert body["time_search"]["delta_minutes"] == half["delta_minutes"]
        blob = json.dumps(body)
        assert case["known_time"] not in blob
        assert case["known_time"].replace(":", "") not in blob


def test_vendor_request_carries_no_credential():
    case = CASES[0]
    blob = json.dumps(vendor.build_request(case, case["events"], protocol.VENDOR_HALVES[0]))
    assert "ask_" not in blob
    assert "Authorization" not in blob
    assert "Bearer" not in blob


def test_cached_fixtures_carry_no_credential():
    for path in vendor.FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "ask_" not in text, path
        assert "Bearer" not in text, path
        assert "Authorization" not in text, path


def test_fixtures_use_the_normalised_score_key():
    """The vendor's own score field name trips the repo's astrology-only guard.

    It is renamed on ingest rather than the guard being weakened, so no
    committed fixture may carry the vendor spelling.
    """
    for path in vendor.FIXTURE_DIR.glob("*.json"):
        assert vendor.VENDOR_SCORE_FIELD not in path.read_text(encoding="utf-8"), path


def test_missing_key_fails_loudly_by_name(monkeypatch):
    monkeypatch.delenv(vendor.API_KEY_ENV, raising=False)
    with pytest.raises(vendor.VendorKeyMissing) as exc:
        vendor.api_key()
    assert vendor.API_KEY_ENV in str(exc.value)


def test_every_event_type_maps_to_a_vendor_category():
    assert set(vendor.CATEGORY_MAP) == corpus.VALID_TYPES
    assert set(vendor.PRECISION_MAP) == corpus.VALID_PRECISION


def test_arm_e_returns_the_same_time_regardless_of_case():
    from benchmarks.harness import arm_e

    runs = [arm_e.run(c, arm_e.NOON_MINUTE) for c in CASES]
    assert {r["returned_time"] for r in runs} == {"12:00"}
    assert all(r["peak_over_mean"] is None for r in runs)
    assert all(r["score_by_minute"] == {} for r in runs)


def test_arm_e_corpus_median_is_on_the_grid():
    from benchmarks.harness import arm_e

    m = arm_e.corpus_median_minute(CASES)
    assert m in protocol.GRID_MINUTES
    # Half the corpus is born before it and half after, by construction.
    known = sorted(c.known_minute for c in CASES)
    assert known[len(known) // 2 - 1] <= m <= known[len(known) // 2]


def test_percentile_and_hit_rates():
    assert metrics.percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    assert metrics.percentile([], 0.5) is None
    records = [{"abs_error_minutes": e} for e in (0, 3, 10, 100)]
    t = metrics.accuracy_table(records)
    assert t["hits_2"] == 1 and t["hits_5"] == 2 and t["hits_15"] == 3
    assert t["hit_rate_5"] == 0.5


def test_signal_vs_null_auc_is_chance_for_identical_distributions():
    same = [{"peak_over_mean": v} for v in (1.0, 2.0, 3.0, 4.0)]
    s = metrics.signal_vs_null(same, list(same))
    assert s["auc"] == pytest.approx(0.5)


def test_ascendant_speed_profile_is_not_flat():
    """The bias check is only meaningful if Ascendant speed actually varies."""
    profile = bias.hour_speed_profile(CASES[0])
    assert len(profile) == 24
    assert max(profile.values()) > 1.5 * min(profile.values())


def test_arm_a_uses_shipped_defaults():
    from astro_engine.schemas import RectificationConfig

    from benchmarks.harness import arm_a

    req = arm_a.build_request(CASES[0], CASES[0]["events"])
    assert req.config.model_dump() == RectificationConfig().model_dump()
    assert req.candidate_window.step_minutes == protocol.STEP_MINUTES
