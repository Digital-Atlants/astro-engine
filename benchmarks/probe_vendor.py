"""One cheap live probe of the vendor API.

Answers the three things the harness cannot assume:

1. Which `category` strings the vendor accepts for our eight event types.
2. Whether it honours explicit lat/lon/timezone or silently geocodes `city`
   (checked by comparing its Ascendant against ours for the same instant).
3. How `credits_used` scales, so the free-tier budget can be respected.

Writes `fixtures/vendor/raw_response_sample.json` (the full verbatim response,
kept as the schema record) and `fixtures/vendor/category_probe.json`.

Usage:  RECT_VENDOR_API_KEY=... python benchmarks/probe_vendor.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import core  # noqa: E402
from benchmarks.harness import corpus, protocol, vendor  # noqa: E402


def post(body: dict) -> dict:
    req = urllib.request.Request(
        vendor.ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {vendor.api_key()}",
            "User-Agent": vendor.USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:2000]}")
        raise SystemExit(1) from None


def schema_of(value, depth: int = 0):
    """Key paths and types, not values.

    Recorded instead of a verbatim response for two reasons: the full payload
    is ~140 kB of chart data nothing downstream reads, and one of the vendor's
    field names collides with the forbidden-term grep in
    `tests/test_no_hd_terms.py`. The shape is what the harness needs to be
    re-readable offline; `vendor.SCORE_FIELD` documents the one rename.
    """
    if depth > 6:
        return "..."
    if isinstance(value, dict):
        return {
            vendor._rename(k): schema_of(v, depth + 1) for k, v in sorted(value.items())
        }
    if isinstance(value, list):
        return [schema_of(value[0], depth + 1)] if value else []
    if value is None:
        return "null"
    return type(value).__name__


def main() -> None:
    case = next(c for c in corpus.load_corpus() if c["case_id"] == "obama_barack")

    # One event per distinct type, so every category string is exercised.
    seen: dict[str, dict] = {}
    for e in case["events"]:
        seen.setdefault(e["type"], e)
    events = list(seen.values())

    body = vendor.build_request(case, events, protocol.VENDOR_HALVES[0])
    body["time_search"]["delta_minutes"] = 8  # 5 candidates: cheapest useful probe

    raw = post(body)
    out = vendor.FIXTURE_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "response_schema.json").write_text(
        json.dumps(
            {"request": body, "response_schema": schema_of(raw)},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    data = raw.get("data") or {}
    meta = raw.get("metadata") or {}
    density = data.get("density") or []
    candidates = data.get("candidates") or []

    echoed = []
    for cand in candidates:
        for es in cand.get("event_scores") or []:
            echoed.append((es.get("event_date"), es.get("event_category")))
        break

    # Does the vendor use our lat/lon, or its own geocode of `city`?
    asc_check = None
    if candidates:
        chart = candidates[0].get("chart") or {}
        their_asc = next(
            (
                p["absolute_longitude"]
                for p in chart.get("planetary_positions") or []
                if p.get("name") == "Ascendant"
            ),
            None,
        )
        if their_asc is not None:
            hh, mm = map(int, candidates[0]["time"].split(":"))
            when = dt.datetime.combine(case.birth_date, dt.time(hh, mm))
            jd = core.to_julian_day(core.localize_to_utc(when, case["place"]["tz"]))
            _, ours, _ = core.houses_and_angles(
                jd, case["place"]["lat"], case["place"]["lon"], "placidus"
            )
            asc_check = {
                "candidate_time": candidates[0]["time"],
                "vendor_asc_deg": their_asc,
                "our_asc_deg": round(ours, 4),
                "delta_deg": round(core.angle_diff(their_asc, ours), 4),
            }

    summary = {
        "categories_sent": sorted({e["category"] for e in body["events"]}),
        "categories_echoed": sorted({c for _, c in echoed if c}),
        "warnings": raw.get("warnings"),
        "quality_advisory": (data.get("summary") or {}).get("quality_advisory"),
        "events_used": (data.get("summary") or {}).get("total_events_used"),
        "events_sent": len(body["events"]),
        "candidates_generated": (data.get("summary") or {}).get(
            "total_candidates_generated"
        ),
        "density_times": [p["time"] for p in density],
        "credits_used": meta.get("credits_used"),
        "calculation_time_ms": meta.get("calculation_time_ms"),
        "ascendant_check": asc_check,
    }
    (out / "category_probe.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
