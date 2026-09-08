"""The one permitted retune of v3-specific parameters, on train only.

Frozen defaults failed G1 (adjacent-sign 5.37% > 5%), G2 (perfect Tier 1
78.1% < 90%), G4 (median 10 questions > 9) and G5 (perfect sign recovery
75.6% < 90%). The spec allows exactly one retune of the v3 parameters,
searched on the 29-case train split and evaluated once on the 12-case
holdout.

Only the parameters v3 introduced are in the search: how many trait rounds
stage 1 may take, how far the sign mass must concentrate before it stops, and
how many repeat pairs the session schedules. Tier thresholds and the trust
default are NOT touched - they belong to v1/v2 and their retunes are spent or
deliberately unspent.

    python benchmarks/interview_retune_v3.py
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402
from benchmarks.interview_harness_v3 import gates, run  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "interview_retune_v3.json"

GRID = [
    {"max_trait_questions": t, "sign_mass_stop": s, "repeat_pairs": p}
    for t, s, p in itertools.product((2, 3, 4), (0.45, 0.55), (2, 3))
]


def score(g: dict) -> tuple:
    """Rank by gates passed, then by G1 margin - safety first."""
    passed = sum(
        1 for k in ("G1_safety", "G2_usefulness", "G3_refusal", "G4_cost",
                    "G5_sign_recovery")
        if g[k]["pass"]
    )
    g1_margin = 0.05 - max(g["G1_safety"]["per_model"].values())
    g5_margin = g["G5_sign_recovery"]["perfect"] - 0.90
    g4_margin = 9 - g["G4_cost"]["median_questions"]
    return (passed, g1_margin, g4_margin, g5_margin)


def main() -> None:
    train = corpus.load_corpus(split="train")
    holdout = corpus.load_corpus(split="holdout")

    log, best = [], None
    for cand in GRID:
        cfg = interview.InterviewConfig(**cand)
        res = run(cfg, train, f"train {cand}")
        g = gates(res)
        entry = {
            "candidate": cand,
            "train_gates": {
                k: g[k] for k in ("G1_safety", "G2_usefulness", "G3_refusal",
                                  "G4_cost", "G5_sign_recovery")
            },
            "score": score(g),
        }
        log.append(entry)
        print(
            f"  {cand}  passed={entry['score'][0]} "
            f"G1worst={max(g['G1_safety']['per_model'].values()):.3f} "
            f"G4q={g['G4_cost']['median_questions']} "
            f"G5={g['G5_sign_recovery']['perfect']:.3f}",
            flush=True,
        )
        if best is None or entry["score"] > best["score"]:
            best = entry

    chosen = best["candidate"]
    print(f"\nchosen on train: {chosen}")

    cfg = interview.InterviewConfig(**chosen)
    hold = run(cfg, holdout, "holdout")
    full = run(cfg, corpus.load_corpus(), "all-41")

    out = {
        "reason_for_retune": (
            "frozen v3 defaults failed G1 (adjacent_sign 5.37% > 5%), "
            "G2 (perfect Tier 1 78.05% < 90%), G4 (median 10 questions > 9) "
            "and G5 (perfect sign recovery 75.6% < 90%)"
        ),
        "search_space": GRID,
        "searched_on": "train (29 cases) only",
        "parameters_in_scope": [
            "max_trait_questions", "sign_mass_stop", "repeat_pairs"
        ],
        "train_log": log,
        "chosen": chosen,
        "holdout_gates": gates(hold),
        "holdout_per_model": hold["per_model"],
        "all41_gates": gates(full),
        "all41_per_model": full["per_model"],
        "retunes_used": 1,
        "retunes_remaining": 0,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for scope, g in (("holdout", out["holdout_gates"]), ("all 41", out["all41_gates"])):
        print(f"\n=== {scope} ===")
        for k in ("G1_safety", "G2_usefulness", "G3_refusal", "G4_cost",
                  "G5_sign_recovery"):
            print(f"{k}: {'PASS' if g[k]['pass'] else 'FAIL'}  {g[k]}")
        print(f"impostor {g['impostor_tier1_wrong_window_rate']:.2%}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
