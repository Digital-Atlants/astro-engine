"""FROZEN EXPERIMENT: the rectification scorer with the Work item 3 additions.

This is the exact scorer the Work item 3 ablation was run against. Every one
of those additions failed its ablation on the holdout split and was reverted
out of `astro_engine/` before merge, so this file is the only place they still
exist. It lives under `benchmarks/` because it is evidence, not product: it is
never imported by the service.

Do not "fix" or extend it. Its value is that it is the code that produced
`benchmarks/ablation_table.json` and `benchmarks/weight_sweep.json`. If a
future spec wants to retry one of these evaluators, start from the measurement
in `RESULTS_SUBSIGN.md`, not from this file.

Additions present here and absent from the shipped engine:
  3.1 quadrant_cusps        3.2 directed_angles
  3.3 primary_directions    3.4 eclipse_on_angle
  3.5 event_technique_matching
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random

import swisseph as swe

from pydantic import BaseModel, Field

from astro_engine import core
from astro_engine.charts import YEAR_DAYS, profection_for
from astro_engine.schemas import (
    CandidateWindow,
    HouseSystem,
    Place,
    RectificationEvent,
)


class CandidateConfig(BaseModel):
    """The experimental config. Kept here so the shipped schema does not have
    to carry options for techniques that failed and were reverted."""

    house_system: HouseSystem = "whole_sign"
    techniques: list[str] = [
        "transits_to_angles",
        "secondary_progressions",
        "solar_arc",
        "profections",
    ]
    orbs: dict[str, float] = {
        "transits_to_angles": 1.0,
        "secondary_progressions": 1.0,
        "solar_arc": 1.0,
        "quadrant_cusps": 1.0,
        "directed_angles": 1.0,
        "eclipse_on_angle": 1.0,
    }
    technique_weights: dict[str, float] = {
        "transits_to_angles": 1.0,
        "secondary_progressions": 1.2,
        "solar_arc": 0.8,
        "profections": 0.6,
        "quadrant_cusps": 1.0,
        "directed_angles": 1.2,
        "primary_directions": 1.4,
        "eclipse_on_angle": 1.0,
    }
    precision_weights: dict[str, float] = {"day": 1.0, "month": 0.5, "year": 0.25}
    plateau_ratio: float = Field(default=0.9, gt=0, le=1)
    direction_key: str = "naibod"
    direction_orb_years: float = 1.0
    event_technique_matching: bool = False
    permutation_trials: int = 0
    refusal_percentile: float = 0.90
    refusal_min_separation: float = 0.05


class CandidateRequest(BaseModel):
    birth_date: dt.date
    place: Place
    candidate_window: CandidateWindow
    events: list[RectificationEvent]
    config: CandidateConfig = CandidateConfig()
    ascendant_sign: str | None = None


def houses_angles_armc(jd_ut, lat, lon, house_system):
    cusps, ascmc = swe.houses(jd_ut, lat, lon, core.HOUSE_SYSTEM_CODES[house_system])
    return (
        [core.norm360(c) for c in cusps[:12]],
        core.norm360(ascmc[0]),
        core.norm360(ascmc[1]),
        core.norm360(ascmc[2]),
    )


def right_ascension(jd_ut, planet_id):
    pos, _ = swe.calc_ut(jd_ut, planet_id, core.FLAGS | swe.FLG_EQUATORIAL)
    return core.norm360(pos[0])

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

# Intermediate quadrant cusps. The four angles are scored separately, so the
# quadrant-cusp evaluator takes only the cusps that are not angles.
INTERMEDIATE_CUSPS = (2, 3, 5, 6, 8, 9, 11, 12)

DIRECTED_BODIES = ("sun", "moon", "mars", "jupiter", "saturn")
PROG_BODIES = ("sun", "mercury", "venus", "mars")

# Degrees of primary-direction arc per year of life.
DIRECTION_KEYS = {"ptolemy": 1.0, "naibod": 59.0 / 60.0 + 8.0 / 3600.0}

# Event-to-technique matching. Sudden, dated events are read by fast movers;
# structural, gradual events by slow ones. Applying every technique to every
# event is what makes agreement nearly free.
FAST_EVENTS = frozenset({"accident", "surgery", "child_birth", "marriage"})
SLOW_EVENTS = frozenset({"career_break", "relocation", "death_of_close", "other"})

FAST_TECHNIQUES = frozenset({"secondary_progressions", "transits_to_angles"})
SLOW_TECHNIQUES = frozenset(
    {"solar_arc", "directed_angles", "primary_directions", "profections"}
)
ALWAYS_TECHNIQUES = frozenset({"quadrant_cusps", "eclipse_on_angle"})


def _technique_applies(technique: str, event: RectificationEvent, enabled: bool) -> bool:
    if not enabled or technique in ALWAYS_TECHNIQUES:
        return True
    if event.type in FAST_EVENTS:
        return technique in FAST_TECHNIQUES or technique in ALWAYS_TECHNIQUES
    if event.type in SLOW_EVENTS:
        return technique in SLOW_TECHNIQUES or technique in ALWAYS_TECHNIQUES
    return True


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
        "eclipse_longitudes",
    )

    def __init__(
        self,
        event: RectificationEvent,
        birth_jd_noon: float,
        natal_positions: dict[str, tuple[float, float]],
        precision_weights: dict[str, float],
        want_eclipses: bool = False,
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
        self.eclipse_longitudes = _eclipses_near(self.jd) if want_eclipses else ()


def _eclipses_near(jd: float) -> tuple[float, ...]:
    """Ecliptic longitudes of the solar eclipses bracketing a date."""
    out = []
    for backward in (True, False):
        try:
            res = swe.sol_eclipse_when_glob(jd, core.FLAGS, 0, backward)
        except Exception:
            continue
        t = res[1][0]
        if abs(t - jd) <= 200.0:
            out.append(core.planet_position(t, swe.SUN)[0])
    return tuple(out)


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
        for aname in sorted(angles):
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
    req: CandidateRequest,
    contexts: list[EventContext],
    birth_jd_noon: float,
    natal_positions: dict[str, tuple[float, float]],
    natal_ra: dict[str, float],
    minutes: list[int],
    collect_hits: bool,
) -> list[dict]:
    """The scoring loop. Shared by the real run and every permutation trial."""
    cfg = req.config
    bd = req.birth_date
    tw = cfg.technique_weights
    orbs = cfg.orbs
    match = cfg.event_technique_matching
    key_rate = DIRECTION_KEYS[cfg.direction_key]
    candidates = []

    for m in minutes:
        hh, mm = divmod(m, 60)
        cand_utc = core.localize_to_utc(
            dt.datetime(bd.year, bd.month, bd.day, hh, mm), req.place.tz
        )
        cand_jd = core.to_julian_day(cand_utc)
        cusps, asc, mc, armc = houses_angles_armc(
            cand_jd, req.place.lat, req.place.lon, cfg.house_system
        )
        angles = {"asc": asc, "mc": mc}
        hits: list[dict] = []

        for ctx in contexts:
            ev = ctx.event
            base_w = ev.weight * ctx.precision_weight

            def enabled(name: str) -> bool:
                return name in cfg.techniques and _technique_applies(name, ev, match)

            if enabled("transits_to_angles"):
                hits += _angle_hits(
                    ctx.transit_positions,
                    angles,
                    orbs.get("transits_to_angles", 1.0) * ctx.orb_scale,
                    "transits_to_angles",
                    "tr",
                    ev.id,
                    base_w * tw.get("transits_to_angles", 1.0),
                )

            if enabled("secondary_progressions") and ctx.allow_fast:
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

            if enabled("solar_arc"):
                hits += _angle_hits(
                    ctx.arc_directed,
                    angles,
                    orbs.get("solar_arc", 1.0) * ctx.orb_scale,
                    "solar_arc",
                    "sa",
                    ev.id,
                    base_w * tw.get("solar_arc", 1.0),
                )

            if enabled("directed_angles"):
                # 3.2: the directed angles the previous version computed and
                # then filtered out one line later. Directed MC to a natal
                # planet is the most time-sensitive classical factor there is.
                directed = {
                    "d_asc": core.norm360(asc + ctx.solar_arc),
                    "d_mc": core.norm360(mc + ctx.solar_arc),
                }
                hits += _angle_hits(
                    {n: lon for n, (lon, _) in natal_positions.items()},
                    directed,
                    orbs.get("directed_angles", 1.0) * ctx.orb_scale,
                    "directed_angles",
                    "da",
                    ev.id,
                    base_w * tw.get("directed_angles", 1.0),
                )

            if enabled("quadrant_cusps"):
                # 3.1: the cusps were already being computed and thrown away,
                # which is why house_system had no effect on the result.
                targets = {
                    f"c{h}": cusps[h - 1] for h in INTERMEDIATE_CUSPS
                }
                bodies = dict(ctx.transit_positions)
                bodies.update({f"sa_{k}": v for k, v in ctx.arc_directed.items()})
                if ctx.allow_fast:
                    bodies.update({f"sp_{k}": v for k, v in ctx.prog_positions.items()})
                hits += _angle_hits(
                    bodies,
                    targets,
                    orbs.get("quadrant_cusps", 1.0) * ctx.orb_scale,
                    "quadrant_cusps",
                    "qc",
                    ev.id,
                    base_w * tw.get("quadrant_cusps", 1.0),
                )

            if enabled("primary_directions"):
                # 3.3: ARMC advances one degree per four minutes of birth
                # time, so the age a direction predicts moves about a year for
                # every four minutes. The sharpest factor available.
                orb_years = cfg.direction_orb_years * ctx.orb_scale
                w = base_w * tw.get("primary_directions", 1.0)
                for pname in sorted(natal_ra):
                    for label, offset in (("mc", 0.0), ("ic", 180.0)):
                        arc = core.norm360(natal_ra[pname] - armc + offset)
                        if arc > 180.0:
                            continue
                        years = arc / key_rate
                        delta = abs(years - ctx.prog_years)
                        if delta <= orb_years:
                            hits.append(
                                {
                                    "event_id": ev.id,
                                    "technique": "primary_directions",
                                    "factor": f"pd_{pname}_conj_{label}",
                                    "orb_deg": round(delta * key_rate, core.ROUND_DEG),
                                    "score": round(
                                        _hit_score(delta, orb_years) * w, core.ROUND_DEG
                                    ),
                                }
                            )

            if enabled("eclipse_on_angle") and ctx.eclipse_longitudes:
                hits += _angle_hits(
                    {
                        f"ecl{i}": lon
                        for i, lon in enumerate(ctx.eclipse_longitudes)
                    },
                    angles,
                    orbs.get("eclipse_on_angle", 1.0) * ctx.orb_scale,
                    "eclipse_on_angle",
                    "ec",
                    ev.id,
                    base_w * tw.get("eclipse_on_angle", 1.0),
                )

            if enabled("profections"):
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
    req: CandidateRequest,
    birth_jd_noon: float,
    natal_positions: dict,
    natal_ra: dict,
    minutes: list[int],
    want_eclipses: bool,
) -> list[float]:
    """Peak scores from `permutation_trials` runs on shuffled event dates.

    The seed is derived from the request itself, so the null is deterministic
    for a given request while still being a genuine shuffle.
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
        shuffled = []
        for e in req.events:
            drawn = lo + dt.timedelta(days=rng.randint(0, span))
            shuffled.append(e.model_copy(update={"date": drawn}))
        contexts = [
            EventContext(
                e,
                birth_jd_noon,
                natal_positions,
                req.config.precision_weights,
                want_eclipses,
            )
            for e in shuffled
        ]
        cands = _score_candidates(
            req, contexts, birth_jd_noon, natal_positions, natal_ra, minutes, False
        )
        peaks.append(max(c["total_score"] for c in cands))
    return sorted(peaks)


