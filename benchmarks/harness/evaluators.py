"""Candidate evaluators, as measurable prototypes.

These exist so Work item 2 can ask one question of each of them before any of
them is written into the shipped scorer: **does this value actually vary
between candidate times inside a single rising-sign block?** An evaluator that
is flat inside the block cannot resolve sub-sign position no matter how sound
it is astrologically.

Only evaluators that pass that filter are ported into
`astro_engine/rectification.py`. Nothing here is imported by the service.
"""

from __future__ import annotations

import datetime as dt
import functools

import swisseph as swe

from astro_engine import core
from astro_engine.charts import YEAR_DAYS, profection_for

from . import protocol

EQ_FLAGS = core.FLAGS | swe.FLG_EQUATORIAL

ASPECTS = (("conj", 0.0), ("sq", 90.0), ("opp", 180.0))

# Intermediate quadrant cusps. 1/4/7/10 are the angles and are already scored,
# so they are excluded here to keep the evaluator's contribution disjoint.
INTERMEDIATE_CUSPS = (2, 3, 5, 6, 8, 9, 11, 12)

TRANSIT_PLANETS = ("mars", "jupiter", "saturn", "uranus", "neptune", "pluto")
DIRECTED_BODIES = ("sun", "moon", "mars", "jupiter", "saturn")
PROG_BODIES = ("sun", "mercury", "venus", "mars")

# Primary-direction keys, in degrees of arc per year of life.
DIRECTION_KEYS = {"ptolemy": 1.0, "naibod": 59.0 / 60.0 + 8.0 / 3600.0}


def _hit(orb: float, max_orb: float) -> float:
    return max(0.0, 1.0 - orb / max_orb) if max_orb > 0 else 0.0


def _aspect_score(a: float, b: float, max_orb: float) -> float:
    sep = core.angle_diff(a, b)
    best = 0.0
    for _, deg in ASPECTS:
        orb = abs(sep - deg)
        if orb <= max_orb:
            best = max(best, _hit(orb, max_orb))
    return best


class CaseContext:
    """Everything about a case that does not depend on the candidate time."""

    def __init__(self, case: dict):
        self.case = case
        self.place = case["place"]
        self.birth = dt.date.fromisoformat(case["birth_date"])
        self.jd_noon = core.to_julian_day(
            core.localize_to_utc(
                dt.datetime(self.birth.year, self.birth.month, self.birth.day, 12, 0),
                self.place["tz"],
            )
        )
        self.natal = core.all_planet_positions(self.jd_noon)
        self.events = []
        for e in case["events"]:
            self.events.append(EventContext(e, self))

    @functools.cached_property
    def obliquity(self) -> float:
        return swe.calc_ut(self.jd_noon, swe.ECL_NUT)[0][0]

    def jd_at(self, minute: int) -> float:
        hh, mm = divmod(minute, 60)
        return core.to_julian_day(
            core.localize_to_utc(
                dt.datetime(self.birth.year, self.birth.month, self.birth.day, hh, mm),
                self.place["tz"],
            )
        )

    @functools.lru_cache(maxsize=512)
    def frame(self, minute: int, house_system: str) -> tuple:
        """(cusps, asc, mc, armc) for one candidate time."""
        jd = self.jd_at(minute)
        cusps, ascmc = swe.houses(
            jd, self.place["lat"], self.place["lon"], core.HOUSE_SYSTEM_CODES[house_system]
        )
        return (
            [core.norm360(c) for c in cusps[:12]],
            core.norm360(ascmc[0]),
            core.norm360(ascmc[1]),
            core.norm360(ascmc[2]),
        )


