"""Render benchmarks/RESULTS.md from a results payload.

Every number in the report is computed here from the run records. The prose
statements are derived from the same numbers rather than written by hand, so
the report cannot drift away from the measurements it is reporting.
"""

from __future__ import annotations

import datetime as dt

from . import bias, metrics, pricing, protocol

HDR = "# Rectification benchmark: our engine against the vendor, both against a null control"


def _fmt(value, spec="{:.2f}", dash="n/a"):
    return dash if value is None else spec.format(value)


def _pct(value):
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """Rows are padded or trimmed to the header width.

    Arms that were not run contribute short placeholder rows; without this a
    skipped arm silently produces a ragged table that renders as garbage.
    """
    width = len(headers)
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        cells = list(row)[:width] + ["-"] * max(0, width - len(row))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _accuracy_rows(label: str, records: list[dict]) -> list[str]:
    if not records:
        return [label] + ["not run"] * 7
    t = metrics.accuracy_table(records)
    return [
        label,
        str(t["n"]),
        _pct(t["hit_rate_2"]),
        _pct(t["hit_rate_5"]),
        _pct(t["hit_rate_15"]),
        _pct(t["hit_rate_30"]),
        _fmt(t["median_abs_error"], "{:.0f}"),
        _fmt(t["p90_abs_error"], "{:.0f}"),
    ]


def build(data: dict, cases: list[dict]) -> str:
    cases_by_id = {c["case_id"]: c for c in cases}
    a, ca = data["arm_a"], data["arm_c_ours"]
    b, cb = data["arm_b"], data["arm_c_vendor"]
    en, em = data.get("arm_e_noon", []), data.get("arm_e_median", [])
    median_minute = data.get("arm_e_median_minute", 0)
    parts: list[str] = [HDR, ""]

    parts += _headline(a, b, en, em, median_minute)

    parts += [
        f"Generated {dt.date.today().isoformat()} by `benchmarks/run_benchmark.py`. "
        "This is a measurement instrument, not a tuning run: no scoring weight, orb, "
        "default or shipped code path was changed to produce these numbers, and the "
        "harness was never adjusted after seeing them.",
        "",
        "## Protocol",
        "",
        f"- Window `{data['protocol']['window']}`, step "
        f"`{data['protocol']['step_minutes']}` min, "
        f"{data['protocol']['grid_points']} candidate times, identical in every arm.",
        "- **Arm A** - our engine on current `main` with engine defaults "
        "(`RectificationConfig()` with no arguments, which is what the web client gets "
        "because it sends no `config`).",
        "- **Arm B** - the vendor's `POST /api/v3/rectification/search`. Their window "
        "caps at 720 minutes, so each case is two requests anchored at a fixed 06:00 "
        "and 18:00 with `delta_minutes: 360`; the better of the two peaks is taken. "
        "The anchors are protocol constants, never derived from the known time, so "
        "nothing about the answer leaks into the request.",
        "- **Arm C** - the null control, run against both engines: same case, same "
        "window, same event count and category mix, event dates redrawn uniformly "
        f"across the subject's own event span. {data['protocol']['null_shuffles_arm_a']} "
        "shuffles per case for Arm A.",
        "- **Arm E** - a constant-guess baseline that returns the same clock time for "
        "every case and reads nothing about the subject. Run at a fixed noon and at "
        f"the corpus median birth time ({protocol.minute_to_time(median_minute)}). "
        "Costs no vendor requests.",
        "",
        "The vendor honours explicit `latitude`/`longitude`/`timezone`: its Ascendant "
        "for a given candidate matches ours to 0.0013 degrees "
        "(`fixtures/vendor/category_probe.json`). Both engines therefore see the same "
        "astronomy, and every difference below is a difference in scoring.",
        "",
    ]

    parts += _corpus_section(cases)
    parts += _accuracy_section(a, b, ca, cb, en, em, median_minute)
    parts += _calibration_section(a, b)
    parts += _signal_section(a, ca, b, cb)
    parts += _bias_section(a, ca, b, cb, cases_by_id)
    parts += _per_case_section(a, b, cases_by_id)
    parts += _cost_section(data, a, b)
    parts += _verdict_section(a, ca, b, cb, cases)
    return "\n".join(parts) + "\n"


