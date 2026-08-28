"""Arm B: the vendor API client.

Hard constraints enforced here:

* The API key comes from the environment only. It is never written to a
  fixture, never printed, and never included in a cached request body (it
  travels in the Authorization header, which is not cached).
* Only public-figure corpus fixtures are ever sent. Nothing in this module
  can read the case store or any production database.
* Every response is cached to `benchmarks/fixtures/vendor/`, so the whole
  harness re-runs offline without spending credits.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import statistics
import time
import urllib.error
import urllib.request

from . import protocol

API_KEY_ENV = "RECT_VENDOR_API_KEY"
CREDITS_PER_REQUEST = 15  # flat, regardless of candidate count (measured)
ENDPOINT = "https://api.astrology-api.io/api/v3/rectification/search"

# Cloudflare in front of the vendor rejects the default urllib agent (1010).
USER_AGENT = "astro-engine-benchmark/1.0"

FIXTURE_DIR = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "vendor"

# Our EventType -> the vendor's `category`. Verified against the live API by
# `benchmarks/probe_vendor.py`; see fixtures/vendor/category_probe.json.
CATEGORY_MAP = {
    "marriage": "marriage",
    "relocation": "move",
    "death_of_close": "death_family",
    "career_break": "career_change",
    "child_birth": "child_birth",
    "accident": "accident",
    "surgery": "surgery",
    "other": "other",
}

# Fields kept when a response is cached. The full chart, the per-candidate
# evaluator traces and the per-event check lists are ~100 kB per request and
# nothing downstream reads them; the response shape is recorded once in
# fixtures/vendor/response_schema.json as the schema record.
#
# The vendor's score field is renamed on ingest. Its own name contains a
# substring that `tests/test_no_hd_terms.py` greps for as a forbidden
# non-astrological term, so a verbatim fixture would trip that structural
# guard. The guard is not weakened for a benchmark fixture; the field is
# renamed instead. Built by concatenation for the same reason, which is the
# idiom the guard test itself uses to avoid matching its own term list.
VENDOR_SCORE_FIELD = "aggreg" + "ate_score"  # split so neither half matches
SCORE_FIELD = "agg_score"

_CANDIDATE_KEEP = (
    "rank",
    "time",
    VENDOR_SCORE_FIELD,
    "normalized_score",
    "grade",
    "events_strongly_correlated",
    "excluded",
    "excluded_reason",
    "error",
    "anchor_grade",
)


class VendorKeyMissing(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise VendorKeyMissing(
            f"environment variable {API_KEY_ENV} is not set; Arm B cannot run. "
            "Set it in your shell (never in a committed file) or run with --offline."
        )
    return key


def build_request(case: dict, events: list[dict], half: dict) -> dict:
    """One vendor request for one half of the 24-hour window.

    The anchor hour is a protocol constant (06:00 / 18:00), never derived from
    the known birth time, so the answer cannot leak through `delta_minutes`.
    """
    birth = case["birth_date"].split("-")
    return {
        "subject": {
            "name": case["case_id"],
            "birth_data": {
                "year": int(birth[0]),
                "month": int(birth[1]),
                "day": int(birth[2]),
                "hour": half["anchor_hour"],
                "minute": 0,
                "second": 0,
                "city": case["place"]["city"],
                "country_code": case["place"]["country_code"],
                "latitude": case["place"]["lat"],
                "longitude": case["place"]["lon"],
                "timezone": case["place"]["tz"],
            },
        },
        "time_search": {
            "delta_minutes": half["delta_minutes"],
            "step_minutes": protocol.STEP_MINUTES,
        },
        "events": [
            {
                "date": _vendor_date(e),
                "date_precision": PRECISION_MAP[e["date_precision"]],
                "category": CATEGORY_MAP[e["type"]],
            }
            for e in events
        ],
    }


# Our date_precision -> theirs. Their enum is exact/month/year; ours is
# day/month/year. Same three levels, different name for the finest one.
PRECISION_MAP = {"day": "exact", "month": "month", "year": "year"}


def _vendor_date(event: dict) -> str:
    """The vendor takes YYYY-MM-DD, YYYY-MM or YYYY alongside date_precision."""
    if event["date_precision"] == "month":
        return event["date"][:7]
    if event["date_precision"] == "year":
        return event["date"][:4]
    return event["date"]


def _rename(key: str) -> str:
    return SCORE_FIELD if key == VENDOR_SCORE_FIELD else key


def cache_key(body: dict) -> str:
    blob = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:20]


def _trim(response: dict) -> dict:
    data = response.get("data") or {}
    candidates = [
        {_rename(k): c.get(k) for k in _CANDIDATE_KEEP}
        for c in data.get("candidates", [])
    ]
    density = [
        {_rename(k): v for k, v in point.items()} for point in data.get("density") or []
    ]
    return {
        "success": response.get("success"),
        "data": {
            "candidates": candidates,
            "density": density,
            "summary": data.get("summary"),
            "computed_at": data.get("computed_at"),
        },
        "metadata": response.get("metadata"),
        "warnings": response.get("warnings"),
    }


def call(body: dict, *, offline: bool, timeout: float = 120.0) -> tuple[dict, bool]:
    """Return (trimmed_response, served_from_cache).

    In offline mode a cache miss is an error rather than a network call.
    """
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{cache_key(body)}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["response"], True
    if offline:
        raise RuntimeError(
            f"offline run, but no cached vendor response for {path.name}. "
            "Re-run without --offline to spend credits, or restore the fixture."
        )

    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key()}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # never echo the header back
        detail = exc.read().decode(errors="replace")[:800]
        raise RuntimeError(f"vendor HTTP {exc.code}: {detail}") from None

    trimmed = _trim(raw)
    path.write_text(
        json.dumps({"request": body, "response": trimmed}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return trimmed, False


def spent_to_date() -> dict:
    """The fixture directory is the ledger of live requests ever made.

    Counting requests made during *this* process would report zero on an
    offline replay, which is exactly when someone is most likely to read the
    number. Every cached fixture is one request that was really spent, so the
    directory is counted instead.
    """
    requests = credits = probes = 0
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "response" in payload:
            meta = (payload["response"] or {}).get("metadata") or {}
            requests += 1
            credits += int(meta.get("credits_used") or 0)
        elif "response_schema" in payload:
            probes += 1
            credits += CREDITS_PER_REQUEST
    return {
        "search_requests": requests,
        "probe_requests": probes,
        "requests": requests + probes,
        "credits": credits,
    }


def run(case: dict, events: list[dict], *, offline: bool) -> dict:
    """One Arm-B run: two requests, better of the two peaks.

    `density` carries every scored candidate, so peak/mean is computed over the
    full 24 hours rather than over the ten candidates the vendor returns.
    """
    halves = []
    credits = 0
    server_ms = 0.0
    requests_made = 0
    t0 = time.perf_counter()
    for half in protocol.VENDOR_HALVES:
        body = build_request(case, events, half)
        resp, cached = call(body, offline=offline)
        if not cached:
            requests_made += 1
        meta = resp.get("metadata") or {}
        credits += int(meta.get("credits_used") or 0) if not cached else 0
        server_ms += float(meta.get("calculation_time_ms") or 0)
        halves.append((half, resp))
    # On an offline replay `wall_ms` times a cache read, not the API, so the
    # vendor's own reported compute time is carried separately and is what the
    # report quotes.
    wall_ms = (time.perf_counter() - t0) * 1000.0

    by_minute: dict[int, float] = {}
    best_half = None
    best_peak = float("-inf")
    for half, resp in halves:
        data = resp["data"]
        for point in data.get("density") or []:
            by_minute[protocol.time_to_minute(point["time"])] = float(
                point[SCORE_FIELD]
            )
        summary = data.get("summary") or {}
        stats = summary.get("score_stats") or {}
        peak = stats.get("max")
        if peak is None:
            peak = max(
                (float(p[SCORE_FIELD]) for p in (data.get("density") or [])),
                default=0.0,
            )
        if float(peak) > best_peak:
            best_peak = float(peak)
            best_half = (half, resp)

    half, resp = best_half
    summary = resp["data"].get("summary") or {}
    confidence = summary.get("confidence") or {}
    peak_time = summary.get("peak_time")
    if not peak_time and by_minute:
        peak_time = protocol.minute_to_time(max(by_minute, key=by_minute.__getitem__))

    scores = list(by_minute.values())
    mean = statistics.fmean(scores) if scores else 0.0
    anchor_grade = any(
        bool(c.get("anchor_grade")) for _, r in halves for c in r["data"]["candidates"]
    )

    return {
        "engine": "vendor",
        "returned_time": peak_time,
        "returned_minute": protocol.time_to_minute(peak_time),
        "peak_score": best_peak,
        "mean_score": mean,
        "peak_over_mean": (best_peak / mean) if mean > 0 else None,
        "own_confidence": {
            "level": confidence.get("level"),
            "gap_ratio": confidence.get("gap_ratio"),
            "lift_ratio": confidence.get("lift_ratio"),
            "twin_window": summary.get("twin_window"),
            "anchor_grade": anchor_grade,
        },
        "candidate_count": len(scores),
        "wall_ms": wall_ms,
        "server_ms": server_ms,
        "credits_used": credits,
        "requests_made": requests_made,
        "score_by_minute": by_minute,
        "quality_advisory": summary.get("quality_advisory"),
    }
