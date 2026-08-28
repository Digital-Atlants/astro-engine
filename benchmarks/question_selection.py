"""Work item 1: which two house questions, per chart.

Inside the true rising-sign block, ask how far the block narrows when you are
told the Placidus house of one, two or three planets - and which planets carry
that information. Pure chart geometry: no events, no scoring, no tuning.

Stage (a) and the house vector are both event-independent, so the same run is
repeated on shuffled event dates purely as a wiring check. The two arms must
come out identical; if they do not, something reads events that should not.

    python benchmarks/question_selection.py
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import core  # noqa: E402
from benchmarks.harness import blocks, corpus, protocol  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "question_selection.json"

BODIES = [name for name, _ in core.PLANETS]


def house_vectors(case: dict, minutes: list[int]) -> dict[int, tuple[int, ...]]:
    place = case["place"]
    birth = dt.date.fromisoformat(case["birth_date"])
    out = {}
    for m in minutes:
        hh, mm = divmod(m, 60)
        jd = core.to_julian_day(
            core.localize_to_utc(
                dt.datetime(birth.year, birth.month, birth.day, hh, mm), place["tz"]
            )
        )
        cusps, _, _ = core.houses_and_angles(jd, place["lat"], place["lon"], "placidus")
        out[m] = tuple(
            core.house_of(core.planet_position(jd, pid)[0], cusps)
            for _, pid in core.PLANETS
        )
    return out


def true_vector(case: dict) -> tuple[int, ...]:
    place = case["place"]
    birth = dt.date.fromisoformat(case["birth_date"])
    hh, mm = divmod(blocks.case_known_minute(case), 60)
    jd = core.to_julian_day(
        core.localize_to_utc(
            dt.datetime(birth.year, birth.month, birth.day, hh, mm), place["tz"]
        )
    )
    cusps, _, _ = core.houses_and_angles(jd, place["lat"], place["lon"], "placidus")
    return tuple(
        core.house_of(core.planet_position(jd, pid)[0], cusps) for _, pid in core.PLANETS
    )


def survivors(vectors: dict[int, tuple], tv: tuple, idx: tuple[int, ...]) -> list[int]:
    return [
        m
        for m, v in vectors.items()
        if all(v[i] == tv[i] for i in idx)
    ]


def span_minutes(minutes: list[int]) -> int:
    """Width of the surviving set, counted as candidates x step."""
    return len(minutes) * protocol.STEP_MINUTES


def best_combo(vectors, tv, varying: list[int], k: int):
    """The k planets whose houses narrow the block most.

    Ties broken by the planet order in core.PLANETS so the choice is
    deterministic and not sensitive to dict ordering.
    """
    best = None
    for combo in itertools.combinations(sorted(varying), k):
        n = len(survivors(vectors, tv, combo))
        key = (n, combo)
        if best is None or key < best[0]:
            best = (key, combo, n)
    return (best[1], best[2]) if best else ((), len(vectors))


def analyse(case: dict, events: list[dict] | None = None) -> dict:
    block = blocks.correct_block_minutes(case)
    vectors = house_vectors(case, block)
    tv = true_vector(case)

    varying = [
        i for i in range(len(BODIES)) if len({v[i] for v in vectors.values()}) > 1
    ]
    row = {
        "case_id": case["case_id"],
        "split": case["split"],
        "block_minutes": span_minutes(block),
        "block_candidates": len(block),
        "planets_changing_house": [BODIES[i] for i in varying],
        "n_planets_changing_house": len(varying),
    }

    for k in (1, 2, 3):
        if len(varying) < k:
            row[f"q{k}"] = {
                "planets": [BODIES[i] for i in varying],
                "window_minutes": span_minutes(survivors(vectors, tv, tuple(varying)))
                if varying
                else row["block_minutes"],
                "note": "fewer planets change house than questions asked",
            }
            continue
        combo, n = best_combo(vectors, tv, varying, k)
        row[f"q{k}"] = {
            "planets": [BODIES[i] for i in combo],
            "window_minutes": n * protocol.STEP_MINUTES,
            "candidates": n,
        }

    full = survivors(vectors, tv, tuple(range(len(BODIES))))
    row["full_vector"] = {
        "window_minutes": span_minutes(full),
        "candidates": len(full),
    }
    return row


def main() -> None:
    cases = corpus.load_corpus()
    real_rows = [analyse(c) for c in cases]
    for r in real_rows:
        print(
            f"  {r['case_id']:24} {r['split']:8} block {r['block_minutes']:>4} "
            f"-> q1 {r['q1']['window_minutes']:>4} q2 {r['q2']['window_minutes']:>4} "
            f"q3 {r['q3']['window_minutes']:>4} full {r['full_vector']['window_minutes']:>4} "
            f"({r['n_planets_changing_house']} planets move)",
            flush=True,
        )

    # Work item 1.4: the shuffled arm. Stage (a) and the house vector never
    # read the events, so this must reproduce the real arm exactly.
    null_rows = []
    for case in cases:
        lo, hi = case.lifespan_bounds()
        shuffled = protocol.shuffled_events(case["events"], lo, hi, seed=4242)
        null_rows.append(analyse(case, shuffled))

    identical = all(
        a["q1"]["window_minutes"] == b["q1"]["window_minutes"]
        and a["q2"]["window_minutes"] == b["q2"]["window_minutes"]
        and a["q3"]["window_minutes"] == b["q3"]["window_minutes"]
        and a["full_vector"] == b["full_vector"]
        and a["planets_changing_house"] == b["planets_changing_house"]
        for a, b in zip(real_rows, null_rows)
    )

    def summarise(rows):
        return {
            "cases": len(rows),
            "block_minutes_median": statistics.median(r["block_minutes"] for r in rows),
            "planets_changing_house_median": statistics.median(
                r["n_planets_changing_house"] for r in rows
            ),
            "planets_changing_house_min": min(
                r["n_planets_changing_house"] for r in rows
            ),
            "planets_changing_house_max": max(
                r["n_planets_changing_house"] for r in rows
            ),
            "q1_median": statistics.median(r["q1"]["window_minutes"] for r in rows),
            "q2_median": statistics.median(r["q2"]["window_minutes"] for r in rows),
            "q3_median": statistics.median(r["q3"]["window_minutes"] for r in rows),
            "full_median": statistics.median(
                r["full_vector"]["window_minutes"] for r in rows
            ),
            "q2_equals_full": sum(
                1
                for r in rows
                if r["q2"]["window_minutes"] == r["full_vector"]["window_minutes"]
            ),
            "q3_adds_nothing_over_q2": sum(
                1
                for r in rows
                if r["q3"]["window_minutes"] == r["q2"]["window_minutes"]
            ),
        }

    counts: dict[str, int] = {}
    pairs: dict[str, int] = {}
    for r in real_rows:
        for p in r["q2"]["planets"]:
            counts[p] = counts.get(p, 0) + 1
        pairs["+".join(r["q2"]["planets"])] = pairs.get("+".join(r["q2"]["planets"]), 0) + 1

    out = {
        "all": summarise(real_rows),
        "holdout": summarise([r for r in real_rows if r["split"] == "holdout"]),
        "shuffled_arm_identical": identical,
        "q2_planet_frequency": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "q2_pair_frequency": dict(sorted(pairs.items(), key=lambda kv: -kv[1])),
        "distinct_q2_pairs": len(pairs),
        "per_case": real_rows,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for scope in ("all", "holdout"):
        s = out[scope]
        print(f"\n=== {scope} (n={s['cases']}) ===")
        print(
            f"block {s['block_minutes_median']:.0f} -> q1 {s['q1_median']:.0f} "
            f"-> q2 {s['q2_median']:.0f} -> q3 {s['q3_median']:.0f} "
            f"| full vector {s['full_median']:.0f} (median minutes)"
        )
        print(
            f"planets changing house in block: median "
            f"{s['planets_changing_house_median']:.0f} "
            f"(range {s['planets_changing_house_min']}-{s['planets_changing_house_max']})"
        )
        print(
            f"q2 already equals the full vector in {s['q2_equals_full']}/{s['cases']}; "
            f"q3 adds nothing over q2 in {s['q3_adds_nothing_over_q2']}/{s['cases']}"
        )
    print(f"\nshuffled arm identical to real arm: {identical}")
    print(f"distinct best pairs across {len(real_rows)} charts: {out['distinct_q2_pairs']}")
    print("most-selected planets:", list(out["q2_planet_frequency"].items())[:6])
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