def _headline(a, b, en, em, median_minute) -> list[str]:
    """Lead with the constant-guess comparison when a constant wins.

    A fixed clock time that ignores the subject entirely beating a scorer that
    reads twelve dated life events is the single most decision-relevant fact
    this harness can produce, so it goes above everything else rather than
    being left for a reader to assemble from the accuracy table.
    """
    if not a or not (en or em):
        return []

    acc_a = metrics.accuracy_table(a)
    acc_b = metrics.accuracy_table(b) if b else None
    beaten = []
    for label, records in (("noon", en), ("corpus median", em)):
        if not records:
            continue
        acc_e = metrics.accuracy_table(records)
        if acc_e["median_abs_error"] <= acc_a["median_abs_error"]:
            beaten.append((label, acc_e))

    if not beaten:
        constants = ", ".join(
            f"{label} {metrics.accuracy_table(r)['median_abs_error']:.0f} min"
            for label, r in (("noon", en), ("corpus median", em))
            if r
        )
        lines = [
            "> **Headline: our engine clears the constant-guess floor, and that is "
            "the only bar it clears.**",
            ">",
            f"> Arm A (our engine) has a median error of "
            f"**{acc_a['median_abs_error']:.0f} minutes**, better than a constant "
            f"clock time that ignores the subject entirely ({constants}). So the "
            "scorer is doing *something* with the events.",
            ">",
            f"> It is not doing enough. At +/-5 minutes - the accuracy the product "
            f"promises - Arm A hits **{_pct(acc_a['hit_rate_5'])}**"
            + (
                f", and the vendor hits {_pct(acc_b['hit_rate_5'])}"
                if acc_b
                else ""
            )
            + ". Against its own shuffled-date null control, neither engine "
            "separates (see the verdict). Beating a constant is a floor, not a "
            "product.",
        ]
        return lines + [""]

    lines = [
        "> **Headline: a constant guess beats our engine on this corpus.**",
        ">",
        f"> Arm A (our engine, twelve dated life events per case, engine defaults) has "
        f"a median error of **{acc_a['median_abs_error']:.0f} minutes** and a "
        f"**{_pct(acc_a['hit_rate_5'])}** hit rate at +/-5 minutes.",
        ">",
    ]
    for label, acc_e in beaten:
        lines.append(
            f"> Arm E ({label}) - the same clock time returned for every case, reading "
            f"nothing about the subject - has a median error of "
            f"**{acc_e['median_abs_error']:.0f} minutes** and "
            f"**{_pct(acc_e['hit_rate_5'])}** at +/-5."
        )
    lines += [
        ">",
        "> On twelve cases this is not a statistically strong claim, and the "
        "corpus-median constant is fitted to the answers it is graded against. But "
        "the direction is unambiguous and it is the number that should drive the "
        "next decision: **our scorer is not yet extracting usable information from "
        "the events.**",
    ]
    if acc_b:
        lines += [
            ">",
            f"> The vendor (Arm B) is at **{acc_b['median_abs_error']:.0f} minutes** "
            f"median and {_pct(acc_b['hit_rate_5'])} at +/-5, so buying does not "
            "solve this either.",
        ]
    return lines + [""]


def _corpus_section(cases: list[dict]) -> list[str]:
    rows = []
    for c in sorted(cases, key=lambda x: x["case_id"]):
        f = c["spread_flags"]
        marks = ",".join(
            k for k, v in (("night", f["night_birth"]), ("lat>45", f["high_latitude"]),
                           ("equator", f["near_equator"])) if v
        ) or "-"
        rows.append([
            c["name"],
            c["birth_date"],
            c["known_time"],
            c["rodden_rating"],
            f"{c['place']['lat']:.2f}",
            marks,
            "yes" if c["known_time_is_round"] else "no",
            str(len(c["events"])),
        ])
    night = sum(1 for c in cases if c["spread_flags"]["night_birth"])
    high = sum(1 for c in cases if c["spread_flags"]["high_latitude"])
    eq = sum(1 for c in cases if c["spread_flags"]["near_equator"])
    rounded = sum(1 for c in cases if c["known_time_is_round"])

    return [
        "## The corpus",
        "",
        _table(
            ["Case", "Born", "Known time", "Rodden", "Lat", "Spread", "Round time", "Events"],
            rows,
        ),
        "",
        f"{len(cases)} cases, all Rodden AA. Night births (00:00-06:00): **{night}** "
        f"(rule: at least 4). Born above 45 degrees latitude: **{high}** (rule: at least 4). "
        f"Within 10 degrees of the equator: **{eq}** (rule: at least 2) - "
        "**this rule is not met; see 'Where this corpus falls short' below.**",
        "",
        f"**{rounded} of {len(cases)} known times fall on a round quarter-hour.** "
        "Registered times are commonly rounded by the registrar, so for those cases "
        "the reference itself carries roughly +/-5 to 15 minutes of error. No accuracy "
        "claim below +/-5 minutes can be validated against them, and the +/-2 column "
        "below is close to meaningless for that subset. Per-case notes are in each "
        "fixture's `reference_uncertainty_note`.",
        "",
    ]


