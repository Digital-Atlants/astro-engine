"""v3.3 harness: tiers ordered by strength of claim, plus two new answerers.

Three changes from v3.2, all of them about Tier 3.

* **G8 (new) - Tier 3 has to be reachable.** A `sign_only` answerer is
  perfect on stage 1 and declines everything after. It must land in Tier 3 in
  at least 80% of runs. Without this gate a passing G6 can be arithmetic on an
  empty set, which is exactly what v3.2 shipped.
* **G6-sun (new).** A `sun_attributor` answers stage 1 as if the rising sign
  were the Sun sign - the documented self-attribution effect (van Rooij 1994).
  Its Tier 3 wrong-sign rate is gated at 5%, and the same model is run with
  the detector off so the exposure is reported before the fix as well as
  after.
* **Decan trust** is reported across {0.40, 0.50, 0.60} as a sensitivity row.
  It is a design constant and is not tuned.

Seeds are derived with SHA-256 rather than `hash()`, which is salted per
process and made the v3.2 seed set unreproducible between runs.

    python benchmarks/interview_harness_v3_3.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import random
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "interview_gates_v3_3.json"

NEWLINE = "\n"

RUNS_PER_CASE = 40
MAX_STEPS = 16
CORRELATION = 0.7

SIGNS = interview.TRAIT_SIGNS
AXIS = interview._SIGN_AXIS
STAGE1 = interview.STAGE1_CHANNELS

ANSWERERS = ("perfect", "iid_noisy", "correlated_noisy", "adjacent_sign",
             "random", "dont_know_heavy", "impostor", "sign_only",
             "sun_attributor")
# Every model that can plausibly reach a delivered sign, random included. A
# model that cannot answer coherently is exactly the one a wrong-sign gate has
# to cover.
G6_MODELS = ("perfect", "iid_noisy", "adjacent_sign", "dont_know_heavy",
             "random", "sign_only")
# v3.3.1 adds sun_attributor. It is a model of an honest person answering
# about the wrong thing - the documented self-attribution effect - not of a
# careless or adversarial one, so it belongs inside the safety gates rather
# than beside them.
G1_MODELS = ("perfect", "iid_noisy", "adjacent_sign", "random",
             "dont_know_heavy", "sign_only", "sun_attributor")

# Ranked, not counted. A configuration that passes a higher gate and fails a
# lower one beats one that does the reverse.
PRIORITY_ORDER = ("G1_safety", "G6_tier3_sign", "G6_sun_attribution",
                  "G7_tier2_window", "G3_refusal", "G8_tier3_reachable",
                  "G2_usefulness", "G5_sign_recovery", "G4_cost")


def _seed(*parts) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")


def _partition_label(grid, question, minute, windows):
    labels = interview.partition_for(
        grid, question["channel"], question.get("subject"), windows
    )
    label = labels[minute % interview.N_GRID]
    valid = {o["answer_id"] for o in question["options"]}
    return label if label in valid else None


class Answerer:
    def __init__(self, model, rng, truth_sign, truth_minute, impostor_minute,
                 impostor_sign, sun_sign):
        self.model = model
        self.rng = rng
        self.truth_sign = truth_sign
        self.truth = truth_minute
        self.impostor = impostor_minute
        self.impostor_sign = impostor_sign
        self.sun_sign = sun_sign
        self.memory: dict[tuple, dict] = {}
        self.sign_shift = rng.choice([-1, 1])

    def reference_sign(self, channel: str | None = None):
        if self.model == "impostor":
            return self.impostor_sign
        if self.model == "adjacent_sign":
            return SIGNS[(SIGNS.index(self.truth_sign) + self.sign_shift) % 12]
        if self.model == "sun_attributor" and channel in STAGE1:
            # The whole of the effect: stage 1 describes the Sun sign, which
            # the person knows, instead of the rising sign, which they do not.
            return self.sun_sign
        return self.truth_sign

    def _ideal(self, question, grid, windows) -> list[str]:
        ch = question["channel"]
        ids = [o["answer_id"] for o in question["options"]]
        sign = self.reference_sign(ch)
        if ch == "element":
            want = f"element_{AXIS[sign]['element']}"
            return [want] if want in ids else []
        if ch == "modality":
            want = f"modality_{AXIS[sign]['modality']}"
            return [want] if want in ids else []
        if ch == "sign_portrait":
            return [sign] if sign in ids else []
        reference = self.impostor if self.model == "impostor" else self.truth
        label = _partition_label(grid, question, reference, windows)
        return [label] if label else []

    def answer(self, question, grid, windows) -> list[str]:
        ids = [o["answer_id"] for o in question["options"]]
        if not ids:
            return []
        ch = question["channel"]
        key = (ch, question.get("subject"))
        variant = question.get("variant", "a")

        if self.model == "random":
            pick = self.rng.choice(ids + ["__cannot_choose__"])
            return [] if pick == "__cannot_choose__" else [pick]

        # Perfect on stage 1, "I don't know" on everything after it. This is
        # the person who recognises a temperament description of themselves
        # and has nothing to say about which house Saturn is in. Tier 3 exists
        # for exactly this session, so it is the gate that Tier 3 is reachable.
        if self.model == "sign_only" and ch not in STAGE1:
            return []

        correct = self._ideal(question, grid, windows)
        if self.model == "dont_know_heavy" and self.rng.random() < 0.5:
            return []
        if not correct:
            return []

        # The sun-attributor is confident about stage 1 and ordinarily noisy
        # everywhere else, so its wrong sign is not an artefact of being
        # unreliable in general.
        noisy = self.model in ("iid_noisy", "sun_attributor")
        if noisy and not (self.model == "sun_attributor" and ch in STAGE1):
            if self.rng.random() < 0.2:
                others = [i for i in ids if i not in correct]
                if others:
                    return [self.rng.choice(others)]
            return correct
        if noisy:
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
            if (state["wrong"] and state["repeats"]
                    and all(a in ids for a in state["answer"])):
                return state["answer"]
            return correct

        return correct


def simulate(grid, truth_minute, model, seed, cfg) -> dict:
    rng = random.Random(seed)
    truth_sign = grid.asc_sign[truth_minute]
    impostor_minute = (truth_minute + 360) % interview.N_GRID
    person = Answerer(model, rng, truth_sign, truth_minute, impostor_minute,
                      grid.asc_sign[impostor_minute], grid.sun_sign)

    answers: list[dict] = []
    windows = None
    asked = 0
    stage1_done = False
    sign_top_after_stage1 = None
    bits: dict[str, list[float]] = {}

    for _ in range(MAX_STEPS):
        posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
        q = interview.next_question(grid, posterior, answers, cfg)
        if q is None:
            break
        if q["channel"] not in STAGE1 and not stage1_done:
            stage1_done = True
            sm = interview.sign_mass(posterior, grid.asc_sign)
            sign_top_after_stage1 = max(sm, key=sm.get)
        if q["channel"] == "portrait":
            windows = [tuple(w) for w in q["windows"]]
        bits.setdefault(q["channel"], []).append(q["information_bits"])

        entry = {
            "question_id": q["question_id"],
            "channel": q["channel"],
            "subject": q.get("subject"),
            "variant": q.get("variant", "a"),
            "answer_ids": person.answer(q, grid, windows),
        }
        if "offered_tag_ids" in q:
            entry["offered_tag_ids"] = q["offered_tag_ids"]
        if q["channel"] == "portrait":
            entry["windows"] = [list(w) for w in windows or []]
        answers.append(entry)
        asked += 1

    posterior, trace, pairs = interview.build_posterior(grid, answers, cfg)
    if sign_top_after_stage1 is None:
        sm = interview.sign_mass(posterior, grid.asc_sign)
        sign_top_after_stage1 = max(sm, key=sm.get)
    tier = interview.assign_tier(posterior, trace, cfg, pairs, grid.asc_sign,
                                 sun_sign=grid.sun_sign)

    contains, err, width = False, None, None
    if tier["windows"]:
        w = tier["windows"][0]
        width = w["width_minutes"]
        mh, mm = map(int, w["midpoint"].split(":"))
        d = abs((mh * 60 + mm) - truth_minute) % interview.N_GRID
        err = min(d, interview.N_GRID - d)
        contains = any(_contains(x, truth_minute) for x in tier["windows"])

    return {
        "tier": tier["tier"],
        "questions": asked,
        "sign_recovered": sign_top_after_stage1 == truth_sign,
        "delivered_sign": tier["rising_sign"],
        "sign_correct": tier["rising_sign"] == truth_sign,
        "channel_conflict": tier["channel_conflict"],
        "sun_sign_attribution": tier["sun_sign_attribution"],
        "rising_equals_sun": truth_sign == grid.sun_sign,
        "window_contains_truth": contains,
        "abs_error_minutes": err,
        "window_minutes": width,
        "agreeing_pairs": pairs["agreeing_pairs"],
        "disagreeing_pairs": pairs["disagreeing_pairs"],
        "bits_by_stage": {k: statistics.fmean(v) for k, v in bits.items()},
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
    t2 = [r for r in rows if r["tier"] == 2]
    t3 = [r for r in rows if r["tier"] == 3]
    t1_errs = [r["abs_error_minutes"] for r in t1
               if r["abs_error_minutes"] is not None]
    t1_widths = [r["window_minutes"] for r in t1
                 if r["window_minutes"] is not None]
    stages: dict[str, list[float]] = {}
    for r in rows:
        for k, v in r["bits_by_stage"].items():
            stages.setdefault(k, []).append(v)
    return {
        "n": n,
        "tier_distribution": {str(k): round(v, 4) for k, v in tiers.items()},
        "tier1_rate": round(tiers[1], 4),
        "tier2_rate": round(tiers[2], 4),
        "tier3_rate": round(tiers[3], 4),
        "tier4_rate": round(tiers[4], 4),
        # Wrong answers as a fraction of ALL runs, the denominator v1-v3 used,
        # plus the conditional rate for reading.
        "tier1_wrong_window_rate": round(
            sum(1 for r in t1 if not r["window_contains_truth"]) / n, 4),
        "tier2_wrong_window_rate": round(
            sum(1 for r in t2 if not r["window_contains_truth"]) / n, 4),
        "tier3_wrong_sign_rate": round(
            sum(1 for r in t3 if not r["sign_correct"]) / n, 4),
        "tier1_wrong_of_issued": (
            round(sum(1 for r in t1 if not r["window_contains_truth"]) / len(t1), 4)
            if t1 else None),
        "tier2_wrong_of_issued": (
            round(sum(1 for r in t2 if not r["window_contains_truth"]) / len(t2), 4)
            if t2 else None),
        "tier3_wrong_of_issued": (
            round(sum(1 for r in t3 if not r["sign_correct"]) / len(t3), 4)
            if t3 else None),
        "tier1_contains_truth_rate": (
            round(sum(1 for r in t1 if r["window_contains_truth"]) / len(t1), 4)
            if t1 else None),
        "tier1_median_abs_error": statistics.median(t1_errs) if t1_errs else None,
        "tier1_median_window_minutes": (
            statistics.median(t1_widths) if t1_widths else None),
        "tier1_max_window_minutes": max(t1_widths) if t1_widths else None,
        "tier3_or_4_rate": round(tiers[3] + tiers[4], 4),
        "sign_recovery_rate": round(
            sum(1 for r in rows if r["sign_recovered"]) / n, 4),
        "conflict_rate": round(sum(1 for r in rows if r["channel_conflict"]) / n, 4),
        "sun_attribution_flag_rate": round(
            sum(1 for r in rows if r["sun_sign_attribution"]) / n, 4),
        "rising_equals_sun_rate": round(
            sum(1 for r in rows if r["rising_equals_sun"]) / n, 4),
        "median_questions": statistics.median(r["questions"] for r in rows),
        "mean_questions": round(statistics.fmean(r["questions"] for r in rows), 2),
        "bits_by_stage": {k: round(statistics.fmean(v), 4) for k, v in stages.items()},
        "question_count_distribution": {
            str(q): sum(1 for r in rows if r["questions"] == q)
            for q in sorted({r["questions"] for r in rows})
        },
    }


def run(cfg, cases, label, models=ANSWERERS, runs=None) -> dict:
    runs = runs or RUNS_PER_CASE
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
            for k in range(runs):
                # Seeded off the case and model only, not the run label, so
                # the same answerer sees the same draws under every config.
                row = simulate(grid, truth, model,
                               _seed(case["case_id"], model, k), cfg)
                row["case_id"] = case["case_id"]
                row["split"] = case["split"]
                per_model[model].append(row)
    return {
        "label": label,
        "runs_per_case": runs,
        "seconds": round(time.perf_counter() - t0, 1),
        "per_model": {m: summarise(rows) for m, rows in per_model.items()},
    }


def gates(result) -> dict:
    pm = result["per_model"]
    g1 = {m: pm[m]["tier1_wrong_window_rate"] for m in G1_MODELS if m in pm}
    g7 = {m: pm[m]["tier2_wrong_window_rate"] for m in G1_MODELS if m in pm}
    g6 = {m: pm[m]["tier3_wrong_sign_rate"] for m in G6_MODELS if m in pm}
    perfect = pm["perfect"]
    sun = pm["sun_attributor"]
    return {
        "G1_safety": {"pass": all(v <= 0.05 for v in g1.values()),
                      "per_model": g1},
        "G6_tier3_sign": {"pass": all(v <= 0.05 for v in g6.values()),
                          "per_model": g6},
        "G6_sun_attribution": {
            "pass": sun["tier3_wrong_sign_rate"] <= 0.05,
            "tier3_wrong_sign_rate": sun["tier3_wrong_sign_rate"],
            "tier1_wrong_window_rate": sun["tier1_wrong_window_rate"],
            "tier3_rate": sun["tier3_rate"],
            "flagged_rate": sun["sun_attribution_flag_rate"],
        },
        "G7_tier2_window": {"pass": all(v <= 0.05 for v in g7.values()),
                            "per_model": g7},
        "G3_refusal": {
            "pass": pm["random"]["tier4_rate"] >= 0.90,
            "tier4_rate": pm["random"]["tier4_rate"],
            "tier3_or_4_rate": pm["random"]["tier3_or_4_rate"],
        },
        # Tier 3 must actually be issued to the session it exists for, or a
        # passing G6 means nothing.
        "G8_tier3_reachable": {
            "pass": pm["sign_only"]["tier3_rate"] >= 0.80,
            "sign_only_tier3_rate": pm["sign_only"]["tier3_rate"],
            "sign_only_tier4_rate": pm["sign_only"]["tier4_rate"],
            "random_tier3_rate": pm["random"]["tier3_rate"],
        },
        "G2_usefulness": {
            "pass": (
                perfect["tier1_rate"] >= 0.90
                and (perfect["tier1_max_window_minutes"] or 0) <= 30
                and (perfect["tier1_contains_truth_rate"] or 0) >= 0.95
                and (perfect["tier1_median_abs_error"]
                     if perfect["tier1_median_abs_error"] is not None else 999) <= 8
            ),
            "tier1_rate": perfect["tier1_rate"],
            "tier1_max_window_minutes": perfect["tier1_max_window_minutes"],
            "tier1_contains_truth_rate": perfect["tier1_contains_truth_rate"],
            "tier1_median_abs_error": perfect["tier1_median_abs_error"],
        },
        "G5_sign_recovery": {
            "pass": (perfect["sign_recovery_rate"] >= 0.90
                     and pm["iid_noisy"]["sign_recovery_rate"] >= 0.60),
            "perfect": perfect["sign_recovery_rate"],
            "iid_noisy": pm["iid_noisy"]["sign_recovery_rate"],
        },
        "G4_cost": {"pass": perfect["median_questions"] <= 10,
                    "median_questions": perfect["median_questions"]},
        "impostor_tier1_wrong_window_rate": pm["impostor"]["tier1_wrong_window_rate"],
        "impostor_tier3_wrong_sign_rate": pm["impostor"]["tier3_wrong_sign_rate"],
        "correlated_noisy_tier1_wrong_window_rate":
            pm["correlated_noisy"]["tier1_wrong_window_rate"],
        "correlated_noisy_tier3_wrong_sign_rate":
            pm["correlated_noisy"]["tier3_wrong_sign_rate"],
    }


def rank_key(g: dict) -> tuple:
    """Ranked, not counted: a higher gate outranks every lower one."""
    return tuple(1 if g[name]["pass"] else 0 for name in PRIORITY_ORDER)


def main() -> None:
    cases = corpus.load_corpus()
    out: dict = {
        "runs_per_case": RUNS_PER_CASE,
        "cases": len(cases),
        "priority_order": list(PRIORITY_ORDER),
    }

    detector_on = run(interview.InterviewConfig(), cases, "v3.3-detector-on")
    out["v3_3"] = detector_on
    out["v3_3_gates"] = gates(detector_on)

    # Work item 3c step 1: the exposure, measured before the detector exists.
    detector_off = run(
        interview.InterviewConfig(sun_sign_detector=False), cases,
        "v3.3-detector-off",
        models=("perfect", "sun_attributor", "sign_only", "iid_noisy"),
    )
    out["detector_off"] = {"per_model": detector_off["per_model"]}

    # Work item 3b: reported, not tuned.
    out["decan_trust_sensitivity"] = {}
    for r in (0.40, 0.50, 0.60):
        res = run(
            interview.InterviewConfig(decan_reliability=r), cases,
            f"decan-r-{r}",
            models=("perfect", "iid_noisy", "random", "sign_only",
                    "correlated_noisy", "adjacent_sign", "dont_know_heavy",
                    "impostor", "sun_attributor"),
            runs=20,
        )
        out["decan_trust_sensitivity"][f"{r:.2f}"] = {
            "per_model": {
                m: {k: s[k] for k in ("tier1_rate", "tier3_rate",
                                      "tier1_wrong_window_rate",
                                      "tier3_wrong_sign_rate",
                                      "sign_recovery_rate")}
                for m, s in res["per_model"].items()
            },
            "gates": gates(res),
        }

    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")

    print("\n=== v3.3 per answerer (detector on, 40 seeds) ===")
    for m in ANSWERERS:
        s = detector_on["per_model"][m]
        print(
            f"{m:18} T1 {s['tier1_rate']:>6.1%} T2 {s['tier2_rate']:>6.1%} "
            f"T3 {s['tier3_rate']:>6.1%} T4 {s['tier4_rate']:>6.1%} | "
            f"G1 {s['tier1_wrong_window_rate']:>6.2%} "
            f"G7 {s['tier2_wrong_window_rate']:>6.2%} "
            f"G6 {s['tier3_wrong_sign_rate']:>6.2%} | "
            f"sign {s['sign_recovery_rate']:>6.1%} q {s['median_questions']:>4}"
        )

    print("\n=== sun-attributor, detector off vs on ===")
    for label, src in (("off", detector_off["per_model"]),
                       ("on", detector_on["per_model"])):
        for m in ("sun_attributor", "perfect"):
            s = src[m]
            print(f"detector {label:3} {m:15} T1 {s['tier1_rate']:>6.1%} "
                  f"T3 {s['tier3_rate']:>6.1%} "
                  f"T1-wrong {s['tier1_wrong_window_rate']:>6.2%} "
                  f"T3-wrong {s['tier3_wrong_sign_rate']:>6.2%}")

    print("\n=== gates, in priority order ===")
    for k in PRIORITY_ORDER:
        g = out["v3_3_gates"][k]
        print(f"{k:20} {'PASS' if g['pass'] else 'FAIL'}  "
              f"{ {x: y for x, y in g.items() if x != 'pass'} }")
    print(f"\nwrote {OUT}")


def shard() -> None:
    """One phase of the measurement, so the phases can run concurrently.

    The full sweep is about 43,000 simulations at ~0.11 s each. Sharding by
    phase and by answerer model turns an hour and a half of wall clock into a
    few minutes, and the seeds do not depend on the shard: `_seed` is keyed on
    the case and the model only, so a model measured in any shard sees exactly
    the same draws.

        python benchmarks/interview_harness_v3_3.py shard --out x.json             --models perfect,iid_noisy --runs 40 --decan-reliability 0.5
    """
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("shard", nargs="?")
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=",".join(ANSWERERS))
    ap.add_argument("--runs", type=int, default=RUNS_PER_CASE)
    ap.add_argument("--label", default="shard")
    ap.add_argument("--decan-reliability", type=float, default=None)
    # The detector defaults OFF in InterviewConfig, so the switch turns it ON.
    ap.add_argument("--sun-detector", action="store_true")
    args = ap.parse_args()

    kwargs = {}
    if args.decan_reliability is not None:
        kwargs["decan_reliability"] = args.decan_reliability
    if args.sun_detector:
        kwargs["sun_sign_detector"] = True

    cases = corpus.load_corpus()
    res = run(interview.InterviewConfig(**kwargs), cases, args.label,
              models=tuple(args.models.split(",")), runs=args.runs)
    pathlib.Path(args.out).write_text(
        json.dumps(res, indent=2, sort_keys=True) + NEWLINE, encoding="utf-8")
    for m, s_ in res["per_model"].items():
        print(f"{m:18} T1 {s_['tier1_rate']:>6.1%} T2 {s_['tier2_rate']:>6.1%} "
              f"T3 {s_['tier3_rate']:>6.1%} T4 {s_['tier4_rate']:>6.1%} | "
              f"G1 {s_['tier1_wrong_window_rate']:>6.2%} "
              f"G7 {s_['tier2_wrong_window_rate']:>6.2%} "
              f"G6 {s_['tier3_wrong_sign_rate']:>6.2%} | "
              f"sign {s_['sign_recovery_rate']:>6.1%} "
              f"sunflag {s_['sun_attribution_flag_rate']:>6.1%} "
              f"q {s_['median_questions']:>4}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "shard":
        shard()
    else:
        main()
