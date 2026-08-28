"""Ceiling of the full stack under perfect oracles. Measurement only.

Three stages applied in sequence to each case:

  (a) perfect oracle on the rising sign - keep candidates whose Ascendant is
      in the true sign;
  (b) perfect oracle on the Placidus natal house configuration - keep only
      candidates whose planet-to-house vector equals the true time's vector;
  (c) engine argmax over whatever survives.

Stages (a) and (b) are oracles: they use the known birth time and are not
things the engine or a client could actually supply. They exist to answer one
question - *if both were free and perfect, how good could this get?*

Note that (a) and (b) depend only on the chart, never on the events. The
shuffled-date null therefore has identical survivor sets and differs from the
real arm at stage (c) alone, which is exactly the comparison worth making.

No scoring change, no tuning. The shipped engine at its defaults with the
permutation null off, because only the argmax is read.

    python benchmarks/oracle_ceiling.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import core  # noqa: E402
from astro_engine.rectification import score_rectification  # noqa: E402
from astro_engine.schemas import (  # noqa: E402
    CandidateWindow,
    Place,
    RectificationConfig,
    RectificationEvent,
    RectificationRequest,
)
from benchmarks.harness import blocks, corpus, protocol  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "oracle_ceiling.json"

SHUFFLES = 5

# The ten bodies the engine itself carries. The house vector is their Placidus
# house numbers, in this fixed order.
VECTOR_BODIES = [name for name, _ in core.PLANETS]


def _jd_at(case: dict, minute: int) -> float:
    birth = dt.date.fromisoformat(case["birth_date"])
    hh, mm = divmod(minute, 60)
    return core.to_julian_day(
        core.localize_to_utc(
            dt.datetime(birth.year, birth.month, birth.day, hh, mm), case["place"]["tz"]
        )
    )


def house_vector(case: dict, jd: float) -> tuple[int, ...]:
    """Placidus house of each body at a given instant."""
    place = case["place"]
    cusps, _, _ = core.houses_and_angles(jd, place["lat"], place["lon"], "placidus")
    out = []
    for name, pid in core.PLANETS:
        lon, _ = core.planet_position(jd, pid)
        out.append(core.house_of(lon, cusps))
    return tuple(out)


def true_house_vector(case: dict) -> tuple[int, ...]:
    """Computed at the known time exactly, not snapped to the grid."""
    return house_vector(case, _jd_at(case, blocks.case_known_minute(case)))


def disjoint_runs(minutes: list[int]) -> int:
    """Number of maximal contiguous runs on the circular 4-minute grid."""
    if not minutes:
        return 0
    grid = protocol.GRID_MINUTES
    n = len(grid)
    present = set(minutes)
    if len(present) == n:
        return 1
    idx = {m: i for i, m in enumerate(grid)}
    starts = 0
    for m in present:
        prev = grid[(idx[m] - 1) % n]
        if prev not in present:
            starts += 1
    return starts


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
    return {
        protocol.time_to_minute(c["time"]): c["total_score"]
        for c in score_rectification(req)["candidates"]
    }


def blind_stats(survivors: list[int], known: int) -> dict:
    """What a uniform pick among the survivors gives. The filter's own ceiling."""
    if not survivors:
        return {"median": None, "hit_5": None, "hit_15": None}
    errs = [protocol.circular_error_minutes(m, known) for m in survivors]
    return {
        "median": statistics.median(errs),
        "hit_5": sum(1 for e in errs if e <= 5) / len(errs),
        "hit_15": sum(1 for e in errs if e <= 15) / len(errs),
    }


def argmax_err(scores: dict[int, float], survivors: list[int], known: int):
    if not survivors:
        return None
    best = max(survivors, key=lambda m: (scores[m], -m))
    return protocol.circular_error_minutes(best, known)


