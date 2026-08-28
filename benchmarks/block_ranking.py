"""Block ranking and the in-block null. Measurement only.

Two questions, asked of the shipped engine exactly as it is:

1. Does the true block rank above chance when blocks are ranked by their peak
   score? Asked twice - for the twelve two-hour clock blocks, and for the
   twelve rising-sign blocks - and for real events against shuffled dates.

2. Inside the correct rising-sign block, do real events beat shuffled dates at
   all? With a blind uniform pick inside the same block as the floor.

Nothing here tunes anything. The engine runs at its shipped defaults with the
permutation null switched off, because the null cannot move the argmax and
this script only reads the argmax.

    python benchmarks/block_ranking.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine.rectification import score_rectification  # noqa: E402
from astro_engine.schemas import (  # noqa: E402
    CandidateWindow,
    Place,
    RectificationConfig,
    RectificationEvent,
    RectificationRequest,
)
from benchmarks.harness import blocks, corpus, protocol  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "block_ranking.json"

SHUFFLES = 5
CLOCK_BLOCK_MINUTES = 120  # twelve two-hour blocks


def score_grid(case: dict, events: list[dict]) -> dict[int, float]:
    req = RectificationRequest(
        birth_date=case["birth_date"],
        place=Place(
            lat=case["place"]["lat"], lon=case["place"]["lon"], tz=case["place"]["tz"]
        ),
        candidate_window=CandidateWindow(
            start_time=protocol.WINDOW_START,
            end_time=protocol.WINDOW_END,
            step_minutes=protocol.STEP_MINUTES,
        ),
        events=[
            RectificationEvent(
                id=e["id"],
                date=e["date"],
                date_precision=e["date_precision"],
                type=e["type"],
            )
            for e in events
        ],
        config=RectificationConfig(permutation_trials=0),
    )
    result = score_rectification(req)
    return {
        protocol.time_to_minute(c["time"]): c["total_score"]
        for c in result["candidates"]
    }


def rank_of_true_block(
    scores: dict[int, float], membership: dict[int, object], true_block: object
) -> int:
    """1-based rank of the true block when blocks are ordered by peak score.

    Ties are broken pessimistically for the engine: a block tying with the
    true block is counted as ranking above it, so a flat scorer cannot be
    credited with a good rank by accident.
    """
    peaks: dict[object, float] = {}
    for minute, score in scores.items():
        b = membership[minute]
        if score > peaks.get(b, float("-inf")):
            peaks[b] = score
    true_peak = peaks[true_block]
    return 1 + sum(1 for b, p in peaks.items() if b != true_block and p >= true_peak)


def blind_median_in_block(block: list[int], known: int) -> float:
    """Median |err| of a uniform pick among the block's candidate times."""
    return statistics.median(
        protocol.circular_error_minutes(m, known) for m in block
    )


def summarise(ranks: list[int]) -> dict:
    n = len(ranks)
    return {
        "n": n,
        "first": sum(1 for r in ranks if r == 1) / n,
        "top3": sum(1 for r in ranks if r <= 3) / n,
        "median_rank": statistics.median(ranks),
    }


def summarise_errors(errs: list[int]) -> dict:
    return {
        "n": len(errs),
        "median": statistics.median(errs),
        "mean": statistics.fmean(errs),
        "hit_15": sum(1 for e in errs if e <= 15) / len(errs),
        "hit_30": sum(1 for e in errs if e <= 30) / len(errs),
    }


def main() -> None:
    cases = corpus.load_corpus()
    per_case = []

    for case in cases:
        known = blocks.case_known_minute(case)
        sign_by_minute = blocks.sign_by_minute(case)
        true_sign = blocks.true_ascendant_sign(case)
        clock_membership = {m: m // CLOCK_BLOCK_MINUTES for m in protocol.GRID_MINUTES}
        true_clock = known // CLOCK_BLOCK_MINUTES
        block = blocks.correct_block_minutes(case)

        real = score_grid(case, case["events"])
        row = {
            "case_id": case["case_id"],
            "split": case["split"],
            "real": {
                "clock_rank": rank_of_true_block(real, clock_membership, true_clock),
                "sign_rank": rank_of_true_block(real, sign_by_minute, true_sign),
                "in_block_err": protocol.circular_error_minutes(
                    blocks.best_in_block(real, block), known
                ),
            },
            "null": [],
            "blind_in_block_median": blind_median_in_block(block, known),
            "block_width": len(block) * protocol.STEP_MINUTES,
        }

        lo, hi = case.lifespan_bounds()
        for s in range(SHUFFLES):
            events = protocol.shuffled_events(case["events"], lo, hi, seed=1000 + s)
            sc = score_grid(case, events)
            row["null"].append(
                {
                    "clock_rank": rank_of_true_block(sc, clock_membership, true_clock),
                    "sign_rank": rank_of_true_block(sc, sign_by_minute, true_sign),
                    "in_block_err": protocol.circular_error_minutes(
                        blocks.best_in_block(sc, block), known
                    ),
                }
            )
        per_case.append(row)
        print(
            f"  {case['case_id']:24} {case['split']:8} "
            f"clock#{row['real']['clock_rank']:>2} sign#{row['real']['sign_rank']:>2} "
            f"err={row['real']['in_block_err']:>4}",
            flush=True,
        )

    def report(rows: list[dict]) -> dict:
        return {
            "cases": len(rows),
            "clock_blocks": {
                "real": summarise([r["real"]["clock_rank"] for r in rows]),
                "null": summarise(
                    [n["clock_rank"] for r in rows for n in r["null"]]
                ),
            },
            "sign_blocks": {
                "real": summarise([r["real"]["sign_rank"] for r in rows]),
                "null": summarise([n["sign_rank"] for r in rows for n in r["null"]]),
            },
            "in_block": {
                "real": summarise_errors([r["real"]["in_block_err"] for r in rows]),
                "null": summarise_errors(
                    [n["in_block_err"] for r in rows for n in r["null"]]
                ),
                "blind_uniform_median": statistics.median(
                    r["blind_in_block_median"] for r in rows
                ),
                "median_block_width": statistics.median(
                    r["block_width"] for r in rows
                ),
            },
        }

    out = {
        "shuffles_per_case": SHUFFLES,
        "chance_first": 1 / 12,
        "chance_top3": 3 / 12,
        "all": report(per_case),
        "holdout": report([r for r in per_case if r["split"] == "holdout"]),
        "per_case": per_case,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for scope in ("all", "holdout"):
        r = out[scope]
        print(f"\n=== {scope} (n={r['cases']}) ===")
        for name in ("clock_blocks", "sign_blocks"):
            a, b = r[name]["real"], r[name]["null"]
            print(
                f"{name:12} real 1st {a['first']:>6.1%} top3 {a['top3']:>6.1%} | "
                f"null 1st {b['first']:>6.1%} top3 {b['top3']:>6.1%}  "
                f"(chance 8.3% / 25.0%)"
            )
        ib = r["in_block"]
        print(
            f"in-block     real median {ib['real']['median']:>5.1f} <=15 {ib['real']['hit_15']:>6.1%} | "
            f"null median {ib['null']['median']:>5.1f} <=15 {ib['null']['hit_15']:>6.1%} | "
            f"blind median {ib['blind_uniform_median']:>5.1f}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
