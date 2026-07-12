"""Determinism, snake_case, and auth contract tests."""

import re

NATAL_BODY = {
    "birth_datetime": "1985-03-21T04:15:00",
    "place": {"lat": 48.85, "lon": 2.35, "tz": "Europe/Paris"},
    "house_system": "placidus",
}

RECT_BODY = {
    "birth_date": "1985-03-21",
    "place": {"lat": 48.85, "lon": 2.35, "tz": "Europe/Paris"},
    "candidate_window": {"start_time": "03:00", "end_time": "06:00", "step_minutes": 10},
    "events": [
        {"id": "e1", "date": "2015-06-20", "date_precision": "day", "type": "marriage", "weight": 1.0},
        {"id": "e2", "date": "2018-03-01", "date_precision": "month", "type": "career_break", "weight": 1.0},
    ],
    "config": {"house_system": "whole_sign"},
}

SNAKE = re.compile(r"^[a-z0-9_]+$")


def _assert_snake(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert SNAKE.match(k), f"non-snake_case key: {k}"
            _assert_snake(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_snake(item)


def test_determinism_natal(client, auth_headers):
    r1 = client.post("/v1/charts/natal", json=NATAL_BODY, headers=auth_headers)
    r2 = client.post("/v1/charts/natal", json=NATAL_BODY, headers=auth_headers)
    assert r1.status_code == 200
    assert r1.content == r2.content


def test_determinism_rectification(client, auth_headers):
    r1 = client.post("/v1/rectification/score", json=RECT_BODY, headers=auth_headers)
    r2 = client.post("/v1/rectification/score", json=RECT_BODY, headers=auth_headers)
    assert r1.status_code == 200
    b1, b2 = r1.json(), r2.json()
    # compute_ms is wall-clock telemetry, excluded from the determinism contract.
    b1.pop("compute_ms")
    b2.pop("compute_ms")
    assert b1 == b2


def test_snake_case_keys(client, auth_headers):
    for path, body in [
        ("/v1/charts/natal", NATAL_BODY),
        ("/v1/charts/progressions", {**NATAL_BODY, "target_date": "2020-01-01"}),
        ("/v1/charts/directions", {**NATAL_BODY, "target_date": "2020-01-01"}),
        ("/v1/charts/profections", {**NATAL_BODY, "target_date": "2020-01-01"}),
        ("/v1/rectification/score", RECT_BODY),
    ]:
        resp = client.post(path, json=body, headers=auth_headers)
        assert resp.status_code == 200, path
        _assert_snake(resp.json())


def test_auth_required_everywhere_except_health(client):
    assert client.get("/health").status_code == 200
    for path, body in [
        ("/v1/charts/natal", NATAL_BODY),
        ("/v1/charts/progressions", {**NATAL_BODY, "target_date": "2020-01-01"}),
        ("/v1/charts/directions", {**NATAL_BODY, "target_date": "2020-01-01"}),
        ("/v1/charts/profections", {**NATAL_BODY, "target_date": "2020-01-01"}),
        ("/v1/rectification/score", RECT_BODY),
    ]:
        assert client.post(path, json=body).status_code == 401, path
        bad = {"Authorization": "Bearer wrong-key"}
        assert client.post(path, json=body, headers=bad).status_code == 401, path
