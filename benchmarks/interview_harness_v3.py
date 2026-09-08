"""v3 harness: trait-split stage 1, G1-G5.

Answerer models are the v2 seven, adapted to tag selection. What this measures
is detection logic - whether the tiers respond correctly to answer quality -
not astrological accuracy, which inherits from RESULTS_SUBSIGN.md.

    python benchmarks/interview_harness_v3.py
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

OUT = pathlib.Path(__file__).resolve().parent / "interview_gates_v3.json"

RUNS_PER_CASE = 20
MAX_STEPS = 16
CORRELATION = 0.7
TIE = 0.05  # a tag within this of the best is "equally the highest"

SIGNS = interview.TRAIT_SIGNS
ANSWERERS = ("perfect", "iid_noisy", "correlated_noisy", "adjacent_sign",
             "random", "dont_know_heavy", "impostor")
GATED = ("perfect", "iid_noisy", "adjacent_sign", "random", "dont_know_heavy")


def _true_partition_label(grid, question, minute, windows):
    labels = interview.partition_for(
        grid, question["channel"], question.get("subject"), windows
    )
    label = labels[minute % interview.N_GRID]
    valid = {o["answer_id"] for o in question["options"]}
    return label if label in valid else None


def _best_tags_for(question, sign) -> list[str]:
    """The offered tags whose likelihood is highest for this sign."""
    ids = [o["answer_id"] for o in question["options"]]
    lik = {t: interview.TRAIT_TAGS[t]["likelihood"][sign] for t in ids}
    if not lik:
        return []
    top = max(lik.values())
    return [t for t, v in lik.items() if v >= top - TIE]


class Answerer:
    def __init__(self, model, rng, truth_sign, truth_minute, impostor_minute,
                 impostor_sign):
        self.model = model
        self.rng = rng
        self.truth_sign = truth_sign
        self.truth = truth_minute
        self.impostor = impostor_minute
        self.impostor_sign = impostor_sign
        self.memory: dict[tuple, dict] = {}
        self.sign_shift = rng.choice([-1, 1])

    def _reference_sign(self):
        if self.model == "impostor":
            return self.impostor_sign
        if self.model == "adjacent_sign":
            return SIGNS[(SIGNS.index(self.truth_sign) + self.sign_shift) % 12]
        return self.truth_sign

    def answer(self, question, grid, windows) -> list[str]:
        ids = [o["answer_id"] for o in question["options"]]
        if not ids:
            return []
        key = (question["channel"], question.get("subject"))
        variant = question.get("variant", "a")

        if self.model == "random":
            pick = self.rng.choice(ids + ["__cannot_choose__"])
            return [] if pick == "__cannot_choose__" else [pick]

        if question["channel"] == "trait":
            correct = _best_tags_for(question, self._reference_sign())
        else:
            reference = self.impostor if self.model == "impostor" else self.truth
            label = _true_partition_label(question and question, question, reference, windows) \
                if False else _true_partition_label(grid, question, reference, windows)
            correct = [label] if label else []

        if self.model == "dont_know_heavy" and self.rng.random() < 0.5:
            return []
        if not correct:
            return []

        if self.model == "iid_noisy":
            # Each phrasing independently wrong.
            if self.rng.random() < 0.2:
                others = [i for i in ids if i not in correct]
                if others:
                    return [self.rng.choice(others)]
            return correct

        if self.model == "correlated_noisy":
            state = self.memory.get(key)
            if variant == "a" or state is None:
                wrong = self.rng.random() < 0.2
                others = [i for i in ids if i not in correct]
                pick = [self.rng.choice(others)] if (wrong and others) else correct
                state = {"wrong": wrong and bool(others), "answer": pick,
                         "repeats": self.rng.random() < CORRELATION}
                self.memory[key] = state
                return pick
            if state["wrong"] and state["repeats"] and all(
                a in ids for a in state["answer"]
            ):
                return state["answer"]
            return correct

        return correct  # perfect, adjacent_sign, impostor


def simulate(grid, truth_minute, model, seed, cfg, free_text=False) -> dict:
    rng = random.Random(seed)
    truth_sign = grid.asc_sign[truth_minute]
    impostor_minute = (truth_minute + 360) % interview.N_GRID
    person = Answerer(model, rng, truth_sign, truth_minute, impostor_minute,
                      grid.asc_sign[impostor_minute])

    tags = None
    if free_text:
        # Two confirmed tags drawn from the person's own words, at the trust
        # level for that source.
        ranked = sorted(
            interview.TRAIT_TAGS,
            key=lambda t: -interview.TRAIT_TAGS[t]["likelihood"][person._reference_sign()],
        )
        tags = ranked[:2]

    answers: list[dict] = []
    if tags:
        # Confirmed free-text tags arrive before the interview begins, as one
        # more observation of the same vocabulary at their own trust level.
        answers.append({
            "question_id": "free_text_traits",
            "channel": "trait",
            "subject": "free_text",
            "variant": "a",
            "source": "free_text_confirmed",
            "answer_ids": list(tags),
            "offered_tag_ids": list(tags),
        })
    windows = None
    asked = 0
    stage1_rounds = 0
    sign_top_after_stage1 = None
    bits_by_stage: dict[str, list[float]] = {}

    for _ in range(MAX_STEPS):
        posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
        q = interview.next_question(grid, posterior, answers, cfg)
        if q is None:
            break
        if q["channel"] != "trait" and sign_top_after_stage1 is None:
            sm = interview.sign_mass(posterior, grid.asc_sign)
            sign_top_after_stage1 = max(sm, key=sm.get)
        if q["channel"] == "portrait":
            windows = [tuple(w) for w in q["windows"]]
        if q["channel"] == "trait" and q.get("variant", "a") == "a":
            stage1_rounds += 1
        bits_by_stage.setdefault(q["channel"], []).append(q["information_bits"])

        entry = {
            "question_id": q["question_id"],
            "channel": q["channel"],
            "subject": q.get("subject"),
            "variant": q.get("variant", "a"),
            "answer_ids": person.answer(q, grid, windows),
        }
        if q["channel"] == "trait":
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if q["channel"] == "portrait":
            entry["windows"] = [list(w) for w in windows or []]
        answers.append(entry)
        asked += 1

    posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
    if sign_top_after_stage1 is None:
        sm = interview.sign_mass(posterior, grid.asc_sign)
        sign_top_after_stage1 = max(sm, key=sm.get)
    tier = interview.assign_tier(posterior, trace, cfg, pairs)

    issued = tier["tier"] in (1, 2) and tier["windows"]
    contains, err, width = False, None, None
    if issued:
        w = tier["windows"][0]
        width = w["width_minutes"]
        mh, mm = map(int, w["midpoint"].split(":"))
        d = abs((mh * 60 + mm) - truth_minute) % interview.N_GRID
        err = min(d, interview.N_GRID - d)
        contains = any(_contains(x, truth_minute) for x in tier["windows"])

    return {
        "tier": tier["tier"],
        "questions": asked,
        "stage1_rounds": stage1_rounds,
        "sign_recovered": sign_top_after_stage1 == truth_sign,
        "issued": bool(issued),
        "window_contains_truth": contains,
        "abs_error_minutes": err,
        "window_minutes": width,
        "agreeing_pairs": pairs["agreeing_pairs"],
        "disagreeing_pairs": pairs["disagreeing_pairs"],
        "bits_by_stage": {k: statistics.fmean(v) for k, v in bits_by_stage.items()},
    }


def _contains(window, minute) -> bool:
    sh, sm = map(int, window["start"].split(":"))
    eh, em = map(int, window["end"].split(":"))
    start, end = sh * 60 + sm, eh * 60 + em
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end


def summarise(rows) -> dict:
    n = len(rows)
    tiers = {t: sum(1 for r in rows if r["tier"] == t) / n for t in (1, 2, 3, 4)}
    t1 = [r for r in rows if r["tier"] == 1]
    t1_wrong = [r for r in t1 if not r["window_contains_truth"]]
    t1_errs = [r["abs_error_minutes"] for r in t1 if r["abs_error_minutes"] is not None]
    t1_widths = [r["window_minutes"] for r in t1 if r["window_minutes"] is not None]
    stages: dict[str, list[float]] = {}
    for r in rows:
        for k, v in r["bits_by_stage"].items():
            stages.setdefault(k, []).append(v)
    return {
        "n": n,
        "tier_distribution": {str(k): round(v, 4) for k, v in tiers.items()},
        "tier1_rate": round(tiers[1], 4),
        "tier1_wrong_window_rate": round(len(t1_wrong) / n, 4),
        "tier1_contains_truth_rate": (
            round(sum(1 for r in t1 if r["window_contains_truth"]) / len(t1), 4)
            if t1 else None
        ),
        "tier1_median_abs_error": statistics.median(t1_errs) if t1_errs else None,
        "tier1_median_window_minutes": statistics.median(t1_widths) if t1_widths else None,
        "tier1_max_window_minutes": max(t1_widths) if t1_widths else None,
        "tier3_or_4_rate": round(tiers[3] + tiers[4], 4),
        "sign_recovery_rate": round(
            sum(1 for r in rows if r["sign_recovered"]) / n, 4
        ),
        "median_questions": statistics.median(r["questions"] for r in rows),
        "mean_questions": round(statistics.fmean(r["questions"] for r in rows), 2),
        "median_stage1_rounds": statistics.median(r["stage1_rounds"] for r in rows),
        "bits_by_stage": {k: round(statistics.fmean(v), 4) for k, v in stages.items()},
        "question_count_distribution": {
            str(q): sum(1 for r in rows if r["questions"] == q)
            for q in sorted({r["questions"] for r in rows})
        },
    }


def run(cfg, cases, label, free_text=False, models=ANSWERERS) -> dict:
    per_model = {m: [] for m in models}
    t0 = time.perf_counter()
    for case in cases:
        grid = interview.ChartGrid(
            dt.date.fromisoformat(case["birth_date"]),
            case["place"]["lat"], case["place"]["lon"], case["place"]["tz"],
            cfg.house_system,
        )
        hh, mm = map(int, case["known_time"].split(":"))
        truth = hh * 60 + mm
        for model in models:
            for k in range(RUNS_PER_CASE):
                seed = abs(hash((case["case_id"], model, k, label))) % (2**31)
                row = simulate(grid, truth, model, seed, cfg, free_text)
                row["case_id"] = case["case_id"]
                row["split"] = case["split"]
                per_model[model].append(row)
    return {
        "label": label,
        "seconds": round(time.perf_counter() - t0, 1),
        "per_model": {m: summarise(rows) for m, rows in per_model.items()},
    }


def gates(result) -> dict:
    pm = result["per_model"]
    rates = {m: pm[m]["tier1_wrong_window_rate"] for m in GATED if m in pm}
    pooled = sum(pm[m]["tier1_wrong_window_rate"] * pm[m]["n"] for m in rates) / sum(
        pm[m]["n"] for m in rates
    )
    perfect = pm["perfect"]
    g1 = all(v <= 0.05 for v in rates.values()) and pooled <= 0.05
    g2 = (
        perfect["tier1_rate"] >= 0.90
        and (perfect["tier1_max_window_minutes"] or 0) <= 30
        and (perfect["tier1_contains_truth_rate"] or 0) >= 0.95
        and (perfect["tier1_median_abs_error"]
             if perfect["tier1_median_abs_error"] is not None else 999) <= 8
    )
    g3 = pm["random"]["tier3_or_4_rate"] >= 0.95
    g4 = perfect["median_questions"] <= 9
    g5 = (
        perfect["sign_recovery_rate"] >= 0.90
        and pm["iid_noisy"]["sign_recovery_rate"] >= 0.60
    )
    return {
        "G1_safety": {"pass": bool(g1), "per_model": rates, "pooled": round(pooled, 4)},
        "G2_usefulness": {
            "pass": bool(g2),
            "tier1_rate": perfect["tier1_rate"],
            "tier1_max_window_minutes": perfect["tier1_max_window_minutes"],
            "tier1_contains_truth_rate": perfect["tier1_contains_truth_rate"],
            "tier1_median_abs_error": perfect["tier1_median_abs_error"],
        },
        "G3_refusal": {"pass": bool(g3), "tier3_or_4_rate": pm["random"]["tier3_or_4_rate"]},
        "G4_cost": {"pass": bool(g4), "median_questions": perfect["median_questions"]},
        "G5_sign_recovery": {
            "pass": bool(g5),
            "perfect": perfect["sign_recovery_rate"],
            "iid_noisy": pm["iid_noisy"]["sign_recovery_rate"],
            "thresholds": {"perfect": 0.90, "iid_noisy": 0.60},
        },
        "impostor_tier1_wrong_window_rate": pm["impostor"]["tier1_wrong_window_rate"],
        "correlated_noisy_tier1_wrong_window_rate":
            pm["correlated_noisy"]["tier1_wrong_window_rate"],
    }


def main() -> None:
    cases = corpus.load_corpus()
    out = {"runs_per_case": RUNS_PER_CASE, "cases": len(cases)}

    print("=== v3 ===", flush=True)
    v3 = run(interview.InterviewConfig(), cases, "v3")
    out["v3"] = v3
    out["v3_gates"] = gates(v3)

    print("=== free-text traits ===", flush=True)
    ft = run(interview.InterviewConfig(), cases, "free-text", free_text=True)
    out["free_text"] = {"per_model": ft["per_model"], "gates": gates(ft)}

    print("=== sensitivity over r ===", flush=True)
    out["sensitivity_r"] = {}
    for r in (0.50, 0.60, 0.75):
        res = run(interview.InterviewConfig(channel_reliability=r), cases, f"r={r}")
        out["sensitivity_r"][str(r)] = {"gates": gates(res), "per_model": res["per_model"]}

    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== v3 per answerer ===")
    for m in ANSWERERS:
        s = v3["per_model"][m]
        print(
            f"{m:18} T1 {s['tier1_rate']:>6.1%} T3/4 {s['tier3_or_4_rate']:>6.1%} "
            f"wrong {s['tier1_wrong_window_rate']:>6.2%} sign {s['sign_recovery_rate']:>6.1%} "
            f"err {str(s['tier1_median_abs_error']):>5} q {s['median_questions']:>4} "
            f"s1 {s['median_stage1_rounds']:>3}"
        )
    print("\n=== gates ===")
    for k in ("G1_safety", "G2_usefulness", "G3_refusal", "G4_cost", "G5_sign_recovery"):
        g = out["v3_gates"][k]
        print(f"{k}: {'PASS' if g['pass'] else 'FAIL'}  {g}")
    print(f"impostor {out['v3_gates']['impostor_tier1_wrong_window_rate']:.2%}  "
          f"correlated {out['v3_gates']['correlated_noisy_tier1_wrong_window_rate']:.2%}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
