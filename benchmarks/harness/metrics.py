"""Aggregation: hit rates, error percentiles, calibration, signal versus null."""

from __future__ import annotations

import statistics

from . import protocol

HIT_THRESHOLDS = (2, 5, 15, 30)


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile. Small n, so no numpy dependency."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def error_minutes(run: dict, case: dict) -> int:
    return protocol.circular_error_minutes(
        run["returned_minute"], _known_minute(case)
    )


def _known_minute(case: dict) -> int:
    hh, mm = map(int, case["known_time"].split(":"))
    return hh * 60 + mm


def accuracy_table(records: list[dict]) -> dict:
    """Hit rates and error percentiles over one arm's real-data records."""
    errs = [r["abs_error_minutes"] for r in records]
    n = len(errs)
    row = {
        "n": n,
        "median_abs_error": percentile([float(e) for e in errs], 0.5),
        "p90_abs_error": percentile([float(e) for e in errs], 0.9),
        "mean_abs_error": statistics.fmean(errs) if errs else None,
    }
    for t in HIT_THRESHOLDS:
        hits = sum(1 for e in errs if e <= t)
        row[f"hits_{t}"] = hits
        row[f"hit_rate_{t}"] = hits / n if n else None
    return row


def calibration_table(records: list[dict], arm: str) -> list[dict]:
    """Of the cases at each self-reported confidence level, how many hit +/-5?

    Ours has no confidence *level*, only `residual_window_minutes`; a narrower
    residual window is the engine claiming a sharper answer, so it is bucketed
    from narrow (highest self-reported confidence) to wide.
    """
    buckets: dict[str, list[dict]] = {}
    for r in records:
        buckets.setdefault(_confidence_bucket(r, arm), []).append(r)

    order = (
        ["high", "medium", "low", "unknown"]
        if arm == "vendor"
        else ["0 min", "4-12 min", "16-60 min", ">60 min"]
    )
    rows = []
    for label in order:
        group = buckets.get(label)
        if not group:
            continue
        within5 = sum(1 for r in group if r["abs_error_minutes"] <= 5)
        within15 = sum(1 for r in group if r["abs_error_minutes"] <= 15)
        rows.append(
            {
                "bucket": label,
                "n": len(group),
                "within_5": within5,
                "within_5_rate": within5 / len(group),
                "within_15": within15,
                "within_15_rate": within15 / len(group),
                "median_abs_error": percentile(
                    [float(r["abs_error_minutes"]) for r in group], 0.5
                ),
            }
        )
    for label, group in sorted(buckets.items()):
        if label not in order:
            rows.append({"bucket": label, "n": len(group), "within_5": None})
    return rows


def _confidence_bucket(record: dict, arm: str) -> str:
    conf = record["own_confidence"]
    if arm == "vendor":
        return conf.get("level") or "unknown"
    residual = conf.get("residual_window_minutes")
    if residual is None:
        return "unknown"
    if residual == 0:
        return "0 min"
    if residual <= 12:
        return "4-12 min"
    if residual <= 60:
        return "16-60 min"
    return ">60 min"


def signal_vs_null(real: list[dict], null: list[dict]) -> dict:
    """peak/mean on real data against the same statistic on shuffled dates."""
    r = [x["peak_over_mean"] for x in real if x["peak_over_mean"] is not None]
    n = [x["peak_over_mean"] for x in null if x["peak_over_mean"] is not None]
    out = {
        "real_n": len(r),
        "null_n": len(n),
        "real_median": percentile(r, 0.5),
        "null_median": percentile(n, 0.5),
        "real_p10": percentile(r, 0.10),
        "null_p90": percentile(n, 0.90),
        "real_min": min(r) if r else None,
        "null_max": max(n) if n else None,
    }
    if len(r) > 1 and len(n) > 1:
        sr, sn = statistics.stdev(r), statistics.stdev(n)
        pooled = ((sr**2 + sn**2) / 2) ** 0.5
        out["mean_gap"] = statistics.fmean(r) - statistics.fmean(n)
        out["cohens_d"] = (out["mean_gap"] / pooled) if pooled > 0 else None
        # Fraction of (real, null) pairs where real ranks higher. 0.5 is chance.
        wins = sum(1 for a in r for b in n if a > b)
        ties = sum(1 for a in r for b in n if a == b)
        out["auc"] = (wins + 0.5 * ties) / (len(r) * len(n))
    return out


def null_accuracy(null_records: list[dict]) -> dict:
    """Arm C hit rates. This is the floor any real result must clear."""
    return accuracy_table(null_records)


def hour_histogram(records: list[dict]) -> dict[int, int]:
    counts = {h: 0 for h in range(24)}
    for r in records:
        counts[r["returned_minute"] // 60] += 1
    return counts