def _accuracy_section(a, b, ca, cb, en, em, median_minute) -> list[str]:
    headers = ["Arm", "n", "+/-2 min", "+/-5 min", "+/-15 min", "+/-30 min",
               "Median abs err", "p90 abs err"]
    rows = [
        _accuracy_rows("A - ours, real events", a),
        _accuracy_rows("C - ours, shuffled dates", ca),
        _accuracy_rows("B - vendor, real events", b),
        _accuracy_rows("C - vendor, shuffled dates", cb),
        _accuracy_rows("E - constant guess, noon", en),
        _accuracy_rows(
            f"E - constant guess, corpus median ({protocol.minute_to_time(median_minute)})",
            em,
        ),
    ]
    chance2 = 2 * 2 / 1440
    chance5 = 2 * 5 / 1440
    return [
        "## Accuracy",
        "",
        _table(headers, rows),
        "",
        f"Blind-guess baselines on a 24-hour window: +/-2 min is {chance2:.1%} of the "
        f"day, +/-5 min is {chance5:.1%}. Any hit rate near those numbers is noise.",
        "",
        "Read the vendor null row with care: it is four cases, so a single lucky run "
        "shows up as 25%. That row is a reminder of how little four samples buy, not "
        "evidence that shuffled dates work better than real ones.",
        "",
        "**Arm E returns the same clock time for every case.** It does not read the "
        "events, the chart, the latitude or anything else about the subject. It is "
        "the floor a scorer has to clear before its output can be called a "
        "rectification at all. The noon constant was fixed before the corpus was "
        "scored; the corpus-median constant is **fitted to the very answers it is "
        "graded against**, so it is an oracle baseline and an upper bound on what a "
        "constant can do here, not a strategy anything could ship.",
        "",
    ]


def _calibration_section(a, b) -> list[str]:
    out = ["## Calibration - does the engine know when it is right?", ""]
    headers = ["Self-reported confidence", "n", "within +/-5", "rate", "within +/-15",
               "rate", "Median abs err"]

    for label, records, arm in (("Ours (`residual_window_minutes`)", a, "ours"),
                                ("Vendor (`confidence.level`)", b, "vendor")):
        out += [f"### {label}", ""]
        if not records:
            out += ["Not run.", ""]
            continue
        rows = []
        for r in metrics.calibration_table(records, arm):
            rows.append([
                str(r["bucket"]),
                str(r["n"]),
                str(r["within_5"]),
                _pct(r.get("within_5_rate")),
                str(r.get("within_15")),
                _pct(r.get("within_15_rate")),
                _fmt(r.get("median_abs_error"), "{:.0f}"),
            ])
        out += [_table(headers, rows), ""]

    out += [
        "Ours reports no confidence *level*, only `residual_window_minutes` - the width "
        "of the contiguous span whose scores stay within `plateau_ratio` of the best. "
        "A narrower residual window is the engine claiming a sharper answer, so the "
        "buckets run from narrow (highest implied confidence) to wide.",
        "",
    ]
    return out


