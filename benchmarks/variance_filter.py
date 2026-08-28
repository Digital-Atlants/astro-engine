"""Work item 2: the within-block variance filter.

For every candidate evaluator, score every candidate time inside the *correct*
rising-sign block and report how much the value moves. An evaluator that is
flat inside the block cannot resolve sub-sign position, however sound it is
astrologically, so this table decides what gets built.

    python benchmarks/variance_filter.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.harness import blocks, corpus, evaluators  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "variance_table.json"

# An evaluator needs to move enough inside the block to reorder candidates.
# CV is scale-free, so the threshold is on CV; `distinct_frac` is reported
# alongside because a high CV driven by one outlier minute is not resolution.
CV_INCLUDE = 0.05


def summarise(series: list[float]) -> dict:
    mean = statistics.fmean(series)
    sd = statistics.stdev(series) if len(series) > 1 else 0.0
    distinct = len(set(round(v, 9) for v in series))
    return {
        "mean": mean,
        "sd": sd,
        "cv": (sd / mean) if mean > 0 else (float("inf") if sd > 0 else 0.0),
        "range": max(series) - min(series),
        "distinct_values": distinct,
        "distinct_frac": distinct / len(series),
    }


def main() -> None:
    cases = corpus.load_corpus(split="train")  # parameters are chosen on train only
    rows: dict[str, list[dict]] = {name: [] for name in evaluators.EVALUATORS}

    for case in cases:
        block = blocks.correct_block_minutes(case)
        for name in evaluators.EVALUATORS:
            hs = "placidus" if name == "quadrant_cusps" else "whole_sign"
            series = evaluators.score_series(case, name, block, hs)
            rows[name].append(summarise(series))
        print(f"  {case['case_id']} done ({len(block)} block candidates)", flush=True)

    table = []
    for name, per_case in rows.items():
        cvs = [r["cv"] for r in per_case if r["cv"] != float("inf")]
        flat = sum(1 for r in per_case if r["distinct_values"] <= 1)
        median_cv = statistics.median(cvs) if cvs else 0.0
        table.append(
            {
                "evaluator": name,
                "median_cv": median_cv,
                "mean_distinct_frac": statistics.fmean(
                    r["distinct_frac"] for r in per_case
                ),
                "cases_flat_in_block": flat,
                "cases": len(per_case),
                "median_range": statistics.median(r["range"] for r in per_case),
                "include": median_cv >= CV_INCLUDE and flat < len(per_case),
            }
        )
    table.sort(key=lambda r: -r["median_cv"])

    OUT.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print()
    hdr = f"{'evaluator':24} {'median CV':>10} {'distinct':>9} {'flat':>6} {'range':>9}  decision"
    print(hdr)
    print("-" * len(hdr))
    for r in table:
        print(
            f"{r['evaluator']:24} {r['median_cv']:>10.3f} "
            f"{r['mean_distinct_frac']:>9.2f} "
            f"{r['cases_flat_in_block']:>3}/{r['cases']:<2} "
            f"{r['median_range']:>9.3f}  "
            f"{'INCLUDE' if r['include'] else 'EXCLUDE'}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
