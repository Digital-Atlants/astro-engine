"""Give each addition its best shot before reverting it.

An addition could fail the ablation simply because its weight was wrong. This
sweeps each new technique's weight on `train` only, takes the weight that
minimises the in-block median error there, and then evaluates that single
choice once on `holdout`. Tuning on train and measuring on holdout is the
whole point of the split; a weight picked on holdout would make the gate
meaningless.

    python benchmarks/weight_sweep.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.ablation import BASE, evaluate, run_case  # noqa: E402
from benchmarks.harness import blocks, corpus, protocol  # noqa: E402
from benchmarks.harness.candidate_engine import (  # noqa: E402
    CandidateConfig as RectificationConfig,
)

OUT = pathlib.Path(__file__).resolve().parent / "weight_sweep.json"

WEIGHTS = [0.2, 0.5, 1.0, 1.4, 2.0, 3.0]

CANDIDATES = [
    ("quadrant_cusps (placidus)", "quadrant_cusps", {"house_system": "placidus"}),
    ("directed_angles", "directed_angles", {}),
    ("primary_directions (ptolemy)", "primary_directions", {"direction_key": "ptolemy"}),
    ("primary_directions (naibod)", "primary_directions", {"direction_key": "naibod"}),
    ("eclipse_on_angle", "eclipse_on_angle", {}),
]


def cfg_for(tech: str, weight: float, extra: dict) -> RectificationConfig:
    weights = dict(RectificationConfig().technique_weights)
    weights[tech] = weight
    return RectificationConfig(
        techniques=BASE + [tech],
        technique_weights=weights,
        event_technique_matching=False,
        permutation_trials=0,
        **extra,
    )


def train_median(cases, cfg) -> float:
    errs = []
    for case in cases:
        scores = run_case(case, cfg)
        block = blocks.correct_block_minutes(case)
        errs.append(
            protocol.circular_error_minutes(
                blocks.best_in_block(scores, block), blocks.case_known_minute(case)
            )
        )
    return statistics.median(errs)


def main() -> None:
    train = corpus.load_corpus(split="train")
    holdout = corpus.load_corpus(split="holdout")
    baseline_cfg = RectificationConfig(
        techniques=BASE, event_technique_matching=False, permutation_trials=0
    )
    base_train = train_median(train, baseline_cfg)
    base_hold = evaluate(holdout, baseline_cfg)
    print(f"baseline: train {base_train:.1f}  holdout {base_hold['median_in_block']:.1f}\n")

    results = {
        "baseline": {
            "train_median": base_train,
            "holdout": {k: v for k, v in base_hold.items() if k != "errors_in_block"},
        },
        "swept": {},
    }

    for label, tech, extra in CANDIDATES:
        curve = {}
        for w in WEIGHTS:
            m = train_median(train, cfg_for(tech, w, extra))
            curve[w] = m
            print(f"  {label:30} w={w:<4} train median {m:>6.1f}", flush=True)
        best_w = min(curve, key=lambda w: (curve[w], w))
        hold = evaluate(holdout, cfg_for(tech, best_w, extra))
        results["swept"][label] = {
            "train_curve": curve,
            "best_weight_on_train": best_w,
            "train_median_at_best": curve[best_w],
            "holdout": {k: v for k, v in hold.items() if k != "errors_in_block"},
            "beats_baseline_on_holdout": hold["median_in_block"]
            < base_hold["median_in_block"],
        }
        print(
            f"  -> {label}: best w={best_w} (train {curve[best_w]:.1f}), "
            f"holdout {hold['median_in_block']:.1f} "
            f"{'BEATS' if results['swept'][label]['beats_baseline_on_holdout'] else 'does not beat'} "
            f"baseline {base_hold['median_in_block']:.1f}\n",
            flush=True,
        )

    OUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
