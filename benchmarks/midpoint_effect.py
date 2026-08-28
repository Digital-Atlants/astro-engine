"""Work item 5: the corpus numbers before and after the midpoint rule.

The rule only engages when the surviving candidate set is narrower than
`midpoint_below_minutes`. The place that happens on this corpus is after the
stage-(b) house-vector oracle from the ceiling appendix, where the survivor
set is a single contiguous run about 16 to 20 minutes wide. This measures the
argmax against the interval midpoint over exactly those sets.

    python benchmarks/midpoint_effect.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.harness import blocks, corpus, protocol  # noqa: E402
from benchmarks.oracle_ceiling import (  # noqa: E402
    _jd_at,
    house_vector,
    score_grid,
    true_house_vector,
)

OUT = pathlib.Path(__file__).resolve().parent / "midpoint_effect.json"


def main() -> None:
    rows = []
    for case in corpus.load_corpus():
        known = blocks.case_known_minute(case)
        sign_by_minute = blocks.sign_by_minute(case)
        true_sign = blocks.true_ascendant_sign(case)
        tv = true_house_vector(case)

        stage_a = [m for m in protocol.GRID_MINUTES if sign_by_minute[m] == true_sign]
        stage_b = [m for m in stage_a if house_vector(case, _jd_at(case, m)) == tv]
        if not stage_b:
            continue

        scores = score_grid(case, case["events"])
        argmax = max(stage_b, key=lambda m: (scores[m], -m))
        midpoint = stage_b[(len(stage_b) - 1) // 2]
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "survivors": len(stage_b),
                "window_minutes": len(stage_b) * protocol.STEP_MINUTES,
                "argmax_err": protocol.circular_error_minutes(argmax, known),
                "midpoint_err": protocol.circular_error_minutes(midpoint, known),
            }
        )
        print(
            f"  {case['case_id']:24} window {rows[-1]['window_minutes']:>3} "
            f"argmax {rows[-1]['argmax_err']:>4} midpoint {rows[-1]['midpoint_err']:>4}",
            flush=True,
        )

    def agg(rs):
        a = [r["argmax_err"] for r in rs]
        m = [r["midpoint_err"] for r in rs]
        return {
            "n": len(rs),
            "argmax": {
                "median": statistics.median(a),
                "mean": statistics.fmean(a),
                "hit_5": sum(1 for e in a if e <= 5) / len(a),
                "hit_15": sum(1 for e in a if e <= 15) / len(a),
            },
            "midpoint": {
                "median": statistics.median(m),
                "mean": statistics.fmean(m),
                "hit_5": sum(1 for e in m if e <= 5) / len(m),
                "hit_15": sum(1 for e in m if e <= 15) / len(m),
            },
            "midpoint_better": sum(1 for r in rs if r["midpoint_err"] < r["argmax_err"]),
            "argmax_better": sum(1 for r in rs if r["argmax_err"] < r["midpoint_err"]),
            "tie": sum(1 for r in rs if r["argmax_err"] == r["midpoint_err"]),
            "engages_below_26min": sum(1 for r in rs if r["window_minutes"] < 26),
        }

    out = {
        "all": agg(rows),
        "holdout": agg([r for r in rows if r["split"] == "holdout"]),
        "per_case": rows,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for scope in ("all", "holdout"):
        a = out[scope]
        print(f"\n=== {scope} (n={a['n']}) ===")
        print(
            f"before (argmax)   median {a['argmax']['median']:>5.1f}  mean "
            f"{a['argmax']['mean']:>5.1f}  <=5 {a['argmax']['hit_5']:.0%}  "
            f"<=15 {a['argmax']['hit_15']:.0%}"
        )
        print(
            f"after  (midpoint) median {a['midpoint']['median']:>5.1f}  mean "
            f"{a['midpoint']['mean']:>5.1f}  <=5 {a['midpoint']['hit_5']:.0%}  "
            f"<=15 {a['midpoint']['hit_15']:.0%}"
        )
        print(
            f"midpoint better in {a['midpoint_better']}, argmax better in "
            f"{a['argmax_better']}, tie {a['tie']}; rule engages in "
            f"{a['engages_below_26min']}/{a['n']}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