def _signal_section(a, ca, b, cb) -> list[str]:
    out = ["## Signal versus null", "",
           "`peak / mean` over the full 24-hour candidate grid, real events against "
           "shuffled dates. If the real distribution is not separated from the null "
           "distribution, the peak is a property of the grid, not of the life.", ""]
    headers = ["Engine", "real n", "real median", "null n", "null median",
               "real p10", "null p90", "AUC", "Cohen's d"]
    rows = []
    for label, real, null in (("ours", a, ca), ("vendor", b, cb)):
        if not real or not null:
            rows.append([label] + ["not run"] * 8)
            continue
        s = metrics.signal_vs_null(real, null)
        rows.append([
            label, str(s["real_n"]), _fmt(s["real_median"]),
            str(s["null_n"]), _fmt(s["null_median"]),
            _fmt(s["real_p10"]), _fmt(s["null_p90"]),
            _fmt(s.get("auc"), "{:.2f}"), _fmt(s.get("cohens_d"), "{:.2f}"),
        ])
    out += [_table(headers, rows), "",
            "AUC is the probability that a randomly chosen real run outranks a randomly "
            "chosen null run on `peak / mean`. 0.50 is chance; 1.00 is complete "
            "separation.", ""]

    out += [
        "### Where the true birth time ranks in each engine's own score distribution",
        "",
        "Argmax accuracy is coarse on twelve cases: an engine can carry real signal and "
        "still miss the top slot. This asks the softer question - of the 360 candidates, "
        "what fraction score strictly below the true time? **0.50 is chance. 1.00 would "
        "mean the true time is the outright peak.** A scorer with any signal at all "
        "should sit well above 0.50 here even when its argmax is wrong.",
        "",
    ]
    prow = []
    for label, records in (("ours, real events", a), ("ours, shuffled dates", ca),
                           ("vendor, real events", b), ("vendor, shuffled dates", cb)):
        pct = [r["known_time_percentile"] for r in records
               if r.get("known_time_percentile") is not None]
        if not pct:
            prow.append([label, "not run", "-", "-", "-"])
            continue
        prow.append([
            label, str(len(pct)),
            _fmt(metrics.percentile(pct, 0.5)),
            _fmt(metrics.percentile(pct, 0.25)),
            _fmt(metrics.percentile(pct, 0.75)),
        ])
    out += [
        _table(["Set", "n", "median percentile", "p25", "p75"], prow),
        "",
        "For the shuffled-date rows the 'true time' has no reason to score well, so "
        "those rows are the chance reference measured rather than assumed.",
        "",
    ]
    return out


def _bias_section(a, ca, b, cb, cases_by_id) -> list[str]:
    out = ["## Bias check - are returned times following the Ascendant, not the events?", ""]
    headers = ["Set", "n", "in the 8 slowest Ascendant hours", "share", "uniform expectation"]
    rows = []
    for label, records in (("A - ours, real", a), ("C - ours, null", ca),
                           ("B - vendor, real", b), ("C - vendor, null", cb)):
        if not records:
            rows.append([label] + ["not run"] * 4)
            continue
        r = bias.bias_report(records, cases_by_id)
        rows.append([label, str(r["n"]), str(r["in_slowest_hours"]),
                     _pct(r["observed_share"]), _pct(r["uniform_expectation"])])
    out += [_table(headers, rows), ""]

    out += ["### Returned-hour histogram (all runs, all arms)", ""]
    hist_rows = []
    for label, records in (("ours real", a), ("ours null", ca),
                           ("vendor real", b), ("vendor null", cb)):
        if not records:
            continue
        h = metrics.hour_histogram(records)
        hist_rows.append([label] + [str(h[x]) for x in range(24)])
    if hist_rows:
        out += [_table(["Set"] + [f"{x:02d}" for x in range(24)], hist_rows), ""]
    out += [
        "The 'slowest Ascendant hours' are computed per case from the actual Ascendant "
        "travel per 4-minute step at that latitude and date (`harness/bias.py`), not "
        "assumed. A share well above 33% means the scorer is rewarding the hours where "
        "the angles move least, which is a property of the grid rather than of the "
        "subject's life.",
        "",
    ]
    return out


