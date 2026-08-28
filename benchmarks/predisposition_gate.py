"""Work item 4: score the predisposition channel, matched against mismatched.

The constraint is a reweighting, never a filter: a `yes` for an item mapped to
house H adds the number of planets tenanting H at that candidate time, a `no`
subtracts it, `unknown` contributes nothing. Nothing is ever removed from the
candidate set, so a wrong answer degrades the result instead of deleting the
truth.

Everything runs inside the true rising-sign block, so this measures the channel
alone and not stage 1.

The null is mismatched pairs: subject A's answers scored against subject B's
chart, every case against at least five others. If mismatched pairs narrow as
well as matched ones, the mapping is vacuous.

    python benchmarks/predisposition_gate.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import core  # noqa: E402
from benchmarks.harness import blocks, corpus, protocol  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
OUT = pathlib.Path(__file__).resolve().parent / "predisposition_gate.json"

MISMATCHES = 5


def house_counts(case: dict, minutes: list[int]) -> dict[int, dict[int, int]]:
    """Planets per house, per candidate minute, Placidus."""
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
        counts = {h: 0 for h in range(1, 13)}
        for _, pid in core.PLANETS:
            counts[core.house_of(core.planet_position(jd, pid)[0], cusps)] += 1
        out[m] = counts
    return out


def audited_answers(coding: str) -> dict[str, dict[str, str]]:
    raw = json.loads((FIX / "predisposition_answers.json").read_text(encoding="utf-8"))
    audit = json.loads((FIX / "predisposition_audit.json").read_text(encoding="utf-8"))
    rejected = {
        (v["case"], v["item"]) for v in audit["verdicts"] if v["verdict"] == "reject"
    }
    out = {}
    for cid, row in raw.items():
        out[cid] = {}
        for item, v in row.items():
            ans = v[coding]
            if ans == "yes" and (cid, item) in rejected:
                ans = "unknown"  # demoted by the audit, never flipped to `no`
            out[cid][item] = ans
    return out


def support_curve(answers: dict[str, str], counts: dict[int, dict[int, int]],
                  mapping: list[dict]) -> dict[int, float]:
    curve = {m: 0.0 for m in counts}
    for entry in mapping:
        ans = answers.get(entry["item"], "unknown")
        if ans == "unknown":
            continue
        sign = 1.0 if ans == "yes" else -1.0
        for m, c in counts.items():
            curve[m] += sign * sum(c[h] for h in entry["houses"])
    return curve


def survivors(curve: dict[int, float]) -> list[int]:
    """Candidates at the maximum support. Never empty by construction."""
    best = max(curve.values())
    return sorted(m for m, v in curve.items() if v == best)


def evaluate(curve: dict[int, float], known: int) -> dict:
    surv = survivors(curve)
    mid = surv[(len(surv) - 1) // 2]
    return {
        "window_minutes": len(surv) * protocol.STEP_MINUTES,
        "true_survives": min(
            protocol.circular_error_minutes(m, known) for m in surv
        )
        <= protocol.STEP_MINUTES,
        "midpoint_err": protocol.circular_error_minutes(mid, known),
    }


def main() -> None:
    mapping = json.loads((FIX / "predisposition_mapping.json").read_text(encoding="utf-8"))["kept"]
    cases = corpus.load_corpus()
    by_id = {c["case_id"]: c for c in cases}
    results = {}

    for coding in ("strict", "documented_absence"):
        answers = audited_answers(coding)
        matched, mismatched, paired = [], [], []
        rng = random.Random(9)

        for case in cases:
            cid = case["case_id"]
            block = blocks.correct_block_minutes(case)
            known = blocks.case_known_minute(case)
            counts = house_counts(case, block)

            own = evaluate(support_curve(answers[cid], counts, mapping), known)
            own["case_id"] = cid
            own["split"] = case["split"]
            matched.append(own)

            others = [c["case_id"] for c in cases if c["case_id"] != cid]
            rng.shuffle(others)
            mism = []
            for other in others[:MISMATCHES]:
                r = evaluate(support_curve(answers[other], counts, mapping), known)
                r["case_id"] = cid
                r["donor"] = other
                mismatched.append(r)
                mism.append(r["window_minutes"])
            paired.append((own["window_minutes"], statistics.fmean(mism)))

        obs = statistics.fmean(a - b for a, b in paired)
        rng2 = random.Random(17)
        n_perm, hits = 20000, 0
        for _ in range(n_perm):
            tot = 0.0
            for a, b in paired:
                x, y = (a, b) if rng2.random() < 0.5 else (b, a)
                tot += x - y
            if tot / len(paired) <= obs:
                hits += 1
        p = hits / n_perm

        mw = [r["window_minutes"] for r in matched]
        uw = [r["window_minutes"] for r in mismatched]
        wins = sum(1 for a in mw for b in uw if a < b)
        ties = sum(1 for a in mw for b in uw if a == b)
        auc = (wins + 0.5 * ties) / (len(mw) * len(uw))

        def block(rows, key):
            v = [r[key] for r in rows]
            return statistics.median(v)

        results[coding] = {
            "n_matched": len(matched),
            "n_mismatched": len(mismatched),
            "matched": {
                "median_window": statistics.median(mw),
                "true_survives_rate": sum(1 for r in matched if r["true_survives"]) / len(matched),
                "median_midpoint_err": block(matched, "midpoint_err"),
                "hit_5": sum(1 for r in matched if r["midpoint_err"] <= 5) / len(matched),
                "hit_15": sum(1 for r in matched if r["midpoint_err"] <= 15) / len(matched),
            },
            "mismatched": {
                "median_window": statistics.median(uw),
                "true_survives_rate": sum(1 for r in mismatched if r["true_survives"]) / len(mismatched),
                "median_midpoint_err": block(mismatched, "midpoint_err"),
                "hit_5": sum(1 for r in mismatched if r["midpoint_err"] <= 5) / len(mismatched),
                "hit_15": sum(1 for r in mismatched if r["midpoint_err"] <= 15) / len(mismatched),
            },
            "auc_matched_narrower": auc,
            "mean_window_difference": obs,
            "permutation_p": p,
            "narrowing_significant": p < 0.05,
            "true_survives_80pct": (
                sum(1 for r in matched if r["true_survives"]) / len(matched)
            )
            >= 0.80,
        }

    for coding, r in results.items():
        g = r["narrowing_significant"] and r["true_survives_80pct"]
        print(f"\n=== {coding} ===")
        print(
            f"matched    window {r['matched']['median_window']:>5.0f}  "
            f"survives {r['matched']['true_survives_rate']:.0%}  "
            f"mid err {r['matched']['median_midpoint_err']:>5.0f}  "
            f"<=5 {r['matched']['hit_5']:.0%}  <=15 {r['matched']['hit_15']:.0%}"
        )
        print(
            f"mismatched window {r['mismatched']['median_window']:>5.0f}  "
            f"survives {r['mismatched']['true_survives_rate']:.0%}  "
            f"mid err {r['mismatched']['median_midpoint_err']:>5.0f}  "
            f"<=5 {r['mismatched']['hit_5']:.0%}  <=15 {r['mismatched']['hit_15']:.0%}"
        )
        print(
            f"AUC {r['auc_matched_narrower']:.3f}  mean diff "
            f"{r['mean_window_difference']:+.1f} min  p={r['permutation_p']:.4f}"
        )
        print(
            f"GATE: narrowing p<0.05 {r['narrowing_significant']}, "
            f"true survives >=80% {r['true_survives_80pct']} -> "
            f"{'PASS' if g else 'FAIL'}"
        )

    OUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
