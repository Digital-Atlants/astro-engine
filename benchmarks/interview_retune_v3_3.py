"""v3.3.1: the last retune, spent on `tier2_chance_p` with decan trust at 0.40.

Discipline, because a retune is the one thing in this project that can quietly
turn measurement into fitting:

* **Train only.** The sweep sees the 29 training cases. The 12 holdout cases
  are scored once, for the winner and the baseline, after the choice is made.
* **Ranked, not counted.** The winner is chosen by the gate priority order,
  so a configuration that passes a higher gate and fails a lower one beats one
  that does the reverse. G6, G6-sun and G8 are gone with Tier 3.
* **One parameter swept.** `decan_reliability` is fixed at 0.40 - the owner's
  decision, taken on the v3.3 sensitivity row - and is not a free variable
  here. `tier2_chance_p` is the sweep.
* **The baseline is in the sweep.** 0.20 is the shipped value, so the table
  shows what the retune bought against doing nothing.

`tier2_chance_p` is the right lever for the failing gate. G7 asks how often a
Tier 2 shortlist misses the truth, and the parameter is the ceiling on how
much of the channel agreement behind a shortlist may be chance. Lowering it
refuses more shortlists; the cost lands on the answerers who need one.

    python benchmarks/interview_retune_v3_3.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import interview  # noqa: E402
from benchmarks import interview_harness_v3_3 as h  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "interview_retune_v3_3.json"

# Frozen before the sweep ran.
GRID = (0.20, 0.15, 0.10, 0.05, 0.02)
DECAN_RELIABILITY = 0.40
BASELINE = 0.20
RUNS_TRAIN = 20
RUNS_FINAL = 40

# Tier 3 is gone, so G6, G6-sun and G8 are not in the ranking any more.
RANKED = ("G1_safety", "G7_tier2_window", "G3_refusal", "G2_usefulness",
          "G5_sign_recovery", "G4_cost")


def rank_key(gates: dict) -> tuple:
    return tuple(1 if gates[name]["pass"] else 0 for name in RANKED)


def worst(gates: dict, name: str) -> float:
    per = gates[name].get("per_model") or {}
    return max(per.values()) if per else 0.0


def evaluate(cases, chance_p, runs, label):
    cfg = interview.InterviewConfig(
        tier2_chance_p=chance_p, decan_reliability=DECAN_RELIABILITY
    )
    res = h.run(cfg, cases, label, runs=runs)
    return res, h.gates(res)


def summarise(gates: dict, per_model: dict) -> dict:
    return {
        "rank": rank_key(gates),
        "G1_worst": round(worst(gates, "G1_safety"), 4),
        "G7_worst": round(worst(gates, "G7_tier2_window"), 4),
        "G1_pass": gates["G1_safety"]["pass"],
        "G7_pass": gates["G7_tier2_window"]["pass"],
        "G3_random_tier4": gates["G3_refusal"]["tier4_rate"],
        "G3_pass": gates["G3_refusal"]["pass"],
        "G2_perfect_tier1": gates["G2_usefulness"]["tier1_rate"],
        "G2_pass": gates["G2_usefulness"]["pass"],
        "G5_perfect": gates["G5_sign_recovery"]["perfect"],
        "G5_iid": gates["G5_sign_recovery"]["iid_noisy"],
        "G5_pass": gates["G5_sign_recovery"]["pass"],
        "G4_median_questions": gates["G4_cost"]["median_questions"],
        "G4_pass": gates["G4_cost"]["pass"],
        "sun_attributor_G1": per_model["sun_attributor"]["tier1_wrong_window_rate"],
        "sun_attributor_G7": per_model["sun_attributor"]["tier2_wrong_window_rate"],
        "sun_attributor_tier4": per_model["sun_attributor"]["tier4_rate"],
        "sun_attributor_flagged": per_model["sun_attributor"]["sun_attribution_flag_rate"],
        "correlated_noisy_G1": per_model["correlated_noisy"]["tier1_wrong_window_rate"],
        "impostor_G1": per_model["impostor"]["tier1_wrong_window_rate"],
        "dont_know_heavy_tier2": per_model["dont_know_heavy"]["tier2_rate"],
        "iid_noisy_tier2": per_model["iid_noisy"]["tier2_rate"],
    }


def chance_p_distribution(cases, runs=6):
    """Why the sweep is flat: the quantity `tier2_chance_p` tests is bimodal.

    `chance_agreement` returns 1.0 by construction when the channels'
    supported regions do not intersect, and a product of small partition
    probabilities when they do. There is no continuum between the two, so the
    threshold has a wide dead zone and every value inside it selects exactly
    the same sessions. Measured here rather than asserted.
    """
    import datetime as dt
    import random
    import statistics

    cfg = interview.InterviewConfig(decan_reliability=DECAN_RELIABILITY)
    out = {}
    for model in ("perfect", "iid_noisy", "random", "dont_know_heavy"):
        seen, at_tier2 = [], []
        for case in cases:
            grid = interview.ChartGrid(
                dt.date.fromisoformat(case["birth_date"]),
                case["place"]["lat"], case["place"]["lon"],
                case["place"]["tz"], cfg.house_system)
            hh, mm = map(int, case["known_time"].split(":"))
            truth = hh * 60 + mm
            for k in range(runs):
                seed = h._seed(case["case_id"], model, k)
                person = h.Answerer(
                    model, random.Random(seed), grid.asc_sign[truth], truth,
                    (truth + 360) % interview.N_GRID,
                    grid.asc_sign[(truth + 360) % interview.N_GRID],
                    grid.sun_sign)
                answers, windows = [], None
                for _ in range(h.MAX_STEPS):
                    post, _, _ = interview.build_posterior(grid, answers, cfg)
                    q = interview.next_question(grid, post, answers, cfg)
                    if q is None:
                        break
                    if q["channel"] == "portrait":
                        windows = [tuple(w) for w in q["windows"]]
                    entry = {"question_id": q["question_id"],
                             "channel": q["channel"],
                             "subject": q.get("subject"),
                             "variant": q.get("variant", "a"),
                             "answer_ids": person.answer(q, grid, windows)}
                    if "offered_tag_ids" in q:
                        entry["offered_tag_ids"] = q["offered_tag_ids"]
                    if q["channel"] == "portrait":
                        entry["windows"] = [list(w) for w in windows or []]
                    answers.append(entry)
                post, trace, pairs = interview.build_posterior(grid, answers, cfg)
                p_chance, _ = interview.chance_agreement(trace)
                tier = interview.assign_tier(post, trace, cfg, pairs,
                                             grid.asc_sign,
                                             sun_sign=grid.sun_sign)
                seen.append(p_chance)
                if tier["tier"] == 2:
                    at_tier2.append(p_chance)
        out[model] = {
            "n": len(seen),
            "median": statistics.median(seen),
            "fraction_at_one": sum(1 for x in seen if x >= 0.999) / len(seen),
            "tier2_rows": len(at_tier2),
            "max_chance_p_among_tier2": max(at_tier2) if at_tier2 else None,
        }
    return out


def main() -> None:
    cases = corpus.load_corpus()
    train = [c for c in cases if c["split"] == "train"]
    holdout = [c for c in cases if c["split"] == "holdout"]
    print(f"train {len(train)} cases, holdout {len(holdout)} cases "
          f"(holdout untouched until the choice is made)")

    sweep = {}
    for chance_p in GRID:
        res, gates = evaluate(train, chance_p, RUNS_TRAIN, f"train-p{chance_p}")
        sweep[f"{chance_p:.2f}"] = summarise(gates, res["per_model"])
        s = sweep[f"{chance_p:.2f}"]
        print(f"p={chance_p:.2f} rank={s['rank']} G1 {s['G1_worst']:.2%} "
              f"G7 {s['G7_worst']:.2%} G3 {s['G3_random_tier4']:.1%} "
              f"G2 {s['G2_perfect_tier1']:.1%} G5 {s['G5_iid']:.1%} "
              f"dkh-T2 {s['dont_know_heavy_tier2']:.1%}")

    # Ranked choice. Ties on the ranking go to the value that keeps the most
    # Tier 2 coverage for the answerers who need a shortlist, because a
    # refusal is safe but useless; ties after that go to the baseline, so the
    # retune has to earn the change.
    def key(item):
        p, s = item
        return (s["rank"], s["dont_know_heavy_tier2"], float(p) == BASELINE)

    winner_p, winner = max(sweep.items(), key=key)
    print(f"\ntrain winner: tier2_chance_p={winner_p} rank={winner['rank']}")
    changed = float(winner_p) != BASELINE
    print("retune spent" if changed else "retune NOT spent: baseline wins on train")

    # Holdout, scored once, for the winner and for the baseline.
    final = {}
    for name, p in (("winner", float(winner_p)), ("baseline", BASELINE)):
        res, gates = evaluate(holdout, p, RUNS_FINAL, f"holdout-{name}")
        final[name] = {"tier2_chance_p": p,
                       **summarise(gates, res["per_model"])}
        s = final[name]
        print(f"holdout {name:9} p={p:.2f} rank={s['rank']} "
              f"G1 {s['G1_worst']:.2%} G7 {s['G7_worst']:.2%} "
              f"G3 {s['G3_random_tier4']:.1%} G2 {s['G2_perfect_tier1']:.1%} "
              f"G5 {s['G5_iid']:.1%}")

    # And the full corpus at the final configuration, which is what the report
    # quotes as the shipped numbers.
    full_res, full_gates = evaluate(cases, float(winner_p), RUNS_FINAL, "full-final")
    print("\n=== full corpus, final configuration ===")
    for m in h.ANSWERERS:
        s = full_res["per_model"][m]
        print(f"{m:18} T1 {s['tier1_rate']:>6.1%} T2 {s['tier2_rate']:>6.1%} "
              f"T4 {s['tier4_rate']:>6.1%} | G1 {s['tier1_wrong_window_rate']:>6.2%} "
              f"G7 {s['tier2_wrong_window_rate']:>6.2%} | "
              f"sign {s['sign_recovery_rate']:>6.1%} "
              f"sunflag {s['sun_attribution_flag_rate']:>6.1%} "
              f"q {s['median_questions']:>4}")
    print("\n=== gates, ranked ===")
    for name in RANKED:
        g = full_gates[name]
        print(f"{name:20} {'PASS' if g['pass'] else 'FAIL'}  "
              f"{ {k: v for k, v in g.items() if k != 'pass'} }")

    dist = chance_p_distribution(cases)
    print()
    print("=== why the sweep is flat: chance_p is bimodal ===")
    for model, d in dist.items():
        print(f"{model:18} median {d['median']:.2e} "
              f"at-1.0 {d['fraction_at_one']:.0%} | "
              f"tier-2 rows {d['tier2_rows']}, max chance_p among them "
              f"{(d['max_chance_p_among_tier2'] or 0):.2e}")

    OUT.write_text(json.dumps({
        "chance_p_distribution": dist,
        "grid": list(GRID),
        "decan_reliability": DECAN_RELIABILITY,
        "baseline_tier2_chance_p": BASELINE,
        "runs_per_case_train": RUNS_TRAIN,
        "runs_per_case_final": RUNS_FINAL,
        "ranked_gates": list(RANKED),
        "train_cases": len(train),
        "holdout_cases": len(holdout),
        "train_sweep": sweep,
        "train_winner": winner_p,
        "retune_spent": changed,
        "holdout": final,
        "full_final": {"per_model": full_res["per_model"], "gates": full_gates},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