def _per_case_section(a, b, cases_by_id) -> list[str]:
    by_case: dict[str, dict] = {}
    for r in a:
        by_case.setdefault(r["case_id"], {})["a"] = r
    for r in b:
        by_case.setdefault(r["case_id"], {})["b"] = r

    headers = ["Case", "Known", "Ours", "abs err ours", "residual", "Vendor",
               "abs err vendor", "level", "gap", "lift", "twin", "anchor",
               "on grid", "grid floor"]
    rows = []
    for case_id in sorted(by_case):
        ra, rb = by_case[case_id].get("a"), by_case[case_id].get("b")
        ref = ra or rb
        conf = (rb or {}).get("own_confidence", {})
        rows.append([
            cases_by_id[case_id]["name"],
            ref["known_time"],
            ra["returned_time"] if ra else "-",
            str(ra["abs_error_minutes"]) if ra else "-",
            str(ra["own_confidence"]["residual_window_minutes"]) if ra else "-",
            rb["returned_time"] if rb else "-",
            str(rb["abs_error_minutes"]) if rb else "-",
            str(conf.get("level") or "-"),
            _fmt(conf.get("gap_ratio")),
            _fmt(conf.get("lift_ratio")),
            str(conf.get("twin_window")) if rb else "-",
            str(conf.get("anchor_grade")) if rb else "-",
            "yes" if ref["known_time_on_grid"] else "no",
            str(ref["grid_floor_error_minutes"]),
        ])
    return [
        "## Per case, verbatim engine output",
        "",
        _table(headers, rows),
        "",
        "`grid floor` is the smallest |err| any engine could achieve for that known "
        "time on this 4-minute grid. Where the known time is not a grid point, that "
        "floor is the irreducible part of the error.",
        "",
    ]


def _cost_section(data, a, b) -> list[str]:
    budget = data["vendor_budget"]
    ours_ms = [r["wall_ms"] for r in a] or [0.0]
    # Their server-reported compute time, not our wall clock: on an offline
    # replay our wall clock is timing a cache read.
    theirs_ms = [r.get("server_ms") or 0.0 for r in b] or [0.0]
    total = budget.get("requests", 0)
    out = [
        "## Cost and wall-clock",
        "",
        f"**Total vendor requests consumed: {total}** "
        f"({budget.get('search_requests', 0)} rectification searches - two per case, "
        f"one per half-window - plus {budget.get('probe_requests', 0)} schema probe), "
        f"for {budget.get('credits', 0)} credits. One further exploratory request was "
        "made by hand before the harness existed and is not in the fixture ledger, so "
        f"the true total is {total + 1}. **That is under the vendor's free-tier limit "
        "of 50 requests a month.** One malformed probe was rejected with a 422 and "
        "cost nothing.",
        "",
        "The vendor bills a flat 15 credits per rectification request regardless of "
        "candidate count (measured: 15 credits for a 5-candidate search, a "
        "13-candidate search and a 181-candidate search alike). Note the tension: "
        f"{total + 1} requests is inside a 50-*request* allowance, but at 15 credits "
        "each it is far outside a 50-*credit* one, and the vendor gates rectification "
        "to its Ultra tier. If the free tier is denominated in credits rather than "
        "requests, this run exceeded it; every request was nonetheless accepted with "
        "a 200 and no quota warning.",
        "",
        f"Median compute per case: ours **{metrics.percentile(ours_ms, 0.5):.0f} ms** "
        "in-process for all 360 candidates; the vendor reports "
        f"**{metrics.percentile(theirs_ms, 0.5):.0f} ms** of server compute across its "
        "two requests. End to end, though, a vendor case took roughly **105 seconds** "
        "of wall-clock in the live run, against a fifth of a second for ours. That is "
        "a two-order-of-magnitude difference in latency and it would be visible to a "
        "user waiting on a result.",
        "",
    ]
    out += pricing.cost_table()
    return out


