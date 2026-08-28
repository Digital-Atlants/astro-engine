"""Birth-time rectification scoring.

Performance contract: transit/progressed positions and the solar arc for an
event date do NOT depend on the candidate birth time (except the progressed
Moon, which is recomputed per candidate with a single cheap ephemeris call).
They are precomputed once per event; the per-candidate loop only computes
Asc/MC/cusps via swe.houses and tests the precomputed longitudes against them.

Two-stage design. Stage 1 narrows the birth time to a rising-sign block -
which is as far as anything a client can answer about their own chart can take
it, because under whole-sign houses every such answer is a function of the
Ascendant sign alone. Anything that is to resolve position *inside* a block
must therefore vary inside the block.

Four techniques ship. Quadrant cusps, directed angles, primary directions,
eclipse-on-angle and event-to-technique matching were implemented, measured
and reverted: none improved the held-out in-block error and two roughly
doubled it. `benchmarks/RESULTS_SUBSIGN.md` has the ablation;
`benchmarks/harness/candidate_engine.py` is the frozen experiment.

Note also that `profections` is a block-level prior, not a sub-sign
discriminator: it was measured as exactly constant inside the correct block in
29 of 29 training cases, because the profected house follows the Ascendant
sign. It is kept because it helps rank blocks, not minutes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random

from . import core
from .charts import YEAR_DAYS, profection_for
from .schemas import RectificationEvent, RectificationRequest

# Slow factors remain usable for month/year date precision.
SLOW_PLANETS = ("jupiter", "saturn", "uranus", "neptune", "pluto")
TRANSIT_PLANETS = ("mars", "jupiter", "saturn", "uranus", "neptune", "pluto")
ASPECT_ANGLES = (
    ("conj", 0.0),
    ("sq", 90.0),
    ("opp", 180.0),
)

# Traditional house topics used to score annual profections per event type.
EVENT_HOUSES = {
    "marriage": (7,),
    "relocation": (4, 9),
    "death_of_close": (8,),
    "career_break": (10,),
    "child_birth": (5,),
    "accident": (1, 6),
    "surgery": (1, 6),
    "other": (1,),
}

DIRECTED_BODIES = ("sun", "moon", "mars", "jupiter", "saturn")
PROG_BODIES = ("sun", "mercury", "venus", "mars")


def _event_jd(event: RectificationEvent) -> float:
    date = _effective_date(event)
    return core.to_julian_day(dt.datetime(date.year, date.month, date.day, 12, 0))


def _effective_date(event: RectificationEvent) -> dt.date:
    if event.date_precision == "month":
        return event.date.replace(day=15)
    if event.date_precision == "year":
        return event.date.replace(month=7, day=1)
    return event.date


class EventContext:
    """Candidate-independent positions for one event date."""

    __slots__ = (
        "event",
        "jd",
        "date",
        "transit_positions",
        "prog_positions",
        "solar_arc",
        "arc_directed",
        "orb_scale",
        "precision_weight",
        "allow_fast",
        "prog_years",
    )

    def __init__(
        self,
        event: RectificationEvent,
        birth_jd_noon: float,
        natal_positions: dict[str, tuple[float, float]],
        precision_weights: dict[str, float],
    ):
        self.event = event
        self.jd = _event_jd(event)
        self.date = _effective_date(event)
        self.precision_weight = precision_weights.get(event.date_precision, 1.0)
        self.allow_fast = event.date_precision == "day"
        self.orb_scale = 1.0 if event.date_precision == "day" else 2.0
        self.prog_years = (self.jd - birth_jd_noon) / YEAR_DAYS

        allowed_transits = (
            TRANSIT_PLANETS if event.date_precision == "day" else SLOW_PLANETS
        )
        if event.date_precision == "year":
            allowed_transits = ("saturn", "uranus", "neptune", "pluto")
        self.transit_positions = {
            name: core.planet_position(self.jd, pid)[0]
            for name, pid in core.PLANETS
            if name in allowed_transits
        }

        jd_prog = birth_jd_noon + self.prog_years
        self.prog_positions = {
            name: core.planet_position(jd_prog, pid)[0]
            for name, pid in core.PLANETS
            if name in PROG_BODIES
        }

        self.solar_arc = core.norm360(
            core.planet_position(jd_prog, 0)[0] - natal_positions["sun"][0]
        )
        self.arc_directed = {
            name: core.norm360(lon + self.solar_arc)
            for name, (lon, _) in natal_positions.items()
            if name in DIRECTED_BODIES
        }


def _hit_score(orb: float, max_orb: float) -> float:
    return max(0.0, 1.0 - orb / max_orb) if max_orb > 0 else 0.0


def _angle_hits(
    positions: dict[str, float],
    angles: dict[str, float],
    max_orb: float,
    technique: str,
    prefix: str,
    event_id: str,
    weight: float,
) -> list[dict]:
    hits = []
    for pname in sorted(positions):
        plon = positions[pname]
        for aname in ("asc", "mc"):
            sep = core.angle_diff(plon, angles[aname])
            for asp_code, asp_deg in ASPECT_ANGLES:
                orb = abs(sep - asp_deg)
                if orb <= max_orb:
                    hits.append(
                        {
                            "event_id": event_id,
                            "technique": technique,
                            "factor": f"{prefix}_{pname}_{asp_code}_{aname}",
                            "orb_deg": round(orb, core.ROUND_DEG),
                            "score": round(
                                _hit_score(orb, max_orb) * weight, core.ROUND_DEG
                            ),
                        }
                    )
                    break
    return hits


def _score_candidates(
    req: RectificationRequest,
    contexts: list[EventContext],
    minutes: list[int],
    collect_hits: bool,
) -> list[dict]:
    """The scoring loop. Shared by the real run and every permutation trial."""
    cfg = req.config
    bd = req.birth_date
    tw = cfg.technique_weights
    orbs = cfg.orbs
    candidates = []

    for m in minutes:
        hh, mm = divmod(m, 60)
        cand_utc = core.localize_to_utc(
            dt.datetime(bd.year, bd.month, bd.day, hh, mm), req.place.tz
        )
        cand_jd = core.to_julian_day(cand_utc)
        cusps, asc, mc = core.houses_and_angles(
            cand_jd, req.place.lat, req.place.lon, cfg.house_system
        )
        angles = {"asc": asc, "mc": mc}
        hits: list[dict] = []

        for ctx in contexts:
            ev = ctx.event
            base_w = ev.weight * ctx.precision_weight

            if "transits_to_angles" in cfg.techniques:
                hits += _angle_hits(
                    ctx.transit_positions,
                    angles,
                    orbs.get("transits_to_angles", 1.0) * ctx.orb_scale,
                    "transits_to_angles",
                    "tr",
                    ev.id,
                    base_w * tw.get("transits_to_angles", 1.0),
                )

            if "secondary_progressions" in cfg.techniques and ctx.allow_fast:
                # Progressed Moon is the only candidate-dependent factor:
                # one cheap Moshier call per (candidate, event).
                prog_jd_cand = cand_jd + ctx.prog_years
                prog_moon = core.planet_position(prog_jd_cand, core.PLANETS[1][1])[0]
                positions = dict(ctx.prog_positions)
                positions["moon"] = prog_moon
                hits += _angle_hits(
                    positions,
                    angles,
                    orbs.get("secondary_progressions", 1.0) * ctx.orb_scale,
                    "secondary_progressions",
                    "sp",
                    ev.id,
                    base_w * tw.get("secondary_progressions", 1.0),
                )

            if "solar_arc" in cfg.techniques:
                hits += _angle_hits(
                    ctx.arc_directed,
                    angles,
                    orbs.get("solar_arc", 1.0) * ctx.orb_scale,
                    "solar_arc",
                    "sa",
                    ev.id,
                    base_w * tw.get("solar_arc", 1.0),
                )

            if "profections" in cfg.techniques:
                prof = profection_for(bd, ctx.date, asc)
                if prof["activated_house"] in EVENT_HOUSES[ev.type]:
                    score = base_w * tw.get("profections", 1.0)
                    hits.append(
                        {
                            "event_id": ev.id,
                            "technique": "profections",
                            "factor": (
                                f"profection_house_{prof['activated_house']}"
                                f"_{prof['year_lord']}"
                            ),
                            "orb_deg": 0.0,
                            "score": round(score, core.ROUND_DEG),
                        }
                    )

        total = round(sum(h["score"] for h in hits), core.ROUND_DEG)
        entry = {
            "time": f"{hh:02d}:{mm:02d}",
            "total_score": total,
            "asc_sign": core.sign_of(asc),
        }
        if collect_hits:
            entry["hits"] = hits
        candidates.append(entry)

    return candidates


def _permutation_null(
    req: RectificationRequest,
    birth_jd_noon: float,
    natal_positions: dict,
    minutes: list[int],
) -> list[float]:
    """Peak scores from `permutation_trials` runs on shuffled event dates.

    This is the only figure in the response calibrated against anything: it
    asks whether the real peak is higher than the peak this same engine
    produces from the same events on dates drawn at random from the subject's
    own span. The seed is derived from the request, so the answer is
    deterministic for a given request while still being a genuine shuffle.
    """
    trials = req.config.permutation_trials
    if trials <= 0 or len(req.events) < 2:
        return []

    dates = [_effective_date(e) for e in req.events]
    lo, hi = min(dates), max(dates)
    span = max((hi - lo).days, 1)

    seed_src = f"{req.birth_date}|{req.place.lat}|{req.place.lon}|" + ",".join(
        f"{e.id}:{e.date}" for e in req.events
    )
    rng = random.Random(hashlib.sha256(seed_src.encode()).hexdigest())

    peaks = []
    for _ in range(trials):
        shuffled = [
            e.model_copy(update={"date": lo + dt.timedelta(days=rng.randint(0, span))})
            for e in req.events
        ]
        contexts = [
            EventContext(e, birth_jd_noon, natal_positions, req.config.precision_weights)
            for e in shuffled
        ]
        cands = _score_candidates(req, contexts, minutes, False)
        peaks.append(max(c["total_score"] for c in cands))
    return sorted(peaks)


def score_rectification(req: RectificationRequest) -> dict:
    cfg = req.config
    bd = req.birth_date

    # Reference birth JD at local noon: candidate times differ from it by
    # minutes, which shifts progressed positions by < 0.01' for everything
    # except the Moon (recomputed per candidate below).
    noon_utc = core.localize_to_utc(
        dt.datetime(bd.year, bd.month, bd.day, 12, 0), req.place.tz
    )
    birth_jd_noon = core.to_julian_day(noon_utc)
    natal_positions = core.all_planet_positions(birth_jd_noon)

    contexts = [
        EventContext(e, birth_jd_noon, natal_positions, cfg.precision_weights)
        for e in req.events
    ]

    sh, sm = map(int, req.candidate_window.start_time.split(":"))
    eh, em = map(int, req.candidate_window.end_time.split(":"))
    start_min, end_min = sh * 60 + sm, eh * 60 + em
    step = req.candidate_window.step_minutes
    minutes = list(range(start_min, end_min + 1, step))

    candidates = _score_candidates(req, contexts, minutes, True)

    # Stage-1 hook: mark, do not drop. The density curve stays a complete
    # picture of the window even when a rising sign has been supplied.
    for c in candidates:
        c["excluded"] = bool(
            req.ascendant_sign is not None and c["asc_sign"] != req.ascendant_sign
        )

    eligible = [i for i, c in enumerate(candidates) if not c["excluded"]] or list(
        range(len(candidates))
    )
    best_idx = max(eligible, key=lambda i: (candidates[i]["total_score"], -i))
    best = candidates[best_idx]

    threshold = best["total_score"] * cfg.plateau_ratio
    lo = best_idx
    while lo > 0 and candidates[lo - 1]["total_score"] >= threshold:
        lo -= 1
    hi = best_idx
    while hi < len(candidates) - 1 and candidates[hi + 1]["total_score"] >= threshold:
        hi += 1
    residual = (hi - lo) * step

    null_peaks = _permutation_null(req, birth_jd_noon, natal_positions, minutes)
    confidence = _confidence(candidates, eligible, null_peaks, cfg)

    chosen, selection = _select_time(candidates, eligible, best_idx, step, cfg)

    return {
        "candidates": candidates,
        "density": [
            {"time": c["time"], "score": c["total_score"], "excluded": c["excluded"]}
            for c in candidates
        ],
        "suggested_best": {
            "time": None if confidence["refused"] else chosen,
            "score": best["total_score"],
            "residual_window_minutes": residual,
            "selection": selection,
        },
        "confidence": confidence,
        "config_echo": cfg.model_dump(),
    }


def _select_time(
    candidates: list[dict],
    eligible: list[int],
    best_idx: int,
    step: int,
    cfg,
) -> tuple[str, str]:
    """Argmax, unless the surviving set is too narrow for the argmax to mean
    anything - in which case the midpoint of that interval.

    Measured on the 41-case corpus: once the candidate set is narrow, the
    score ordering is anti-correlated with the truth (AUC 0.422 over all
    cases, 0.420 on holdout) and loses to a blind pick 20 times against 13.
    Taking the middle of the surviving interval is strictly the better
    estimator there, so below `midpoint_below_minutes` the engine stops
    pretending its ordering is informative. Above it, nothing changes.
    """
    if cfg.midpoint_below_minutes <= 0 or not eligible:
        return candidates[best_idx]["time"], "argmax"

    # The contiguous run of eligible candidates containing the argmax.
    eligible_set = set(eligible)
    lo = hi = best_idx
    while lo - 1 >= 0 and (lo - 1) in eligible_set:
        lo -= 1
    while hi + 1 < len(candidates) and (hi + 1) in eligible_set:
        hi += 1

    width = (hi - lo + 1) * step
    if width >= cfg.midpoint_below_minutes:
        return candidates[best_idx]["time"], "argmax"
    return candidates[(lo + hi) // 2]["time"], "interval_midpoint"


def _confidence(
    candidates: list[dict],
    eligible: list[int],
    null_peaks: list[float],
    cfg,
) -> dict:
    """Confidence that responds to evidence, plus a refusal state.

    `residual_window_minutes` stays in `suggested_best` because clients read
    it, but it is deliberately no longer the confidence figure: it evaluates
    to 0 or one step on random data and does not move when every event's date
    precision drops from day to year. `permutation_percentile` replaces it -
    the real peak's rank among peaks from the same events on shuffled dates.

    A low percentile is the engine saying the events did not pick this time
    out; in that case it returns no time at all rather than a confident wrong
    answer.
    """
    scores = sorted((candidates[i]["total_score"] for i in eligible), reverse=True)
    peak = scores[0] if scores else 0.0
    runner_up = scores[1] if len(scores) > 1 else 0.0
    mean = (sum(scores) / len(scores)) if scores else 0.0

    separation = ((peak - runner_up) / peak) if peak > 0 else 0.0
    lift = (peak / mean) if mean > 0 else None

    percentile = None
    if null_peaks:
        below = sum(1 for p in null_peaks if p < peak)
        ties = sum(1 for p in null_peaks if p == peak)
        percentile = (below + 0.5 * ties) / len(null_peaks)

    reasons = []
    if peak <= 0:
        reasons.append("no technique scored above zero for any candidate")
    if separation < cfg.refusal_min_separation:
        reasons.append(
            "top candidates are not separable "
            f"(separation {separation:.3f} < {cfg.refusal_min_separation})"
        )
    if percentile is not None and percentile < cfg.refusal_percentile:
        reasons.append(
            "the real peak does not stand out from shuffled event dates "
            f"(permutation percentile {percentile:.2f} < {cfg.refusal_percentile})"
        )

    refused = bool(reasons)
    return {
        "refused": refused,
        "reasons": reasons,
        "level": "none" if refused else ("high" if separation >= 0.15 else "moderate"),
        "peak_score": round(peak, core.ROUND_DEG),
        "mean_score": round(mean, core.ROUND_DEG),
        "peak_over_mean": None if lift is None else round(lift, core.ROUND_DEG),
        "separation": round(separation, core.ROUND_DEG),
        "permutation_trials": len(null_peaks),
        "permutation_percentile": None
        if percentile is None
        else round(percentile, core.ROUND_DEG),
    }