def score_rectification(req: CandidateRequest) -> dict:
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

    want_eclipses = "eclipse_on_angle" in cfg.techniques
    natal_ra = (
        {name: right_ascension(birth_jd_noon, pid) for name, pid in core.PLANETS}
        if "primary_directions" in cfg.techniques
        else {}
    )

    contexts = [
        EventContext(e, birth_jd_noon, natal_positions, cfg.precision_weights, want_eclipses)
        for e in req.events
    ]

    sh, sm = map(int, req.candidate_window.start_time.split(":"))
    eh, em = map(int, req.candidate_window.end_time.split(":"))
    start_min, end_min = sh * 60 + sm, eh * 60 + em
    step = req.candidate_window.step_minutes
    minutes = list(range(start_min, end_min + 1, step))

    candidates = _score_candidates(
        req, contexts, birth_jd_noon, natal_positions, natal_ra, minutes, True
    )

    # Stage-1 hook: mark, do not drop. The density curve stays complete.
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

    null_peaks = _permutation_null(
        req, birth_jd_noon, natal_positions, natal_ra, minutes, want_eclipses
    )
    confidence = _confidence(best, candidates, eligible, null_peaks, cfg)

    return {
        "candidates": candidates,
        "density": [
            {"time": c["time"], "score": c["total_score"], "excluded": c["excluded"]}
            for c in candidates
        ],
        "suggested_best": {
            "time": None if confidence["refused"] else best["time"],
            "score": best["total_score"],
            "residual_window_minutes": residual,
        },
        "confidence": confidence,
        "config_echo": cfg.model_dump(),
    }


def _confidence(
    best: dict,
    candidates: list[dict],
    eligible: list[int],
    null_peaks: list[float],
    cfg,
) -> dict:
    """Confidence that responds to evidence, and a refusal state.

    `residual_window_minutes` is kept in the response because clients read it,
    but it is not the confidence figure: it evaluates to 0 or one step on
    random data and does not move when every event's date precision drops.
    The permutation percentile is the only figure here calibrated against
    anything - it is the real peak's rank among peaks from the same events on
    shuffled dates.
    """
    scores = sorted(
        (candidates[i]["total_score"] for i in eligible), reverse=True
    )
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
