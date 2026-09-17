"""v3.4: the Tier 2 sweep - width cap x count cap x mass, train only.

G7 (the truth outside every offered window) has failed on two seed sets and
all three splits, and v3.3.1 established that `tier2_chance_p` cannot move it:
zero of 593 training Tier 2 sessions lie in its swept band. The levers that
remain are the ones this script sweeps.

**What the width cap means here.** `tier2_window_minutes` is the widest single
window Tier 2 will admit before refusing. It is an admission limit, not a
construction parameter - the windows themselves come from the posterior at
`tier2_mass`, and raising that mass is what makes them wider. So the two
interact in the intended direction: raise the mass to widen the windows so
they contain the truth, and set the cap to say how wide is still an answer
rather than a shrug.

**Why G9 exists.** Without a usefulness bound every G7 failure has the same
degenerate fix - widen until the windows contain everything. G9 caps the
*total* width across the whole shortlist for the perfect answerer at 90
minutes, because three 40-minute windows are a two-hour answer however they
are presented.

Discipline: train only (29 cases); the grid is frozen; the holdout split is
scored once, afterwards, by `interview_holdout_v3_4.py`. The pre-v3.4
configuration (cap 90, count 3, mass 0.60) is reported as a reference row but
is not a candidate - the spec fixed the grid at 30/40/50.

    python benchmarks/interview_tier2_sweep_v3_4.py --shard 0 --of 6
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks import interview_harness_v3_3 as h  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402

OUT_DIR = pathlib.Path(__file__).resolve().parent / "tier2_sweep_v3_4"

# Frozen before the sweep ran, in the spec's order of preference.
WIDTH_CAPS = (30, 40, 50)
COUNT_CAPS = (2, 3)
MASSES = (0.60, 0.70, 0.80)
RUNS = 20

# The sweep only needs the models the two gates are defined over.
SWEEP_MODELS = ("perfect", "iid_noisy", "adjacent_sign", "random",
                "dont_know_heavy", "sun_attributor")

BASELINE = {"tier2_window_minutes": 90, "tier2_max_windows": 3,
            "tier2_mass": 0.60}


def cells() -> list[dict]:
    return [
        {"tier2_window_minutes": w, "tier2_max_windows": c, "tier2_mass": m}
        for w, c, m in itertools.product(WIDTH_CAPS, COUNT_CAPS, MASSES)
    ]


def label(cell: dict) -> str:
    return (f"w{cell['tier2_window_minutes']}"
            f"_n{cell['tier2_max_windows']}"
            f"_m{cell['tier2_mass']:.2f}")


def evaluate(cases, cell: dict, runs: int) -> dict:
    cfg = interview.InterviewConfig(decan_reliability=0.40, **cell)
    res = h.run(cfg, cases, label(cell), models=SWEEP_MODELS, runs=runs)
    pm = res["per_model"]
    g7 = {m: pm[m]["tier2_wrong_window_rate"] for m in SWEEP_MODELS}
    g1 = {m: pm[m]["tier1_wrong_window_rate"] for m in SWEEP_MODELS}
    return {
        "cell": cell,
        "G7_per_model": g7,
        "G7_worst": max(g7.values()),
        "G7_pass": all(v <= 0.05 for v in g7.values()),
        "G1_per_model": g1,
        "G1_worst": max(g1.values()),
        "G1_pass": all(v <= 0.05 for v in g1.values()),
        "G9_perfect_median_shortlist": pm["perfect"]["tier2_median_shortlist_minutes"],
        "G9_pass": (pm["perfect"]["tier2_median_shortlist_minutes"] or 0) <= 90,
        "G9_per_model": {
            m: pm[m]["tier2_median_shortlist_minutes"] for m in SWEEP_MODELS
        },
        "G3_random_tier4": pm["random"]["tier4_rate"],
        "G3_pass": pm["random"]["tier4_rate"] >= 0.90,
        "G2_perfect_tier1": pm["perfect"]["tier1_rate"],
        "G5_perfect": pm["perfect"]["sign_recovery_rate"],
        "G5_iid": pm["iid_noisy"]["sign_recovery_rate"],
        "G4_median_questions": pm["perfect"]["median_questions"],
        "perfect_tier2_rate": pm["perfect"]["tier2_rate"],
        "perfect_tier2_contains": pm["perfect"]["tier2_contains_truth_rate"],
        "dont_know_heavy_tier2": pm["dont_know_heavy"]["tier2_rate"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--baseline", action="store_true",
                    help="score the pre-v3.4 configuration as a reference row")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = [c for c in corpus.load_corpus() if c["split"] == "train"]

    todo = [BASELINE] if args.baseline else cells()[args.shard::args.of]
    for cell in todo:
        row = evaluate(cases, cell, RUNS)
        name = "baseline" if args.baseline else label(cell)
        (OUT_DIR / f"{name}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{name:20} G7 {row['G7_worst']:>6.2%} {'ok' if row['G7_pass'] else 'FAIL'} "
              f"| G1 {row['G1_worst']:>6.2%} {'ok' if row['G1_pass'] else 'FAIL'} "
              f"| G9 {row['G9_perfect_median_shortlist']} min "
              f"{'ok' if row['G9_pass'] else 'FAIL'} "
              f"| G2 {row['G2_perfect_tier1']:>6.1%} "
              f"| dkh-T2 {row['dont_know_heavy_tier2']:>6.1%}")


if __name__ == "__main__":
    main()