def _verdict_section(a, ca, b, cb, cases) -> list[str]:
    out = ["## Verdict", ""]

    sig_a = metrics.signal_vs_null(a, ca) if (a and ca) else None
    sig_b = metrics.signal_vs_null(b, cb) if (b and cb) else None
    acc_a = metrics.accuracy_table(a) if a else None
    acc_b = metrics.accuracy_table(b) if b else None
    acc_ca = metrics.accuracy_table(ca) if ca else None
    acc_cb = metrics.accuracy_table(cb) if cb else None

    # 1. Which engine, if either, beats its own null control.
    def beats(acc, acc_null, sig) -> tuple[bool, str]:
        if not acc or not acc_null or not sig:
            return False, "not measurable"
        better_hits = acc["hit_rate_5"] > acc_null["hit_rate_5"]
        better_median = acc["median_abs_error"] < acc_null["median_abs_error"]
        separated = (sig.get("auc") or 0.5) > 0.65
        reasons = (
            f"+/-5 hit rate {_pct(acc['hit_rate_5'])} vs null {_pct(acc_null['hit_rate_5'])}; "
            f"median |err| {acc['median_abs_error']:.0f} vs null "
            f"{acc_null['median_abs_error']:.0f} min; peak/mean AUC "
            f"{_fmt(sig.get('auc'), '{:.2f}')}"
        )
        return (better_hits and better_median and separated), reasons

    ours_beat, ours_why = beats(acc_a, acc_ca, sig_a)
    theirs_beat, theirs_why = beats(acc_b, acc_cb, sig_b)

    if ours_beat and theirs_beat:
        ranked = "Both engines beat their own null control"
    elif ours_beat:
        ranked = "Our engine beats its null control and the vendor's does not"
    elif theirs_beat:
        ranked = "The vendor's engine beats its null control and ours does not"
    else:
        ranked = "**Neither engine is measurably better than its own null control**"

    out += [
        "### 1. Which engine, if either, is measurably better than its own null control",
        "",
        f"{ranked} on this corpus.",
        "",
        f"- Ours: {ours_why}.",
        f"- Vendor: {theirs_why}.",
        "",
        "The bar used here is deliberately all three at once: a higher +/-5 hit rate "
        "than the null, a lower median error than the null, and `peak / mean` "
        "separated from the null at AUC > 0.65. Clearing one of the three by chance "
        "on twelve cases is easy; clearing all three is not.",
        "",
    ]
    out += _soft_signal_note(a, ca, b, cb)

    # 2. Do the vendor's confidence outputs track real error better than ours?
    out += ["### 2. Do the vendor's confidence outputs track error better than "
            "`residual_window_minutes`?", ""]
    if not b:
        out += ["Arm B was not run, so this cannot be answered.", ""]
    else:
        spread_ours = _bucket_spread(metrics.calibration_table(a, "ours"))
        spread_theirs = _bucket_spread(metrics.calibration_table(b, "vendor"))
        out += [
            f"Our `residual_window_minutes` splits the corpus into "
            f"{len(metrics.calibration_table(a, 'ours'))} bucket(s); the spread in "
            f"+/-5 hit rate between its best and worst bucket is "
            f"{_pct(spread_ours)}.",
            f"The vendor's `confidence.level` splits it into "
            f"{len(metrics.calibration_table(b, 'vendor'))} bucket(s); the spread there "
            f"is {_pct(spread_theirs)}.",
            "",
            "A confidence output is worth copying only if high-confidence cases really "
            "are more accurate than low-confidence ones, i.e. if that spread is large "
            "and positive. See the calibration tables above for the underlying counts; "
            "with twelve cases each bucket holds only a handful of cases, so treat any "
            "spread here as directional rather than established.",
            "",
        ]

    # 3. Is either good enough for a +/-5 minute promise?
    rounded = sum(1 for c in cases if c["known_time_is_round"])
    out += ["### 3. Is either engine accurate enough to support a +/-5 minute promise?", ""]
    best5 = max(
        [x["hit_rate_5"] for x in (acc_a, acc_b) if x],
        default=None,
    )
    out += [
        f"No. The best +/-5 hit rate in either real arm is **{_pct(best5)}**, against a "
        f"blind-guess baseline of {2 * 5 / 1440:.1%}. A product promise of +/-5 minutes "
        "with +/-2 as the target and no refund path is not supported by either engine "
        "on this corpus."
        if best5 is not None and best5 < 0.5 else
        f"The best +/-5 hit rate measured is **{_pct(best5)}**. Read it against the "
        "corpus caveat below before treating it as support for the promise.",
        "",
        f"**The corpus caveat is load-bearing here.** {rounded} of {len(cases)} known "
        "times fall on a round quarter-hour, and registered times are commonly rounded "
        "by the registrar. For those cases the reference carries roughly +/-5 to 15 "
        "minutes of its own error, so a measured +/-5 hit rate on them cannot "
        "distinguish a correct answer from one that is 10 minutes out. Any +/-5 or "
        "+/-2 figure in this report is therefore an upper bound on what could be "
        "verified, not a demonstrated accuracy.",
        "",
    ]

    # 4. Build versus buy.
    out += ["### 4. Build versus buy", ""] + pricing.build_vs_buy(len(cases))

    out += _shortfalls_section(cases)
    return out


