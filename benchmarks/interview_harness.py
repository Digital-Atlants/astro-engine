"""Work item 4: synthetic answerers and the pre-registered gates.

Six answerer models drive the real interview core over all 41 corpus cases,
20 seeded runs each. What this tests is the **detection logic** - whether the
tiers respond correctly to answer quality - not astrological accuracy. Answer
quality is exactly the variable being simulated, so simulating it is the point
rather than a violation of the no-self-generated-data rule; the astrological
accuracy of the pipeline inherits from the ceiling measurements already made
against known birth times in RESULTS_SUBSIGN.md.

    python benchmarks/interview_harness.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "interview_gates.json"

RUNS_PER_CASE = 20
MAX_STEPS = 8

SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]

ANSWERERS = ("perfect", "iid_noisy", "adjacent_sign", "random",
             "dont_know_heavy", "impostor")


def true_label(grid: interview.ChartGrid, question: dict, minute: int,
               windows: list[tuple[int, int]] | None) -> str | None:
    labels = interview.partition_for(
        grid, question["channel"], question.get("subject"), windows
    )
    label = labels[minute % interview.N_GRID]
    valid = {o["answer_id"] for o in question["options"]}
    return label if label in valid else None


def choose(model: str, rng: random.Random, question: dict,
           grid: interview.ChartGrid, truth_minute: int,
           impostor_minute: int, windows) -> list[str]:
    options = [o["answer_id"] for o in question["options"]]
    if not options:
        return []

    if model == "random":
        # Uniform over the options plus `cannot_choose`.
        pick = rng.choice(options + ["__cannot_choose__"])
        return [] if pick == "__cannot_choose__" else [pick]

    reference = impostor_minute if model == "impostor" else truth_minute
    correct = true_label(grid, question, reference, windows)

    if model == "dont_know_heavy" and rng.random() < 0.5:
        return []

    if correct is None:
        return []

    if model == "adjacent_sign" and question["channel"] == "rising_sign":
        idx = SIGNS.index(correct) if correct in SIGNS else None
        if idx is not None:
            neighbour = SIGNS[(idx + rng.choice([-1, 1])) % 12]
            return [neighbour] if neighbour in options else [correct]

    if model == "iid_noisy" and rng.random() < 0.2:
        alternatives = [o for o in options if o != correct]
        if alternatives:
            return [rng.choice(alternatives)]

    return [correct]


def simulate(grid: interview.ChartGrid, truth_minute: int, model: str, seed: int,
             cfg: interview.InterviewConfig) -> dict:
    rng = random.Random(seed)
    impostor_minute = (truth_minute + 360) % interview.N_GRID
    answers: list[dict] = []
    windows: list[tuple[int, int]] | None = None
    questions_asked = 0

    for _ in range(MAX_STEPS):
        posterior, trace = interview.build_posterior(grid, answers, cfg)
        question = interview.next_question(grid, posterior, answers, cfg)
        if question is None:
            break
        if question["channel"] == "portrait":
            windows = [tuple(w) for w in question["windows"]]
        picked = choose(model, rng, question, grid, truth_minute,
                        impostor_minute, windows)
        entry = {
            "question_id": question["question_id"],
            "channel": question["channel"],
            "subject": question.get("subject"),
            "answer_ids": picked,
        }
        if question["channel"] == "portrait":
            entry["windows"] = [list(w) for w in windows or []]
        answers.append(entry)
        questions_asked += 1

    posterior, trace = interview.build_posterior(grid, answers, cfg)
    tier = interview.assign_tier(posterior, trace, cfg)

    issued = tier["tier"] in (1, 2) and tier["windows"]
    contains = False
    err = None
    width = None
    if issued:
        w = tier["windows"][0]
        width = w["width_minutes"]
        mh, mm = map(int, w["midpoint"].split(":"))
        mid = mh * 60 + mm
        d = abs(mid - truth_minute) % interview.N_GRID
        err = min(d, interview.N_GRID - d)
        contains = any(
            _contains(x, truth_minute) for x in tier["windows"]
        )

    return {
        "tier": tier["tier"],
        "questions": questions_asked,
        "cannot_choose": sum(1 for a in answers if not a["answer_ids"]),
        "issued": bool(issued),
        "window_contains_truth": contains,
        "abs_error_minutes": err,
        "window_minutes": width,
        "chance_agreement_p": tier["coherence"]["chance_agreement_p"],
        "concentration": tier["coherence"]["concentration"],
    }


def _contains(window: dict, minute: int) -> bool:
    sh, sm = map(int, window["start"].split(":"))
    eh, em = map(int, window["end"].split(":"))
    start, end = sh * 60 + sm, eh * 60 + em
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    tiers = {t: sum(1 for r in rows if r["tier"] == t) / n for t in (1, 2, 3, 4)}
    t1 = [r for r in rows if r["tier"] == 1]
    issued = [r for r in rows if r["issued"]]
    errs = [r["abs_error_minutes"] for r in issued if r["abs_error_minutes"] is not None]
    widths = [r["window_minutes"] for r in issued if r["window_minutes"] is not None]
    t1_wrong = [r for r in t1 if not r["window_contains_truth"]]
    # G2's conditions are all about Tier 1, so its window and error statistics
    # must be read off Tier 1 rows only. Mixing Tier 2 windows in made the
    # "stated window <= 30 minutes" check look violated when no Tier 1 window
    # ever exceeded 30 by construction.
    t1_errs = [r["abs_error_minutes"] for r in t1 if r["abs_error_minutes"] is not None]
    t1_widths = [r["window_minutes"] for r in t1 if r["window_minutes"] is not None]
    return {
        "tier1_median_abs_error": statistics.median(t1_errs) if t1_errs else None,
        "tier1_median_window_minutes": statistics.median(t1_widths) if t1_widths else None,
        "tier1_max_window_minutes": max(t1_widths) if t1_widths else None,
        "n": n,
        "tier_distribution": {str(k): round(v, 4) for k, v in tiers.items()},
        "tier1_rate": round(tiers[1], 4),
        "tier1_wrong_window_rate": round(len(t1_wrong) / n, 4),
        "tier1_wrong_window_rate_of_tier1": (
            round(len(t1_wrong) / len(t1), 4) if t1 else None
        ),
        "tier1_contains_truth_rate": (
            round(sum(1 for r in t1 if r["window_contains_truth"]) / len(t1), 4)
            if t1 else None
        ),
        "tier3_or_4_rate": round(tiers[3] + tiers[4], 4),
        "median_abs_error": statistics.median(errs) if errs else None,
        "median_window_minutes": statistics.median(widths) if widths else None,
        "max_window_minutes": max(widths) if widths else None,
        "median_questions": statistics.median(r["questions"] for r in rows),
        "mean_questions": round(statistics.fmean(r["questions"] for r in rows), 2),
    }


def run(cfg: interview.InterviewConfig, cases, label: str) -> dict:
    per_model: dict[str, list[dict]] = {m: [] for m in ANSWERERS}
    t0 = time.perf_counter()
    for case in cases:
        grid = interview.ChartGrid(
            dt.date.fromisoformat(case["birth_date"]),
            case["place"]["lat"], case["place"]["lon"], case["place"]["tz"],
            cfg.house_system,
        )
        hh, mm = map(int, case["known_time"].split(":"))
        truth = hh * 60 + mm
        for model in ANSWERERS:
            for k in range(RUNS_PER_CASE):
                row = simulate(grid, truth, model, hash((case["case_id"], model, k)) % (2**31), cfg)
                row["case_id"] = case["case_id"]
                row["split"] = case["split"]
                per_model[model].append(row)
        print(f"  [{label}] {case['case_id']}", flush=True)
    elapsed = time.perf_counter() - t0
    return {
        "label": label,
        "seconds": round(elapsed, 1),
        "per_model": {m: summarise(rows) for m, rows in per_model.items()},
        "raw_counts": {m: len(rows) for m, rows in per_model.items()},
        "_rows": per_model,
    }


def gates(result: dict) -> dict:
    pm = result["per_model"]
    safety_models = [m for m in ANSWERERS if m != "impostor"]
    per_model_rates = {m: pm[m]["tier1_wrong_window_rate"] for m in safety_models}
    pooled_wrong = sum(
        pm[m]["tier1_wrong_window_rate"] * pm[m]["n"] for m in safety_models
    ) / sum(pm[m]["n"] for m in safety_models)

    g1 = all(v <= 0.05 for v in per_model_rates.values()) and pooled_wrong <= 0.05
    perfect = pm["perfect"]
    g2 = (
        perfect["tier1_rate"] >= 0.90
        and (perfect["tier1_max_window_minutes"] or 0) <= 30
        and (perfect["tier1_contains_truth_rate"] or 0) >= 0.95
        and (perfect["tier1_median_abs_error"]
             if perfect["tier1_median_abs_error"] is not None else 999) <= 8
    )
    g3 = pm["random"]["tier3_or_4_rate"] >= 0.95
    return {
        "G1_safety": {
            "pass": bool(g1),
            "per_model_tier1_wrong_window_rate": per_model_rates,
            "pooled": round(pooled_wrong, 4),
            "threshold": 0.05,
        },
        "G2_usefulness": {
            "pass": bool(g2),
            "tier1_rate": perfect["tier1_rate"],
            "tier1_max_window_minutes": perfect["tier1_max_window_minutes"],
            "tier1_contains_truth_rate": perfect["tier1_contains_truth_rate"],
            "tier1_median_abs_error": perfect["tier1_median_abs_error"],
            "thresholds": {"tier1_rate": 0.90, "window": 30, "contains": 0.95, "err": 8},
        },
        "G3_refusal": {
            "pass": bool(g3),
            "tier3_or_4_rate": pm["random"]["tier3_or_4_rate"],
            "threshold": 0.95,
        },
        "impostor_tier1_wrong_window_rate": pm["impostor"]["tier1_wrong_window_rate"],
    }


def main() -> None:
    cases = corpus.load_corpus()
    cfg = interview.InterviewConfig()
    result = run(cfg, cases, "frozen-defaults")
    verdicts = gates(result)

    sensitivity = {}
    for r in (0.6, 0.75, 0.9):
        c = interview.InterviewConfig(channel_reliability=r)
        res = run(c, cases, f"r={r}")
        sensitivity[str(r)] = {
            "per_model": res["per_model"],
            "gates": gates(res),
        }

    rows = result.pop("_rows")
    question_counts = {}
    for m, rs in rows.items():
        counts: dict[str, int] = {}
        for x in rs:
            counts[str(x["questions"])] = counts.get(str(x["questions"]), 0) + 1
        question_counts[m] = dict(sorted(counts.items(), key=lambda kv: int(kv[0])))

    out = {
        "runs_per_case": RUNS_PER_CASE,
        "cases": len(cases),
        "config_frozen": {
            "channel_reliability": cfg.channel_reliability,
            "tier1_mass": cfg.tier1_mass,
            "tier2_mass": cfg.tier2_mass,
            "tier1_chance_p": cfg.tier1_chance_p,
            "tier1_window_minutes": cfg.tier1_window_minutes,
            "min_information_bits": cfg.min_information_bits,
        },
        "result": result,
        "gates": verdicts,
        "sensitivity_over_reliability": {
            k: v["gates"] for k, v in sensitivity.items()
        },
        "sensitivity_detail": {k: v["per_model"] for k, v in sensitivity.items()},
        "question_count_distribution": question_counts,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== per answerer (frozen defaults) ===")
    for m in ANSWERERS:
        s = result["per_model"][m]
        print(
            f"{m:16} T1 {s['tier1_rate']:>6.1%} T3/4 {s['tier3_or_4_rate']:>6.1%} "
            f"wrongT1 {s['tier1_wrong_window_rate']:>6.2%} "
            f"err {str(s['median_abs_error']):>5} win {str(s['median_window_minutes']):>5} "
            f"q {s['median_questions']:>4}"
        )
    print("\n=== gates ===")
    for k in ("G1_safety", "G2_usefulness", "G3_refusal"):
        print(f"{k}: {'PASS' if verdicts[k]['pass'] else 'FAIL'}  {verdicts[k]}")
    print(f"impostor Tier-1 wrong-window rate: {verdicts['impostor_tier1_wrong_window_rate']:.2%}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
