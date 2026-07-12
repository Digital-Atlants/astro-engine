# astro-engine

Deterministic astrology computation service: natal charts, secondary
progressions, solar arc directions, annual profections, and birth-time
rectification scoring.

- **License:** [AGPL-3.0](LICENSE). If you run a modified version of this
  service over a network, the AGPL requires you to offer its source to users.
- **Ephemeris:** planetary positions are computed with
  [pyswisseph](https://github.com/astrorigin/pyswisseph), the Python binding
  for the **Swiss Ephemeris** by Astrodienst AG (Zürich). This project uses
  the built-in Moshier ephemeris (no data files required). Swiss Ephemeris is
  used under its AGPL license option; credit: © Astrodienst AG.

## Running

```bash
pip install -r requirements.txt
SERVICE_API_KEY=your-key uvicorn astro_engine.main:app --port 8000
```

Or with Docker / Railway: the included `Dockerfile` and `railway.toml` deploy
as-is; set the `SERVICE_API_KEY` environment variable.

## Authentication

All endpoints except `GET /health` require:

```
Authorization: Bearer <SERVICE_API_KEY>
```

Missing or wrong token → `401`.

## Determinism

Identical requests produce byte-identical JSON (stable key ordering, fixed
float rounding). The only exception is `compute_ms` in the rectification
response, which is wall-clock telemetry.

## API

All JSON keys are `snake_case`. Angles are ecliptic longitudes in degrees
(0–360). `place.tz` is an IANA timezone name; naive `birth_datetime` values
are interpreted in that timezone.

### `POST /v1/charts/natal`

Request:

```json
{
  "birth_datetime": "1990-05-15T10:30:00",
  "place": {"lat": 52.5, "lon": 13.4, "tz": "Europe/Berlin"},
  "house_system": "whole_sign"
}
```

`house_system`: `"whole_sign"` or `"placidus"`.

Response (contract for downstream report generation):

```json
{
  "planets": [
    {"name": "sun", "longitude_deg": 54.123456, "sign": "taurus",
     "house": 10, "speed_deg_per_day": 0.958765}
  ],
  "asc_deg": 123.456789,
  "mc_deg": 33.21,
  "cusps_deg": [120.0, 150.0, ...],
  "aspects": [
    {"point_a": "moon", "point_b": "sun", "aspect": "trine", "orb_deg": 2.1}
  ]
}
```

`planets` contains Sun through Pluto plus `north_node` and `south_node`
(true node). `aspects` covers major aspects (conjunction, sextile, square,
trine, opposition) among planets, nodes, Asc and MC.

### `POST /v1/charts/progressions`

Secondary progressions (day-for-a-year). Natal request shape plus
`"target_date": "YYYY-MM-DD"`.

Response: `{"progressed_planets": [...same planet shape...],
"progressed_asc_deg": float, "progressed_mc_deg": float, "cusps_deg": [12]}`

### `POST /v1/charts/directions`

Solar arc directions. Same request shape as progressions.

Response: `{"solar_arc_deg": float, "directed_points":
[{"name": "sun", "longitude_deg": float}, ...]}` — includes directed
`asc` and `mc`.

### `POST /v1/charts/profections`

Annual profections. Same request shape as progressions.

Response: `{"profection_year": int, "activated_house": int,
"activated_sign": str, "year_lord": str}`

### `POST /v1/rectification/score`

Scores each candidate birth time in a window against dated life events using
transits to angles, secondary progressions, solar arc, and annual profections.
See the request/response examples in
[`tests/test_rectification.py`](tests/test_rectification.py) and the schema in
[`astro_engine/schemas.py`](astro_engine/schemas.py).

Key response fields:

- `candidates[]` — one entry per candidate time with `total_score` and the
  contributing `hits` (`event_id`, `technique`, `factor`, `orb_deg`, `score`).
- `suggested_best` — best time, its score, and `residual_window_minutes`:
  the width of the contiguous candidate span whose scores stay within
  `config.plateau_ratio` of the best score.
- `config_echo`, `compute_ms`.

Date precision per event: `day` (full weight), `month` (evaluated mid-month,
doubled orbs, slow factors only), `year` (slow techniques only — profections,
solar arc, Saturn-and-slower transits).

Performance: positions per event date are candidate-independent and computed
once; only Asc/MC/cusps (and the progressed Moon) are computed per candidate.
360 candidates × 8 events completes in well under 10 s.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