class EventContext:
    def __init__(self, event: dict, ctx: CaseContext):
        self.event = event
        date = dt.date.fromisoformat(event["date"])
        if event["date_precision"] == "month":
            date = date.replace(day=15)
        elif event["date_precision"] == "year":
            date = date.replace(month=7, day=1)
        self.date = date
        self.jd = core.to_julian_day(
            dt.datetime(date.year, date.month, date.day, 12, 0)
        )
        self.years = (self.jd - ctx.jd_noon) / YEAR_DAYS
        self.orb_scale = 1.0 if event["date_precision"] == "day" else 2.0
        self.allow_fast = event["date_precision"] == "day"

        self.transits = {
            name: core.planet_position(self.jd, pid)[0]
            for name, pid in core.PLANETS
            if name in TRANSIT_PLANETS
        }
        jd_prog = ctx.jd_noon + self.years
        self.prog = {
            name: core.planet_position(jd_prog, pid)[0]
            for name, pid in core.PLANETS
            if name in PROG_BODIES
        }
        self.jd_prog = jd_prog
        self.solar_arc = core.norm360(
            core.planet_position(jd_prog, swe.SUN)[0] - ctx.natal["sun"][0]
        )
        self.arc_directed = {
            name: core.norm360(lon + self.solar_arc)
            for name, (lon, _) in ctx.natal.items()
            if name in DIRECTED_BODIES
        }


# --------------------------------------------------------------------------
# Evaluators. Each returns a score for one candidate minute.
# --------------------------------------------------------------------------


