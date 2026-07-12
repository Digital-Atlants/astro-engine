"""Core astronomical computations built on pyswisseph (Moshier ephemeris).

All functions are pure and deterministic: floats are rounded to fixed
precision before leaving this module so identical requests produce
byte-identical JSON.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pytz
import swisseph as swe

FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED

ROUND_DEG = 6

SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]

# Traditional sign rulers (used as profection year lords).
SIGN_RULERS = {
    "aries": "mars", "taurus": "venus", "gemini": "mercury",
    "cancer": "moon", "leo": "sun", "virgo": "mercury",
    "libra": "venus", "scorpio": "mars", "sagittarius": "jupiter",
    "capricorn": "saturn", "aquarius": "saturn", "pisces": "jupiter",
}

PLANETS = [
    ("sun", swe.SUN),
    ("moon", swe.MOON),
    ("mercury", swe.MERCURY),
    ("venus", swe.VENUS),
    ("mars", swe.MARS),
    ("jupiter", swe.JUPITER),
    ("saturn", swe.SATURN),
    ("uranus", swe.URANUS),
    ("neptune", swe.NEPTUNE),
    ("pluto", swe.PLUTO),
]

NODE = swe.TRUE_NODE

HOUSE_SYSTEM_CODES = {"whole_sign": b"W", "placidus": b"P"}

MAJOR_ASPECTS = [
    ("conjunction", 0.0, 8.0),
    ("sextile", 60.0, 4.0),
    ("square", 90.0, 6.0),
    ("trine", 120.0, 6.0),
    ("opposition", 180.0, 8.0),
]


def norm360(x: float) -> float:
    return x % 360.0


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute angular separation between two longitudes."""
    d = abs(norm360(a) - norm360(b))
    return min(d, 360.0 - d)


def sign_of(longitude: float) -> str:
    return SIGNS[int(norm360(longitude) // 30) % 12]


def to_julian_day(when_utc: dt.datetime) -> float:
    hour = (
        when_utc.hour
        + when_utc.minute / 60.0
        + when_utc.second / 3600.0
        + when_utc.microsecond / 3.6e9
    )
    return swe.julday(when_utc.year, when_utc.month, when_utc.day, hour, swe.GREG_CAL)


def localize_to_utc(naive_or_aware: dt.datetime, tz_name: str) -> dt.datetime:
    """Interpret a datetime in the given IANA timezone and convert to UTC."""
    if naive_or_aware.tzinfo is not None:
        return naive_or_aware.astimezone(dt.timezone.utc)
    tz = pytz.timezone(tz_name)
    return tz.localize(naive_or_aware).astimezone(dt.timezone.utc)


def planet_position(jd_ut: float, planet_id: int) -> tuple[float, float]:
    """Return (longitude_deg, speed_deg_per_day)."""
    pos, _ = swe.calc_ut(jd_ut, planet_id, FLAGS)
    return norm360(pos[0]), pos[3]


def all_planet_positions(jd_ut: float) -> dict[str, tuple[float, float]]:
    """Longitudes and speeds for Sun..Pluto plus the lunar nodes."""
    out: dict[str, tuple[float, float]] = {}
    for name, pid in PLANETS:
        out[name] = planet_position(jd_ut, pid)
    lon, speed = planet_position(jd_ut, NODE)
    out["north_node"] = (lon, speed)
    out["south_node"] = (norm360(lon + 180.0), speed)
    return out


def houses_and_angles(
    jd_ut: float, lat: float, lon: float, house_system: str
) -> tuple[list[float], float, float]:
    """Return (cusps_deg[12], asc_deg, mc_deg)."""
    cusps, ascmc = swe.houses(jd_ut, lat, lon, HOUSE_SYSTEM_CODES[house_system])
    return [norm360(c) for c in cusps[:12]], norm360(ascmc[0]), norm360(ascmc[1])


def house_of(longitude: float, cusps: list[float]) -> int:
    """House number (1..12) of a longitude given 12 cusps in zodiacal order."""
    lon = norm360(longitude)
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        span = norm360(end - start)
        if norm360(lon - start) < span:
            return i + 1
    return 12


def aspects_between(
    positions: dict[str, float], orb_scale: float = 1.0
) -> list[dict]:
    """Major aspects among the given points, sorted deterministically."""
    names = list(positions.keys())
    found: list[dict] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            sep = angle_diff(positions[a], positions[b])
            for asp_name, asp_deg, max_orb in MAJOR_ASPECTS:
                orb = abs(sep - asp_deg)
                if orb <= max_orb * orb_scale:
                    found.append(
                        {
                            "point_a": a,
                            "point_b": b,
                            "aspect": asp_name,
                            "orb_deg": round(orb, ROUND_DEG),
                        }
                    )
                    break
    found.sort(key=lambda x: (x["point_a"], x["point_b"], x["aspect"]))
    return found


def planet_payload(
    positions: dict[str, tuple[float, float]], cusps: list[float]
) -> list[dict]:
    out = []
    for name, (lon, speed) in positions.items():
        out.append(
            {
                "name": name,
                "longitude_deg": round(lon, ROUND_DEG),
                "sign": sign_of(lon),
                "house": house_of(lon, cusps),
                "speed_deg_per_day": round(speed, ROUND_DEG),
            }
        )
    return out
