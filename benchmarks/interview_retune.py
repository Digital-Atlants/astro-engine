"""The one permitted retune of T1/T2/P1, on train only.

The frozen defaults failed G1 (iid-noisy issued Tier 1 with the truth outside
the window 7.8% of the time, over the 5% bar) and G2 (the perfect answerer
reached Tier 1 in 87.8% of runs, under the 90% bar). The spec allows exactly
one retune, searched on the 29-case train split and then evaluated once on the
12-case holdout.

The two failures pull in opposite directions - G1 wants Tier 1 harder to
reach, G2 wants it easier - so the lever has to be the one that separates good
answers from bad ones rather than the one that trades them off. That lever is
cross-channel agreement: a perfect answerer's channels genuinely agree, while a
noisy answerer's agreement is occasional and accidental. Tightening
`tier1_chance_p` should cut wrong Tier 1s harder than right ones, and
`tier1_mass` can then be relaxed to recover the Tier 1 rate.

    python benchmarks/interview_retune.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402
from benchmarks.interview_harness import gates, run  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "interview_retune.json"

# A deliberately small, pre-declared search. Two parameters, three values
# each, in the directions argued above. Nothing else is touched.
CANDIDATES = [
    {"tier1_chance_p": p, "tier1_mass": m}
    for p in (0.05, 0.01, 0.002)
    for m in (0.60, 0.50, 0.40)
]


def score(g: dict) -> tuple:
    """Rank by gates passed, then by margin. G1 is the gate that matters."""
    passed = sum(
        1 for k in ("G1_safety", "G2_usefulness", "G3_refusal") if g[k]["pass"]
    )
    g1_margin = 0.05 - max(g["G1_safety"]["per_model_tier1_wrong_window_rate"].values())
    g2_margin = g["G2_usefulness"]["tier1_rate"] - 0.90
    g3_margin = g["G3_refusal"]["tier3_or_4_rate"] - 0.95
    return (passed, g1_margin, g2_margin, g3_margin)


def main() -> None:
    train = corpus.load_corpus(split="train")
    holdout = corpus.load_corpus(split="holdout")

    log = []
    best = None
    for cand in CANDIDATES:
        cfg = interview.InterviewConfig(**cand)
        res = run(cfg, train, f"train {cand}")
        g = gates(res)
        entry = {
            "candidate": cand,
            "train_gates": {
                k: g[k] for k in ("G1_safety", "G2_usefulness", "G3_refusal")
            },
            "train_score": score(g),
        }
        log.append(entry)
        print(
            f"  {cand}  passed={entry['train_score'][0]}  "
            f"G1max={max(g['G1_safety']['per_model_tier1_wrong_window_rate'].values()):.3f}  "
            f"G2 T1={g['G2_usefulness']['tier1_rate']:.3f}  "
            f"G3={g['G3_refusal']['tier3_or_4_rate']:.3f}",
            flush=True,
        )
        if best is None or entry["train_score"] > best["train_score"]:
            best = entry

    chosen = best["candidate"]
    print(f"\nchosen on train: {chosen}")

    cfg = interview.InterviewConfig(**chosen)
    hold = run(cfg, holdout, "holdout")
    hold_gates = gates(hold)
    full = run(cfg, corpus.load_corpus(), "all-41")
    full_gates = gates(full)

    hold.pop("_rows", None)
    full.pop("_rows", None)
    out = {
        "reason_for_retune": (
            "frozen defaults failed G1 (iid_noisy Tier-1 wrong-window 7.8% > 5%) "
            "and G2 (perfect Tier-1 rate 87.8% < 90%)"
        ),
        "search_space": CANDIDATES,
        "searched_on": "train (29 cases) only",
        "train_log": log,
        "chosen": chosen,
        "holdout_gates": hold_gates,
        "holdout_per_model": hold["per_model"],
        "all41_gates": full_gates,
        "all41_per_model": full["per_model"],
        "retunes_used": 1,
        "retunes_remaining": 0,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== holdout gates (the evaluation that counts) ===")
    for k in ("G1_safety", "G2_usefulness", "G3_refusal"):
        print(f"{k}: {'PASS' if hold_gates[k]['pass'] else 'FAIL'}")
    print(f"impostor floor (holdout): {hold_gates['impostor_tier1_wrong_window_rate']:.2%}")
    print("\n=== all 41 gates ===")
    for k in ("G1_safety", "G2_usefulness", "G3_refusal"):
        print(f"{k}: {'PASS' if full_gates[k]['pass'] else 'FAIL'}  {full_gates[k]}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
