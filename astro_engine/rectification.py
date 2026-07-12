"""Birth-time rectification scoring.

Performance contract: transit/progressed positions and the solar arc for an
event date do NOT depend on the candidate birth time (except the progressed
Moon, which is recomputed per candidate with a single cheap ephemeris call).
They are precomputed once per event; the per-candidate loop only computes
Asc/MC/cusps via swe.houses and tests the precomputed longitudes against them.
"""

from __future__ import annotations

import datetime as dt

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


def _event_jd(event: RectificationEvent) -> float:
    date = event.date
    if event.date_precision == "month":
        date = date.replace(day=15)
    elif event.date_precision == "year":
        date = date.replace(month=7, day=1)
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
            if name in ("sun", "mars", "venus", "mercury")
        }

        self.solar_arc = core.norm360(
            core.planet_position(jd_prog, 0)[0] - natal_positions["sun"][0]
        )
        self.arc_directed = {
            name: core.norm360(lon + self.solar_arc)
            for name, (lon, _) in natal_positions.items()
            if name in ("sun", "moon", "mars", "jupiter", "saturn")
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
                directed = dict(ctx.arc_directed)
                directed["asc"] = core.norm360(asc + ctx.solar_arc)
                directed["mc"] = core.norm360(mc + ctx.solar_arc)
                natal_angles = {"asc": asc, "mc": mc}
                hits += _angle_hits(
                    {k: v for k, v in directed.items() if k not in ("asc", "mc")},
                    natal_angles,
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
        candidates.append(
            {"time": f"{hh:02d}:{mm:02d}", "total_score": total, "hits": hits}
        )

    best_idx = max(
        range(len(candidates)), key=lambda i: (candidates[i]["total_score"], -i)
    )
    best = candidates[best_idx]
    threshold = best["total_score"] * cfg.plateau_ratio
    lo = best_idx
    while lo > 0 and candidates[lo - 1]["total_score"] >= threshold:
        lo -= 1
    hi = best_idx
    while hi < len(candidates) - 1 and candidates[hi + 1]["total_score"] >= threshold:
        hi += 1
    residual = (hi - lo) * step

    return {
        "candidates": candidates,
        "suggested_best": {
            "time": best["time"],
            "score": best["total_score"],
            "residual_window_minutes": residual,
        },
        "config_echo": cfg.model_dump(),
    }