def ev_transits_to_angles(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    _, asc, mc, _ = ctx.frame(minute, hs)
    total = 0.0
    for ec in ctx.events:
        for lon in ec.transits.values():
            for ang in (asc, mc):
                total += _aspect_score(lon, ang, 1.0 * ec.orb_scale)
    return total


def ev_secondary_progressions(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    _, asc, mc, _ = ctx.frame(minute, hs)
    total = 0.0
    for ec in ctx.events:
        if not ec.allow_fast:
            continue
        prog_moon = core.planet_position(ctx.jd_at(minute) + ec.years, swe.MOON)[0]
        for lon in list(ec.prog.values()) + [prog_moon]:
            for ang in (asc, mc):
                total += _aspect_score(lon, ang, 1.0 * ec.orb_scale)
    return total


def ev_solar_arc(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    _, asc, mc, _ = ctx.frame(minute, hs)
    total = 0.0
    for ec in ctx.events:
        for lon in ec.arc_directed.values():
            for ang in (asc, mc):
                total += _aspect_score(lon, ang, 1.0 * ec.orb_scale)
    return total


def ev_profections(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    from astro_engine.rectification import EVENT_HOUSES

    _, asc, _, _ = ctx.frame(minute, hs)
    total = 0.0
    for ec in ctx.events:
        prof = profection_for(ctx.birth, ec.date, asc)
        if prof["activated_house"] in EVENT_HOUSES[ec.event["type"]]:
            total += 1.0
    return total


def ev_sect(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    """Day/night sect as the tradition uses it under whole-sign houses.

    The Sun's whole-sign house is a function of the Ascendant *sign* alone,
    which is exactly the claim Work item 2 asks us to test rather than assume.
    """
    cusps, asc, _, _ = ctx.frame(minute, hs)
    sun = ctx.natal["sun"][0]
    house = core.house_of(sun, cusps)
    return 1.0 if house in (7, 8, 9, 10, 11, 12) else 0.0


def ev_saros(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    """Saros series of the solar eclipse preceding birth.

    A property of the birth *date*, so it cannot depend on the birth time at
    all. Included in the table to make that visible rather than argued.
    """
    return float(_prenatal_saros(ctx.jd_noon))


@functools.lru_cache(maxsize=256)
def _prenatal_saros(jd: float) -> int:
    res = swe.sol_eclipse_when_glob(jd, core.FLAGS, 0, True)
    return int(res[1][0] * 1000) % 223  # stand-in series index, date-only


def ev_quadrant_cusps(ctx: CaseContext, minute: int, hs: str = "placidus") -> float:
    """Transiting, progressed and directed bodies on the intermediate cusps.

    Under a quadrant system these cusps sweep continuously with birth time and
    do not sit on sign boundaries, so a crossing happens at a specific minute.
    """
    cusps, _, _, _ = ctx.frame(minute, hs)
    targets = [cusps[h - 1] for h in INTERMEDIATE_CUSPS]
    total = 0.0
    for ec in ctx.events:
        bodies = list(ec.transits.values()) + list(ec.arc_directed.values())
        if ec.allow_fast:
            bodies += list(ec.prog.values())
        for lon in bodies:
            for cusp in targets:
                total += _aspect_score(lon, cusp, 1.0 * ec.orb_scale)
    return total


def ev_directed_angles(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    """Solar-arc directed Asc and MC to natal planets.

    Computed and then discarded by the shipped scorer.
    """
    _, asc, mc, _ = ctx.frame(minute, hs)
    natal = {n: lon for n, (lon, _) in ctx.natal.items()}
    total = 0.0
    for ec in ctx.events:
        d_asc = core.norm360(asc + ec.solar_arc)
        d_mc = core.norm360(mc + ec.solar_arc)
        for lon in natal.values():
            for ang in (d_asc, d_mc):
                total += _aspect_score(lon, ang, 1.0 * ec.orb_scale)
    return total


def ev_primary_directions(
    ctx: CaseContext, minute: int, hs: str = "whole_sign", key: str = "naibod"
) -> float:
    """Mundane primary directions of natal promissors to the MC.

    The arc from a planet's right ascension to the natal RAMC converts to an
    age at the chosen key. RAMC advances one degree per four minutes of birth
    time, so a four-minute shift moves every predicted age by about a year -
    the sharpest birth-time dependence available.
    """
    _, _, _, armc = ctx.frame(minute, hs)
    rate = DIRECTION_KEYS[key]
    total = 0.0
    for name, pid in core.PLANETS:
        ra = core.norm360(swe.calc_ut(ctx.jd_noon, pid, EQ_FLAGS)[0][0])
        for direct_to in (0.0, 180.0):  # MC and IC
            arc = core.norm360(ra - armc + direct_to)
            if arc > 180.0:
                continue  # only direct conjunctions reached within a lifetime
            years = arc / rate
            for ec in ctx.events:
                orb_years = 1.0 * ec.orb_scale
                delta = abs(years - ec.years)
                if delta <= orb_years:
                    total += _hit(delta, orb_years)
    return total


def ev_eclipse_on_angle(ctx: CaseContext, minute: int, hs: str = "whole_sign") -> float:
    """An eclipse near an event date falling within orb of a natal angle."""
    _, asc, mc, _ = ctx.frame(minute, hs)
    total = 0.0
    for ec in ctx.events:
        for lon in _eclipses_near(ec.jd):
            for ang in (asc, mc):
                total += _aspect_score(lon, ang, 1.0 * ec.orb_scale)
    return total


@functools.lru_cache(maxsize=1024)
def _eclipses_near(jd: float) -> tuple[float, ...]:
    """Ecliptic longitudes of the solar eclipses bracketing a date."""
    out = []
    for backward in (True, False):
        try:
            res = swe.sol_eclipse_when_glob(jd, core.FLAGS, 0, backward)
            t = res[1][0]
            if abs(t - jd) <= 200:
                out.append(core.planet_position(t, swe.SUN)[0])
        except Exception:
            continue
    return tuple(out)


EVALUATORS = {
    "transits_to_angles": ev_transits_to_angles,
    "secondary_progressions": ev_secondary_progressions,
    "solar_arc": ev_solar_arc,
    "profections": ev_profections,
    "sect": ev_sect,
    "saros_family": ev_saros,
    "quadrant_cusps": ev_quadrant_cusps,
    "directed_angles": ev_directed_angles,
    "primary_directions": ev_primary_directions,
    "eclipse_on_angle": ev_eclipse_on_angle,
}

# Which of these can, even in principle, be affected by the house system.
HOUSE_SENSITIVE = {"quadrant_cusps", "profections", "sect"}


def score_series(case: dict, name: str, minutes: list[int], hs: str = "whole_sign") -> list[float]:
    ctx = CaseContext(case)
    fn = EVALUATORS[name]
    return [fn(ctx, m, hs) for m in minutes]