def main() -> None:
    cases = corpus.load_corpus()
    per_case = []

    for case in cases:
        known = blocks.case_known_minute(case)
        sign_by_minute = blocks.sign_by_minute(case)
        true_sign = blocks.true_ascendant_sign(case)
        tv = true_house_vector(case)

        stage_a = [m for m in protocol.GRID_MINUTES if sign_by_minute[m] == true_sign]
        stage_b = [m for m in stage_a if house_vector(case, _jd_at(case, m)) == tv]

        real_scores = score_grid(case, case["events"])
        lo, hi = case.lifespan_bounds()
        null_scores = [
            score_grid(case, protocol.shuffled_events(case["events"], lo, hi, seed=2000 + s))
            for s in range(SHUFFLES)
        ]

        row = {
            "case_id": case["case_id"],
            "split": case["split"],
            "known_minute": known,
            "grid_floor": protocol.grid_floor_error(known),
            "n_all": len(protocol.GRID_MINUTES),
            "n_a": len(stage_a),
            "n_b": len(stage_b),
            "runs_b": disjoint_runs(stage_b),
            "true_survives_b": bool(stage_b)
            and min(
                protocol.circular_error_minutes(m, known) for m in stage_b
            )
            <= protocol.STEP_MINUTES,
            "blind_all": blind_stats(protocol.GRID_MINUTES, known),
            "blind_a": blind_stats(stage_a, known),
            "blind_b": blind_stats(stage_b, known),
            "real_c_after_a": argmax_err(real_scores, stage_a, known),
            "real_c_after_b": argmax_err(real_scores, stage_b, known),
            "null_c_after_a": [argmax_err(s, stage_a, known) for s in null_scores],
            "null_c_after_b": [argmax_err(s, stage_b, known) for s in null_scores],
        }
        per_case.append(row)
        print(
            f"  {case['case_id']:24} {case['split']:8} "
            f"n: 360 -> {row['n_a']:>3} -> {row['n_b']:>3}  runs={row['runs_b']}  "
            f"err a={row['real_c_after_a']} b={row['real_c_after_b']}",
            flush=True,
        )

    def agg_err(values: list) -> dict:
        vals = [v for v in values if v is not None]
        if not vals:
            return {"n": 0, "median": None, "hit_5": None, "hit_15": None}
        return {
            "n": len(vals),
            "median": statistics.median(vals),
            "mean": statistics.fmean(vals),
            "hit_5": sum(1 for e in vals if e <= 5) / len(vals),
            "hit_15": sum(1 for e in vals if e <= 15) / len(vals),
        }

    def agg_blind(rows: list[dict], key: str) -> dict:
        med = [r[key]["median"] for r in rows if r[key]["median"] is not None]
        h5 = [r[key]["hit_5"] for r in rows if r[key]["hit_5"] is not None]
        h15 = [r[key]["hit_15"] for r in rows if r[key]["hit_15"] is not None]
        return {
            "n": len(med),
            "median": statistics.median(med) if med else None,
            "hit_5": statistics.fmean(h5) if h5 else None,
            "hit_15": statistics.fmean(h15) if h15 else None,
        }

    def report(rows: list[dict]) -> dict:
        return {
            "cases": len(rows),
            "survivors": {
                "start": 360,
                "after_a_median": statistics.median(r["n_a"] for r in rows),
                "after_a_mean": statistics.fmean(r["n_a"] for r in rows),
                "after_b_median": statistics.median(r["n_b"] for r in rows),
                "after_b_mean": statistics.fmean(r["n_b"] for r in rows),
                "after_b_min": min(r["n_b"] for r in rows),
                "after_b_max": max(r["n_b"] for r in rows),
                "empty_after_b": sum(1 for r in rows if r["n_b"] == 0),
                "true_survives_b": sum(1 for r in rows if r["true_survives_b"]),
            },
            "runs_after_b": {
                "more_than_one": sum(1 for r in rows if r["runs_b"] > 1),
                "distribution": {
                    str(k): sum(1 for r in rows if r["runs_b"] == k)
                    for k in sorted({r["runs_b"] for r in rows})
                },
                "median": statistics.median(r["runs_b"] for r in rows),
                "max": max(r["runs_b"] for r in rows),
            },
            "blind": {
                "no_oracle": agg_blind(rows, "blind_all"),
                "after_a": agg_blind(rows, "blind_a"),
                "after_b": agg_blind(rows, "blind_b"),
            },
            "engine": {
                "after_a_real": agg_err([r["real_c_after_a"] for r in rows]),
                "after_a_null": agg_err(
                    [v for r in rows for v in r["null_c_after_a"]]
                ),
                "after_b_real": agg_err([r["real_c_after_b"] for r in rows]),
                "after_b_null": agg_err(
                    [v for r in rows for v in r["null_c_after_b"]]
                ),
            },
            "grid_floor_median": statistics.median(r["grid_floor"] for r in rows),
        }

    out = {
        "shuffles_per_case": SHUFFLES,
        "vector_bodies": VECTOR_BODIES,
        "all": report(per_case),
        "holdout": report([r for r in per_case if r["split"] == "holdout"]),
        "per_case": per_case,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for scope in ("all", "holdout"):
        r = out[scope]
        s = r["survivors"]
        print(f"\n=== {scope} (n={r['cases']}) ===")
        print(
            f"survivors  360 -> a median {s['after_a_median']:.0f} "
            f"-> b median {s['after_b_median']:.0f} "
            f"(range {s['after_b_min']}-{s['after_b_max']}, empty {s['empty_after_b']})"
        )
        print(
            f"runs after b: >1 in {r['runs_after_b']['more_than_one']}/{r['cases']} "
            f"cases, distribution {r['runs_after_b']['distribution']}"
        )
        for label, key in (("no oracle", "no_oracle"), ("after a", "after_a"), ("after b", "after_b")):
            b = r["blind"][key]
            print(
                f"blind {label:9} median {b['median']}  <=5 {b['hit_5']:.1%}  <=15 {b['hit_15']:.1%}"
            )
        for label in ("after_a_real", "after_a_null", "after_b_real", "after_b_null"):
            e = r["engine"][label]
            print(
                f"engine {label:14} median {e['median']}  <=5 {e['hit_5']:.1%}  <=15 {e['hit_15']:.1%}  n={e['n']}"
            )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
