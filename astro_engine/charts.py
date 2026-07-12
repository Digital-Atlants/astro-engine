"""Chart-level computations: natal, secondary progressions, solar arc,
annual profections."""

from __future__ import annotations

import datetime as dt

from . import core
from .schemas import DerivedChartRequest, NatalRequest

YEAR_DAYS = 365.25


def _birth_jd(req: NatalRequest) -> float:
    when_utc = core.localize_to_utc(req.birth_datetime, req.place.tz)
    return core.to_julian_day(when_utc)


def _years_elapsed(birth_utc_jd: float, target_date: dt.date) -> float:
    target_jd = core.to_julian_day(
        dt.datetime(target_date.year, target_date.month, target_date.day, 12, 0)
    )
    return (target_jd - birth_utc_jd) / YEAR_DAYS


def natal_chart(req: NatalRequest) -> dict:
    jd = _birth_jd(req)
    cusps, asc, mc = core.houses_and_angles(
        jd, req.place.lat, req.place.lon, req.house_system
    )
    positions = core.all_planet_positions(jd)
    planets = core.planet_payload(positions, cusps)
    aspect_points = {name: lon for name, (lon, _) in positions.items()}
    aspect_points["asc"] = asc
    aspect_points["mc"] = mc
    return {
        "planets": planets,
        "asc_deg": round(asc, core.ROUND_DEG),
        "mc_deg": round(mc, core.ROUND_DEG),
        "cusps_deg": [round(c, core.ROUND_DEG) for c in cusps],
        "aspects": core.aspects_between(aspect_points),
    }


def progressed_jd(birth_jd: float, target_date: dt.date) -> float:
    """Day-for-a-year: one ephemeris day per elapsed year."""
    return birth_jd + _years_elapsed(birth_jd, target_date)


def progressions(req: DerivedChartRequest) -> dict:
    jd_birth = _birth_jd(req)
    jd_prog = progressed_jd(jd_birth, req.target_date)
    cusps, asc, mc = core.houses_and_angles(
        jd_prog, req.place.lat, req.place.lon, req.house_system
    )
    positions = core.all_planet_positions(jd_prog)
    return {
        "progressed_planets": core.planet_payload(positions, cusps),
        "progressed_asc_deg": round(asc, core.ROUND_DEG),
        "progressed_mc_deg": round(mc, core.ROUND_DEG),
        "cusps_deg": [round(c, core.ROUND_DEG) for c in cusps],
    }


def solar_arc(req: DerivedChartRequest) -> dict:
    jd_birth = _birth_jd(req)
    jd_prog = progressed_jd(jd_birth, req.target_date)
    natal_positions = core.all_planet_positions(jd_birth)
    arc = core.norm360(
        core.planet_position(jd_prog, 0)[0] - natal_positions["sun"][0]
    )
    cusps, asc, mc = core.houses_and_angles(
        jd_birth, req.place.lat, req.place.lon, req.house_system
    )
    directed = [
        {
            "name": name,
            "longitude_deg": round(core.norm360(lon + arc), core.ROUND_DEG),
        }
        for name, (lon, _) in natal_positions.items()
    ]
    directed.append(
        {"name": "asc", "longitude_deg": round(core.norm360(asc + arc), core.ROUND_DEG)}
    )
    directed.append(
        {"name": "mc", "longitude_deg": round(core.norm360(mc + arc), core.ROUND_DEG)}
    )
    return {
        "solar_arc_deg": round(arc, core.ROUND_DEG),
        "directed_points": directed,
    }


def profection_for(birth_date: dt.date, target_date: dt.date, asc_deg: float) -> dict:
    age = target_date.year - birth_date.year
    if (target_date.month, target_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    age = max(age, 0)
    activated_house = age % 12 + 1
    asc_sign_index = int(core.norm360(asc_deg) // 30)
    activated_sign = core.SIGNS[(asc_sign_index + activated_house - 1) % 12]
    return {
        "profection_year": age,
        "activated_house": activated_house,
        "activated_sign": activated_sign,
        "year_lord": core.SIGN_RULERS[activated_sign],
    }


def profections(req: DerivedChartRequest) -> dict:
    jd_birth = _birth_jd(req)
    _, asc, _ = core.houses_and_angles(
        jd_birth, req.place.lat, req.place.lon, req.house_system
    )
    return profection_for(req.birth_datetime.date(), req.target_date, asc)
