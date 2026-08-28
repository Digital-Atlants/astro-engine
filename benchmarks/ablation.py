"""Work item 3: the ablation.

Runs against `benchmarks/harness/candidate_engine.py`, the frozen copy of the
scorer that carried all five additions. Every one of them failed here and was
reverted out of `astro_engine/`, so the shipped engine can no longer express
these configurations - which is the point. This script remains runnable so the
numbers in RESULTS_SUBSIGN.md can be reproduced.

Each addition is measured on its own and cumulatively, as median absolute
error *inside the correct rising-sign block*. Decisions are read off `train`;
the pre-registered gate is read off `holdout` and nothing else.

    python benchmarks/ablation.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine.schemas import (  # noqa: E402
    CandidateWindow,
    Place,
    RectificationEvent,
)
from benchmarks.harness.candidate_engine import (  # noqa: E402
    CandidateConfig as RectificationConfig,
    CandidateRequest as RectificationRequest,
    score_rectification,
)
from benchmarks.harness import blocks, corpus, protocol  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "ablation_table.json"

BASE = ["transits_to_angles", "secondary_progressions", "solar_arc", "profections"]

# (label, techniques added to BASE, extra config)
STEPS = [
    ("3.1 quadrant_cusps", ["quadrant_cusps"], {}),
    ("3.2 directed_angles", ["directed_angles"], {}),
    ("3.3 primary_directions", ["primary_directions"], {}),
    ("3.4 eclipse_on_angle", ["eclipse_on_angle"], {}),
    ("3.5 event_technique_matching", [], {"event_technique_matching": True}),
]


def run_case(case: dict, cfg: RectificationConfig) -> dict[int, float]:
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
            for e in case["events"]
        ],
        config=cfg,
    )
    result = score_rectification(req)
    return {
        protocol.time_to_minute(c["time"]): c["total_score"]
        for c in result["candidates"]
    }


def config(techniques: list[str], **extra) -> RectificationConfig:
    base = {"techniques": techniques, "event_technique_matching": False,
            "permutation_trials": 0}
    base.update(extra)
    return RectificationConfig(**base)


def evaluate(cases: list[dict], cfg: RectificationConfig) -> dict:
    errs, in_block_errs = [], []
    for case in cases:
        scores = run_case(case, cfg)
        block = blocks.correct_block_minutes(case)
        known = blocks.case_known_minute(case)
        in_block_errs.append(
            protocol.circular_error_minutes(blocks.best_in_block(scores, block), known)
        )
        full = max(scores, key=lambda m: (scores[m], -m))
        errs.append(protocol.circular_error_minutes(full, known))
    return {
        "n": len(cases),
        "median_in_block": statistics.median(in_block_errs),
        "mean_in_block": statistics.fmean(in_block_errs),
        "hit_5_in_block": sum(1 for e in in_block_errs if e <= 5) / len(cases),
        "hit_15_in_block": sum(1 for e in in_block_errs if e <= 15) / len(cases),
        "hit_30_in_block": sum(1 for e in in_block_errs if e <= 30) / len(cases),
        "median_full_day": statistics.median(errs),
        "errors_in_block": in_block_errs,
    }


def main() -> None:
    train = corpus.load_corpus(split="train")
    holdout = corpus.load_corpus(split="holdout")
    nonround_holdout = [c for c in holdout if not c["known_time_is_round"]]
    results = {}

    def measure(label: str, cfg: RectificationConfig) -> None:
        t0 = time.perf_counter()
        row = {
            "train": evaluate(train, cfg),
            "holdout": evaluate(holdout, cfg),
            "holdout_nonround": evaluate(nonround_holdout, cfg),
            "techniques": list(cfg.techniques),
            "event_technique_matching": cfg.event_technique_matching,
            "house_system": cfg.house_system,
            "direction_key": cfg.direction_key,
            "seconds": time.perf_counter() - t0,
        }
        results[label] = row
        print(
            f"{label:44} train {row['train']['median_in_block']:>6.1f} "
            f"holdout {row['holdout']['median_in_block']:>6.1f} "
            f"({row['seconds']:.0f}s)",
            flush=True,
        )

    print("=== baseline ===")
    measure("baseline (shipped techniques)", config(BASE))

    print("=== individual additions (baseline + one) ===")
    for label, add, extra in STEPS:
        measure(f"individual: {label}", config(BASE + add, **extra))

    print("=== cumulative ===")
    techs = list(BASE)
    extras: dict = {}
    for label, add, extra in STEPS:
        techs = techs + add
        extras.update(extra)
        measure(f"cumulative: +{label}", config(techs, **extras))

    print("=== house system, with quadrant cusps enabled ===")
    for hs in ("whole_sign", "placidus"):
        measure(
            f"house_system={hs} (base + quadrant_cusps)",
            config(BASE + ["quadrant_cusps"], house_system=hs),
        )

    print("=== directions key ===")
    for key in ("ptolemy", "naibod"):
        measure(
            f"direction_key={key} (base + primary_directions)",
            config(BASE + ["primary_directions"], direction_key=key),
        )

    OUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
