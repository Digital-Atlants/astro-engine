"""v2 harness: seven answerer models, paraphrase pairs, professional mode.

What this measures is detection logic - whether the tiers respond correctly to
answer quality - not astrological accuracy, which inherits from the ceiling
measurements in RESULTS_SUBSIGN.md. Answer quality is the variable being
simulated, so simulating it is the point.

    python benchmarks/interview_harness_v2.py
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

OUT = pathlib.Path(__file__).resolve().parent / "interview_gates_v2.json"

RUNS_PER_CASE = 20
MAX_STEPS = 14
CORRELATION = 0.7  # correlated-noisy: chance the same error repeats

SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]

ANSWERERS = ("perfect", "iid_noisy", "correlated_noisy", "adjacent_sign",
             "random", "dont_know_heavy", "impostor")
GATED = ("perfect", "iid_noisy", "adjacent_sign", "random", "dont_know_heavy")


def true_label(grid, question, minute, windows):
    labels = interview.partition_for(
        grid, question["channel"], question.get("subject"), windows
    )
    label = labels[minute % interview.N_GRID]
    valid = {o["answer_id"] for o in question["options"]}
    return label if label in valid else None


class Answerer:
    """One simulated person for one session.

    State is kept per question key so that a *systematic* error repeats across
    both phrasings while an *independent* error does not. That distinction is
    the whole point of asking twice, so the models have to represent it.
    """

    def __init__(self, model: str, rng: random.Random, truth: int, impostor: int):
        self.model = model
        self.rng = rng
        self.truth = truth
        self.impostor = impostor
        self.memory: dict[tuple, dict] = {}
        self.sign_shift = rng.choice([-1, 1])

    def answer(self, question: dict, grid, windows) -> list[str]:
        options = [o["answer_id"] for o in question["options"]]
        if not options:
            return []
        key = (question["channel"], question.get("subject"))
        variant = question.get("variant", "a")

        if self.model == "random":
            pick = self.rng.choice(options + ["__cannot_choose__"])
            return [] if pick == "__cannot_choose__" else [pick]

        reference = self.impostor if self.model == "impostor" else self.truth
        correct = true_label(grid, question, reference, windows)
        if correct is None:
            return []

        if self.model == "dont_know_heavy":
            # Independent per phrasing: a person who often shrugs shrugs again.
            if self.rng.random() < 0.5:
                return []
            return [correct]

        if self.model == "adjacent_sign":
            if question["channel"] != "rising_sign":
                return [correct]
            # A stable misperception: the same neighbour both times.
            idx = SIGNS.index(correct) if correct in SIGNS else None
            if idx is None:
                return [correct]
            neighbour = SIGNS[(idx + self.sign_shift) % 12]
            return [neighbour] if neighbour in options else [correct]

        if self.model == "iid_noisy":
            # Each phrasing independently wrong: paraphrase should catch it.
            if self.rng.random() < 0.2:
                others = [o for o in options if o != correct]
                if others:
                    return [self.rng.choice(others)]
            return [correct]

        if self.model == "correlated_noisy":
            state = self.memory.get(key)
            if variant == "a" or state is None:
                wrong = self.rng.random() < 0.2
                others = [o for o in options if o != correct]
                pick = self.rng.choice(others) if (wrong and others) else correct
                state = {
                    "wrong": wrong and bool(others),
                    "answer": pick,
                    "repeats": self.rng.random() < CORRELATION,
                }
                self.memory[key] = state
                return [pick]
            # Second phrasing: the error repeats only if it is the kind of
            # error a person holds about themselves.
            if state["wrong"] and state["repeats"] and state["answer"] in options:
                return [state["answer"]]
            return [correct]

        return [correct]  # perfect, impostor


def build_inventory(grid, truth: int, rng: random.Random, model: str) -> dict:
    """A professional's sphere inventory, derived from the chart at the true
    time and then degraded by the same error model as the answers."""
    counts = {h: 0 for h in range(1, 13)}
    for name, _ in interview.core.PLANETS:
        counts[grid.planet_house[name][truth]] += 1
    inventory = {}
    for h in range(1, 13):
        status = "dominant" if counts[h] >= 2 else ("present" if counts[h] == 1 else "absent")
        if model in ("iid_noisy", "correlated_noisy") and rng.random() < 0.2:
            status = rng.choice(["dominant", "present", "absent", "unknown"])
        elif model == "random":
            status = rng.choice(["dominant", "present", "absent", "unknown"])
        elif model == "dont_know_heavy" and rng.random() < 0.5:
            status = "unknown"
        inventory[str(h)] = {"status": status, "source": "observed"}
    return inventory


def simulate(grid, truth: int, model: str, seed: int, cfg: interview.InterviewConfig,
             professional: bool = False) -> dict:
    rng = random.Random(seed)
    person = Answerer(model, rng, truth, (truth + 360) % interview.N_GRID)
    inventory = build_inventory(grid, truth, rng, model) if professional else None
    source = "observed" if professional else "client_report"

    answers: list[dict] = []
    windows = None
    asked = 0
    from_inventory = 0
    mover_questions = 0

    for _ in range(MAX_STEPS):
        posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
        question = interview.next_question(grid, posterior, answers, cfg, inventory)
        if question is None:
            break
        if question["channel"] == "portrait":
            windows = [tuple(w) for w in question["windows"]]
        if question["channel"] == "mover_house" and question.get("variant") == "a":
            mover_questions += 1

        from_inv = question.get("answered_from_inventory")
        base = {
            "question_id": question["question_id"],
            "channel": question["channel"],
            "subject": question.get("subject"),
            "variant": question.get("variant", "a"),
            "source": source,
        }
        if question["channel"] == "portrait":
            base["windows"] = [list(w) for w in windows or []]

        if from_inv:
            # The inventory is the second observation of the same partition,
            # from a different source. Work item 4.1: that counts as a pair,
            # so the agreement logic applies exactly as it does to a repeated
            # phrasing - the astrologer's record is checked against what the
            # client says, not substituted for it.
            from_inventory += 1
            answers.append({**base, "variant": "a", "source": "observed",
                            "answer_ids": from_inv})
            answers.append({**base, "variant": "b", "source": source,
                            "answer_ids": person.answer(question, grid, windows)})
            asked += 1
        else:
            answers.append({**base, "answer_ids": person.answer(question, grid, windows)})
            asked += 1

    posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
    tier = interview.assign_tier(posterior, trace, cfg, pairs)

    issued = tier["tier"] in (1, 2) and tier["windows"]
    contains, err, width = False, None, None
    if issued:
        w = tier["windows"][0]
        width = w["width_minutes"]
        mh, mm = map(int, w["midpoint"].split(":"))
        d = abs((mh * 60 + mm) - truth) % interview.N_GRID
        err = min(d, interview.N_GRID - d)
        contains = any(_contains(x, truth) for x in tier["windows"])

    return {
        "tier": tier["tier"],
        "questions": asked,
        "from_inventory": from_inventory,
        "mover_questions": mover_questions,
        "issued": bool(issued),
        "window_contains_truth": contains,
        "abs_error_minutes": err,
        "window_minutes": width,
        "agreeing_pairs": pairs["agreeing_pairs"],
        "disagreeing_pairs": pairs["disagreeing_pairs"],
        "session_reliability": pairs["session_reliability"],
    }


def _contains(window, minute) -> bool:
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
    t1_wrong = [r for r in t1 if not r["window_contains_truth"]]
    t1_errs = [r["abs_error_minutes"] for r in t1 if r["abs_error_minutes"] is not None]
    t1_widths = [r["window_minutes"] for r in t1 if r["window_minutes"] is not None]
    issued = [r for r in rows if r["issued"]]
    errs = [r["abs_error_minutes"] for r in issued if r["abs_error_minutes"] is not None]
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
        "median_abs_error": statistics.median(errs) if errs else None,
        "median_questions": statistics.median(r["questions"] for r in rows),
        "mean_questions": round(statistics.fmean(r["questions"] for r in rows), 2),
        "mean_agreeing_pairs": round(statistics.fmean(r["agreeing_pairs"] for r in rows), 2),
        "mean_disagreeing_pairs": round(statistics.fmean(r["disagreeing_pairs"] for r in rows), 2),
        "mean_session_reliability": round(
            statistics.fmean(r["session_reliability"] for r in rows), 4
        ),
        "inventory_covered_movers": round(
            statistics.fmean(
                (r["from_inventory"] / r["mover_questions"]) if r["mover_questions"] else 0.0
                for r in rows
            ),
            4,
        ),
    }


def run(cfg, cases, label, professional=False, models=ANSWERERS) -> dict:
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
                row = simulate(grid, truth, model, seed, cfg, professional)
                row["case_id"] = case["case_id"]
                row["split"] = case["split"]
                per_model[model].append(row)
    return {
        "label": label,
        "seconds": round(time.perf_counter() - t0, 1),
        "per_model": {m: summarise(rows) for m, rows in per_model.items()},
    }


def gates(result: dict) -> dict:
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
    g3 = pm["random"]["tier3_or_4_rate"] >= 0.95 if "random" in pm else None
    g4 = perfect["median_questions"] <= 8
    return {
        "G1_safety": {"pass": bool(g1), "per_model": rates, "pooled": round(pooled, 4)},
        "G2_usefulness": {
            "pass": bool(g2),
            "tier1_rate": perfect["tier1_rate"],
            "tier1_max_window_minutes": perfect["tier1_max_window_minutes"],
            "tier1_contains_truth_rate": perfect["tier1_contains_truth_rate"],
            "tier1_median_abs_error": perfect["tier1_median_abs_error"],
        },
        "G3_refusal": {
            "pass": bool(g3),
            "tier3_or_4_rate": pm["random"]["tier3_or_4_rate"] if "random" in pm else None,
        },
        "G4_cost": {"pass": bool(g4), "median_questions": perfect["median_questions"]},
        "impostor_tier1_wrong_window_rate": pm.get("impostor", {}).get(
            "tier1_wrong_window_rate"
        ),
        "correlated_noisy_tier1_wrong_window_rate": pm.get(
            "correlated_noisy", {}
        ).get("tier1_wrong_window_rate"),
    }


def main() -> None:
    cases = corpus.load_corpus()
    out = {"runs_per_case": RUNS_PER_CASE, "cases": len(cases)}

    print("=== v2 (paraphrase + conservative r) ===", flush=True)
    v2 = run(interview.InterviewConfig(), cases, "v2")
    out["v2"] = v2
    out["v2_gates"] = gates(v2)

    print("=== isolation ===", flush=True)
    iso = {
        "v1_baseline_r075_no_repeat": run(
            interview.InterviewConfig(channel_reliability=0.75, repeat=False),
            cases, "v1-baseline"),
        "paraphrase_only_r075": run(
            interview.InterviewConfig(channel_reliability=0.75, repeat=True),
            cases, "paraphrase-only"),
        "conservative_only_r060": run(
            interview.InterviewConfig(channel_reliability=0.60, repeat=False),
            cases, "conservative-only"),
    }
    out["isolation"] = {k: {"per_model": v["per_model"], "gates": gates(v)}
                        for k, v in iso.items()}

    print("=== sensitivity over r ===", flush=True)
    out["sensitivity_r"] = {}
    for r in (0.50, 0.60, 0.75):
        res = run(interview.InterviewConfig(channel_reliability=r), cases, f"r={r}")
        out["sensitivity_r"][str(r)] = {"gates": gates(res), "per_model": res["per_model"]}

    print("=== professional mode ===", flush=True)
    pro = run(
        interview.InterviewConfig(repeat=False, mode="professional"),
        cases, "professional", professional=True,
    )
    out["professional"] = pro
    out["professional_gates"] = gates(pro)

    print("=== source-weight sensitivity ===", flush=True)
    out["sensitivity_source"] = {}
    original = dict(interview.SOURCE_TRUST)
    for observed in (0.70, 0.80, 0.90):
        interview.SOURCE_TRUST["observed"] = observed
        res = run(interview.InterviewConfig(repeat=False, mode="professional"),
                  cases, f"observed={observed}", professional=True)
        out["sensitivity_source"][str(observed)] = {
            "gates": gates(res), "per_model": res["per_model"]
        }
    interview.SOURCE_TRUST.update(original)

    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== v2 per answerer ===")
    for m in ANSWERERS:
        s = v2["per_model"][m]
        print(
            f"{m:18} T1 {s['tier1_rate']:>6.1%} T3/4 {s['tier3_or_4_rate']:>6.1%} "
            f"wrongT1 {s['tier1_wrong_window_rate']:>6.2%} "
            f"err {str(s['tier1_median_abs_error']):>5} "
            f"win {str(s['tier1_median_window_minutes']):>5} "
            f"q {s['median_questions']:>4} "
            f"pairs +{s['mean_agreeing_pairs']}/-{s['mean_disagreeing_pairs']}"
        )
    print("\n=== v2 gates ===")
    for k in ("G1_safety", "G2_usefulness", "G3_refusal", "G4_cost"):
        print(f"{k}: {'PASS' if out['v2_gates'][k]['pass'] else 'FAIL'}  {out['v2_gates'][k]}")
    print(f"impostor: {out['v2_gates']['impostor_tier1_wrong_window_rate']:.2%}")
    print(f"correlated-noisy: {out['v2_gates']['correlated_noisy_tier1_wrong_window_rate']:.2%}")
    print("\n=== professional ===")
    for m in ANSWERERS:
        s = pro["per_model"][m]
        print(
            f"{m:18} T1 {s['tier1_rate']:>6.1%} wrongT1 {s['tier1_wrong_window_rate']:>6.2%} "
            f"q {s['median_questions']:>4} inv {s['inventory_covered_movers']:>5.0%}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
