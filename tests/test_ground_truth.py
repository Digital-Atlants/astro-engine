"""Ground-truth checks against hand-verified reference values.

Solar and lunar longitudes come from worked examples in Meeus,
"Astronomical Algorithms" (2nd ed., examples 25.b and 47.a); tolerance
0.1 deg absorbs the UT/TT difference and Moshier vs. VSOP differences.
"""

import datetime as dt

import swisseph as swe

from astro_engine import charts, core
from astro_engine.schemas import DerivedChartRequest, NatalRequest, Place

BERLIN = Place(lat=52.5, lon=13.4, tz="Europe/Berlin")


def test_sun_longitude_meeus_25b():
    # 1992-10-13 00:00 TT -> apparent solar longitude 199.90605 deg.
    jd = core.to_julian_day(dt.datetime(1992, 10, 13, 0, 0))
    lon, _ = core.planet_position(jd, swe.SUN)
    assert abs(lon - 199.906) < 0.1


def test_moon_longitude_meeus_47a():
    # 1992-04-12 00:00 TT -> geocentric lunar longitude 133.162655 deg.
    jd = core.to_julian_day(dt.datetime(1992, 4, 12, 0, 0))
    lon, _ = core.planet_position(jd, swe.MOON)
    assert abs(lon - 133.163) < 0.1


def test_sun_sign_and_speed():
    # Northern summer solstice 2000: Sun at 0 deg Cancer, ~0.95 deg/day.
    jd = core.to_julian_day(dt.datetime(2000, 6, 21, 1, 48))
    lon, speed = core.planet_position(jd, swe.SUN)
    assert abs(lon - 90.0) < 0.1
    assert 0.94 < speed < 0.99


def test_whole_sign_cusps_start_at_sign_boundaries():
    req = NatalRequest(
        birth_datetime=dt.datetime(1990, 5, 15, 10, 30),
        place=BERLIN,
        house_system="whole_sign",
    )
    chart = charts.natal_chart(req)
    for cusp in chart["cusps_deg"]:
        assert abs(cusp % 30.0) < 1e-6
    # Asc must sit inside the first whole-sign house.
    assert chart["cusps_deg"][0] <= chart["asc_deg"] < chart["cusps_deg"][0] + 30.0


def test_profection_exact():
    req = DerivedChartRequest(
        birth_datetime=dt.datetime(1990, 1, 10, 8, 0),
        place=BERLIN,
        target_date=dt.date(2020, 6, 1),
    )
    prof = charts.profections(req)
    # Age 30 -> 30 % 12 = 6 -> 7th house year.
    assert prof["profection_year"] == 30
    assert prof["activated_house"] == 7
    assert prof["year_lord"] == core.SIGN_RULERS[prof["activated_sign"]]


def test_solar_arc_roughly_one_degree_per_year():
    req = DerivedChartRequest(
        birth_datetime=dt.datetime(1990, 1, 10, 8, 0),
        place=BERLIN,
        target_date=dt.date(2020, 1, 10),
    )
    result = charts.solar_arc(req)
    assert 28.0 < result["solar_arc_deg"] < 32.0
    names = {p["name"] for p in result["directed_points"]}
    assert {"asc", "mc", "sun", "moon"} <= names


def test_progressions_shape(client, auth_headers):
    resp = client.post(
        "/v1/charts/progressions",
        json={
            "birth_datetime": "1990-01-10T08:00:00",
            "place": {"lat": 52.5, "lon": 13.4, "tz": "Europe/Berlin"},
            "house_system": "placidus",
            "target_date": "2020-01-10",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cusps_deg"]) == 12
    assert len(body["progressed_planets"]) == 12
    # ~30 elapsed years: progressed Sun ~30 deg past natal Sun (289.6 -> ~320).
    sun = next(p for p in body["progressed_planets"] if p["name"] == "sun")
    assert abs(sun["longitude_deg"] - 319.7) < 1.0
