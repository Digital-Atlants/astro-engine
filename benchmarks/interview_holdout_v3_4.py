"""v3.4: holdout at 40 seeds, before and after the Tier 2 change.

v3.3.1 reported G1 at 5.42% on holdout against 2.01% on the full corpus, from
26 runs over 12 charts. The spec calls that thin in both directions and asks
for it re-measured at 40 seeds per model per case, before any change and
after, with the adjacent-sign answerer's windows inspected if it is still the
driver.

The gates are evaluated **on holdout**, which is the v3.4 change: a number
computed on the split that was held back is the one that has not been looked
at while choices were being made. Full-corpus figures are reported beside it.

    python benchmarks/interview_holdout_v3_4.py --config baseline
    python benchmarks/interview_holdout_v3_4.py --config chosen
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks import interview_harness_v3_3 as h  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402

OUT_DIR = pathlib.Path(__file__).resolve().parent / "holdout_v3_4"
RUNS = 40

BASELINE = {"tier2_window_minutes": 90, "tier2_max_windows": 3,
            "tier2_mass": 0.60}


def adjacent_sign_windows(cases, cell: dict, runs: int = 10) -> dict:
    """Where the truth sits relative to the windows adjacent-sign is offered.

    It is the G1 driver on holdout and its Tier 1 windows contain the truth
    0% of the time, so the useful question is not *whether* it misses but by
    how much and in which direction - a near miss is a resolution problem, a
    whole-sign-block miss is the displacement the model is built from.
    """
    cfg = interview.InterviewConfig(decan_reliability=0.40, **cell)
    offsets, widths, tiers = [], [], collections.Counter()
    for case in cases:
        grid = interview.ChartGrid(
            dt.date.fromisoformat(case["birth_date"]),
            case["place"]["lat"], case["place"]["lon"], case["place"]["tz"],
            cfg.house_system)
        hh, mm = map(int, case["known_time"].split(":"))
        truth = hh * 60 + mm
        for k in range(runs):
            row = h.simulate(grid, truth, "adjacent_sign",
                             h._seed(case["case_id"], "adjacent_sign", k), cfg)
            tiers[row["tier"]] += 1
            if row["tier"] in (1, 2) and row["abs_error_minutes"] is not None:
                offsets.append(row["abs_error_minutes"])
                if row["shortlist_width_minutes"]:
                    widths.append(row["shortlist_width_minutes"])
    return {
        "n_delivered": len(offsets),
        "tier_counts": {str(k): v for k, v in sorted(tiers.items())},
        "median_abs_error_minutes": statistics.median(offsets) if offsets else None,
        "min_abs_error_minutes": min(offsets) if offsets else None,
        "fraction_within_120_minutes": (
            round(sum(1 for o in offsets if o <= 120) / len(offsets), 4)
            if offsets else None),
        "median_shortlist_minutes": statistics.median(widths) if widths else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="baseline")
    ap.add_argument("--width", type=int)
    ap.add_argument("--count", type=int)
    ap.add_argument("--mass", type=float)
    args = ap.parse_args()

    cell = dict(BASELINE)
    if args.width:
        cell["tier2_window_minutes"] = args.width
    if args.count:
        cell["tier2_max_windows"] = args.count
    if args.mass:
        cell["tier2_mass"] = args.mass

    cases = corpus.load_corpus()
    holdout = [c for c in cases if c["split"] == "holdout"]
    cfg = interview.InterviewConfig(decan_reliability=0.40, **cell)

    res_h = h.run(cfg, holdout, f"holdout-{args.config}", runs=RUNS)
    res_f = h.run(cfg, cases, f"full-{args.config}", runs=RUNS)
    gates_h, gates_f = h.gates(res_h), h.gates(res_f)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": args.config,
        "cell": cell,
        "runs_per_case": RUNS,
        "holdout": {"per_model": res_h["per_model"], "gates": gates_h},
        "full": {"per_model": res_f["per_model"], "gates": gates_f},
        "adjacent_sign_windows_holdout": adjacent_sign_windows(holdout, cell),
    }
    (OUT_DIR / f"{args.config}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for split, res, gates in (("holdout", res_h, gates_h), ("full", res_f, gates_f)):
        print(f"\n=== {args.config} / {split} ({RUNS} seeds) ===")
        for m in h.ANSWERERS:
            s = res["per_model"][m]
            print(f"{m:18} T1 {s['tier1_rate']:>6.1%} T2 {s['tier2_rate']:>6.1%} "
                  f"T4 {s['tier4_rate']:>6.1%} | G1 {s['tier1_wrong_window_rate']:>6.2%} "
                  f"G7 {s['tier2_wrong_window_rate']:>6.2%} | "
                  f"shortlist {str(s['tier2_median_shortlist_minutes']):>5} min "
                  f"T2-contains {str(s['tier2_contains_truth_rate']):>6}")
        print("--- gates ---")
        for name in h.PRIORITY_ORDER:
            g = gates[name]
            print(f"{name:20} {'PASS' if g['pass'] else 'FAIL'}")
    print("\nadjacent-sign on holdout:",
          json.dumps(payload["adjacent_sign_windows_holdout"], indent=2))
    print(f"\nwrote {OUT_DIR / (args.config + '.json')}")


if __name__ == "__main__":
    main()
