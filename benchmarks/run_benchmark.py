"""Run the arms and write benchmarks/RESULTS.md.

    python benchmarks/run_benchmark.py --arms a,c,e            # free, no network
    RECT_VENDOR_API_KEY=... python benchmarks/run_benchmark.py --arms a,b,c,e
    python benchmarks/run_benchmark.py --arms a,b,c,e --offline  # replay fixtures

Arms: A ours, B vendor, C null control (both engines), E constant-guess
baseline. Only B touches the network or spends credits.

Nothing here tunes the engine. Arm A calls `score_rectification` with a
default-constructed config and reports what comes back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.harness import (  # noqa: E402
    arm_a,
    arm_e,
    corpus,
    metrics,
    protocol,
    report,
    vendor,
)

RESULTS_JSON = pathlib.Path(__file__).resolve().parent / "results.json"
RESULTS_MD = pathlib.Path(__file__).resolve().parent / "RESULTS.md"


def _measure(run: dict, case: dict, *, arm: str, label: str, shuffle: int | None) -> dict:
    known = case.known_minute
    record = dict(run)
    record.update(
        {
            "case_id": case["case_id"],
            "name": case["name"],
            "arm": arm,
            "label": label,
            "shuffle": shuffle,
            "known_time": case["known_time"],
            "abs_error_minutes": protocol.circular_error_minutes(
                run["returned_minute"], known
            ),
            "known_time_on_grid": protocol.known_time_on_grid(known),
            "grid_floor_error_minutes": protocol.grid_floor_error(known),
            "known_time_percentile": _known_percentile(run["score_by_minute"], known),
        }
    )
    record.pop("score_by_minute", None)
    return record


def _known_percentile(scores: dict[int, float], known_minute: int) -> float | None:
    """Where the true birth time ranks in the engine's own score distribution.

    Argmax accuracy is a coarse instrument on twelve cases: an engine can carry
    real signal and still miss the top slot. This asks the softer question -
    of all 360 candidates, what fraction score below the true time? 0.50 is
    chance, 1.00 means the true time is the outright peak.
    """
    if not scores:
        return None
    nearest = min(scores, key=lambda m: protocol.circular_error_minutes(m, known_minute))
    target = scores[nearest]
    below = sum(1 for v in scores.values() if v < target)
    ties = sum(1 for v in scores.values() if v == target)
    return (below + 0.5 * ties) / len(scores)


def run_arm_a(cases, null_shuffles: int) -> tuple[list[dict], list[dict]]:
    real, null = [], []
    for case in cases:
        real.append(
            _measure(arm_a.run(case, case["events"]), case, arm="A", label="real", shuffle=None)
        )
        lo, hi = case.lifespan_bounds()
        for s in range(null_shuffles):
            events = protocol.shuffled_events(case["events"], lo, hi, seed=hash_seed(case, s))
            null.append(
                _measure(arm_a.run(case, events), case, arm="C-ours", label="null", shuffle=s)
            )
        print(f"  arm A {case['case_id']}: {real[-1]['abs_error_minutes']:>4} min", flush=True)
    return real, null


def run_arm_b(cases, null_cases, *, offline: bool) -> tuple[list[dict], list[dict], dict]:
    real, null = [], []
    budget = {"requests": 0, "credits": 0}
    for case in cases:
        run = vendor.run(case, case["events"], offline=offline)
        budget["requests"] += run["requests_made"]
        budget["credits"] += run["credits_used"]
        real.append(_measure(run, case, arm="B", label="real", shuffle=None))
        print(f"  arm B {case['case_id']}: {real[-1]['abs_error_minutes']:>4} min", flush=True)
    for case in null_cases:
        lo, hi = case.lifespan_bounds()
        events = protocol.shuffled_events(case["events"], lo, hi, seed=hash_seed(case, 0))
        run = vendor.run(case, events, offline=offline)
        budget["requests"] += run["requests_made"]
        budget["credits"] += run["credits_used"]
        null.append(_measure(run, case, arm="C-vendor", label="null", shuffle=0))
        print(f"  arm C/vendor {case['case_id']}", flush=True)
    return real, null, budget


def hash_seed(case: dict, shuffle: int) -> int:
    """Deterministic per (case, shuffle) seed, so null runs are reproducible.

    Not `hash()`: string hashing is salted per process, which would give a
    different null arm on every run.
    """
    blob = f"null|{case['case_id']}|{shuffle}".encode()
    return int.from_bytes(hashlib.sha256(blob).digest()[:4], "big")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--arms", default="a,c,e", help="comma-separated subset of a,b,c,e"
    )
    ap.add_argument("--offline", action="store_true", help="Arm B replays fixtures only")
    ap.add_argument(
        "--vendor-null-cases",
        type=int,
        default=4,
        help="how many cases get a vendor null run (each costs 2 requests)",
    )
    args = ap.parse_args()
    arms = {a.strip().lower() for a in args.arms.split(",") if a.strip()}

    cases = corpus.load_corpus()
    if "b" in arms:
        # One protocol means one case set. Arm B has cached fixtures for the
        # original 12 cases only, so every arm is scoped to those when the
        # vendor arm is requested; see vendor.cases_with_fixtures().
        covered = vendor.cases_with_fixtures()
        scoped = [c for c in cases if c["case_id"] in covered]
        if scoped:
            print(
                f"arm B requested: scoping all arms to the {len(scoped)} cases "
                f"with cached vendor fixtures (corpus has {len(cases)})"
            )
            cases = scoped
    print(f"corpus: {json.dumps(corpus.spread_summary(cases))}")

    out = {
        "corpus": corpus.spread_summary(cases),
        "protocol": {
            "window": f"{protocol.WINDOW_START}-{protocol.WINDOW_END}",
            "step_minutes": protocol.STEP_MINUTES,
            "grid_points": len(protocol.GRID_MINUTES),
            "null_shuffles_arm_a": protocol.NULL_SHUFFLES_ARM_A,
        },
        "arm_a": [],
        "arm_c_ours": [],
        "arm_b": [],
        "arm_c_vendor": [],
        "arm_e_noon": [],
        "arm_e_median": [],
        "arm_e_median_minute": arm_e.corpus_median_minute(cases),
        "vendor_budget": {"requests": 0, "credits": 0},
    }

    if "a" in arms or "c" in arms:
        print("running arm A + arm C (ours)...")
        shuffles = protocol.NULL_SHUFFLES_ARM_A if "c" in arms else 0
        out["arm_a"], out["arm_c_ours"] = run_arm_a(cases, shuffles)

    if "e" in arms:
        print("running arm E (constant-guess baselines)...")
        median_minute = out["arm_e_median_minute"]
        for label, key, minute in (
            ("noon", "arm_e_noon", arm_e.NOON_MINUTE),
            ("corpus-median", "arm_e_median", median_minute),
        ):
            out[key] = [
                _measure(arm_e.run(c, minute), c, arm="E", label=label, shuffle=None)
                for c in cases
            ]
            t = metrics.accuracy_table(out[key])
            print(
                f"  arm E {label} ({protocol.minute_to_time(minute)}): "
                f"median={t['median_abs_error']:.0f} min"
            )

    if "b" in arms:
        print("running arm B + arm C (vendor)...")
        null_cases = cases[: args.vendor_null_cases] if "c" in arms else []
        out["arm_b"], out["arm_c_vendor"], this_run = run_arm_b(
            cases, null_cases, offline=args.offline
        )
        out["vendor_budget"] = {**vendor.spent_to_date(), "this_run": this_run}

    RESULTS_JSON.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS_JSON}")

    RESULTS_MD.write_text(report.build(out, cases), encoding="utf-8")
    print(f"wrote {RESULTS_MD}")

    for arm, key in (("A (ours)", "arm_a"), ("B (vendor)", "arm_b")):
        if out[key]:
            t = metrics.accuracy_table(out[key])
            print(
                f"arm {arm}: n={t['n']} +/-5 ={t['hit_rate_5']:.0%} "
                f"median={t['median_abs_error']:.0f} min"
            )


if __name__ == "__main__":
    main()