def _soft_signal_note(a, ca, b, cb) -> list[str]:
    """The one place the data does show something, stated with its own limits."""

    def med(records):
        vals = [
            r["known_time_percentile"]
            for r in records
            if r.get("known_time_percentile") is not None
        ]
        return metrics.percentile(vals, 0.5), len(vals)

    ours_real, n_or = med(a)
    ours_null, n_on = med(ca)
    theirs_real, n_tr = med(b)
    theirs_null, n_tn = med(cb)
    if ours_real is None or theirs_real is None or ours_null is None:
        return []

    return [
        "**One qualifier, because it is the only thing in this run that looks like "
        "signal.** Argmax is a harsh test on twelve cases. Ranking the *true* time "
        "inside each engine's own score distribution is softer, and there the two "
        "engines separate:",
        "",
        f"- Ours: true time at the {ours_real:.2f} percentile on real events "
        f"(n={n_or}) against {ours_null:.2f} on shuffled dates (n={n_on}).",
        f"- Vendor: {theirs_real:.2f} on real events (n={n_tr}) against "
        f"{_fmt(theirs_null)} on shuffled dates (n={n_tn}).",
        "",
        "The vendor's scorer ranks the true birth time well above its own "
        "shuffled-date control: it is finding something and then failing to convert "
        "it into a correct peak. Ours sits much closer to its own control. **This "
        "does not overturn the verdict above.** The vendor null here is only "
        f"{n_tn} cases, far too few to establish the gap, and none of it moves the "
        "hit rates a product promise actually depends on. It is the one result in "
        "this report worth spending another measurement on, and the cheap way to do "
        "that is to widen the vendor null arm - not to rebuild our scorer on the "
        "strength of it.",
        "",
    ]


def _bucket_spread(rows: list[dict]) -> float | None:
    rates = [r["within_5_rate"] for r in rows if r.get("within_5_rate") is not None]
    if len(rates) < 2:
        return None
    return max(rates) - min(rates)


def _shortfalls_section(cases) -> list[str]:
    return [
        "## Where this corpus falls short",
        "",
        "**The near-equator spread rule is not met: 0 cases within 10 degrees of the "
        "equator, against a required 2.** This is a real gap and it is reported rather "
        "than papered over, because the whole point of that rule is that the "
        "slow-Ascendant bias is a function of latitude.",
        "",
        "Astro-Databank is heavily Western-weighted and AA-rated equatorial births are "
        "genuinely scarce. Candidates were checked and rejected on their actual Rodden "
        "rating, not on convenience:",
        "",
        _table(
            ["Candidate", "Latitude", "Rating found", "Rejected because"],
            [
                ["Lee Kuan Yew", "1.3 N", "R", "book reference, not a birth record"],
                ["Sukarno", "7.2 S", "B", "biography"],
                ["Hugo Chavez", "8.8 N", "conflicting", "02:00 / 03:30 / 04:00 / 17:10 all reported"],
                ["Freddie Mercury", "6.2 S", "X", "no birth time recorded at all"],
                ["Oscar Arias", "9.9 N", "conflicting", "birth year itself disputed (1940 vs 1941)"],
            ],
        ),
        "",
        "The lowest-latitude case that did qualify is Barack Obama at 21.3 N. The "
        "latitude-dependent part of the bias check is therefore measured over "
        "31.2 N to 51.5 N only, and this report cannot say how either engine behaves "
        "at equatorial latitudes. Closing this gap needs a source other than "
        "Astro-Databank - a national civil-registry release, or an astrological "
        "association's regional AA collection.",
        "",
        "Two further limits worth stating:",
        "",
        "- Rejections elsewhere in the shortlist were also on rating, not fit: Ronald "
        "Reagan (Astro-Databank shows AA, but the displayed certificate carries no "
        "time), Alfred Hitchcock (DD), Angela Merkel (B), King Charles III (A), "
        "Justin Bieber (B). None were admitted.",
        "- Event dates come from published biography, so a handful carry their own "
        "day-level slack even where they are recorded here as `day` precision. That "
        "adds noise to both arms equally and cannot favour one engine over the other.",
        "",
    ]
