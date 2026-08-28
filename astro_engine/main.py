"""FastAPI application: bearer-authenticated astrology endpoints."""

from __future__ import annotations

import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import __version__, charts, interview, rectification
from .schemas import (
    DerivedChartRequest,
    InterviewCompareRequest,
    InterviewRequest,
    NatalRequest,
    RectificationRequest,
)

app = FastAPI(
    title="astro-engine",
    version=__version__,
    description="Deterministic astrology computation service (AGPL-3.0).",
)


def require_bearer(request: Request) -> None:
    expected = os.environ.get("SERVICE_API_KEY", "")
    header = request.headers.get("authorization", "")
    if not expected or header != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/v1/charts/natal", dependencies=[Depends(require_bearer)])
def natal(req: NatalRequest) -> JSONResponse:
    return JSONResponse(charts.natal_chart(req))


@app.post("/v1/charts/progressions", dependencies=[Depends(require_bearer)])
def progressions(req: DerivedChartRequest) -> JSONResponse:
    return JSONResponse(charts.progressions(req))


@app.post("/v1/charts/directions", dependencies=[Depends(require_bearer)])
def directions(req: DerivedChartRequest) -> JSONResponse:
    return JSONResponse(charts.solar_arc(req))


@app.post("/v1/charts/profections", dependencies=[Depends(require_bearer)])
def profections(req: DerivedChartRequest) -> JSONResponse:
    return JSONResponse(charts.profections(req))


@app.post("/v1/rectification/score", dependencies=[Depends(require_bearer)])
def rectification_score(req: RectificationRequest) -> JSONResponse:
    t0 = time.perf_counter()
    result = rectification.score_rectification(req)
    result["compute_ms"] = int((time.perf_counter() - t0) * 1000)
    return JSONResponse(result)


def _interview_config(model) -> interview.InterviewConfig:
    return interview.InterviewConfig(**model.model_dump())


@app.post("/v1/interview/step", dependencies=[Depends(require_bearer)])
def interview_step(req: InterviewRequest) -> JSONResponse:
    """One stateless interview step.

    The caller replays every answer so far and receives the posterior summary,
    the next question specification, the tier and the stated window. Answers
    are enumerated ids emitted by this engine; the schema rejects anything
    else, so a calling model can phrase a question but cannot make a numeric
    decision.
    """
    t0 = time.perf_counter()
    result = interview.run_interview(
        req.birth_date,
        req.place.lat,
        req.place.lon,
        req.place.tz,
        [a.model_dump() for a in req.answers],
        _interview_config(req.config),
    )
    result["compute_ms"] = int((time.perf_counter() - t0) * 1000)
    result["telemetry"]["compute_ms"] = result["compute_ms"]
    return JSONResponse(result)


@app.post("/v1/interview/compare", dependencies=[Depends(require_bearer)])
def interview_compare(req: InterviewCompareRequest) -> JSONResponse:
    """Calibration mode: score a finished interview against a documented time.

    The contract this endpoint exists to enforce: a calibration session runs
    fully blind. `POST /v1/interview/step` has no field for a documented birth
    time and rejects unknown fields, so the time cannot reach the interview
    even by accident. It is submitted here, once, after the interview is over,
    and this endpoint returns the error in minutes together with the tier and
    coherence numbers.

    The response carries no answers, no candidate times and no documented
    time - only the PII-free telemetry record the service is allowed to keep.
    That is what makes a live labelled corpus accumulate without storing
    anything about the person.
    """
    result = interview.run_interview(
        req.birth_date,
        req.place.lat,
        req.place.lon,
        req.place.tz,
        [a.model_dump() for a in req.answers],
        _interview_config(req.config),
    )
    hh, mm = map(int, req.documented_time.split(":"))
    documented = hh * 60 + mm

    windows = result["windows"]
    err = None
    contains = None
    if windows:
        mid = windows[0]["midpoint"]
        mh, mmn = map(int, mid.split(":"))
        d = abs((mh * 60 + mmn) - documented) % interview.N_GRID
        err = min(d, interview.N_GRID - d)
        contains = any(_window_contains(w, documented) for w in windows)

    return JSONResponse(
        {
            "tier": result["tier"],
            "abs_error_minutes": err,
            "window_contains_documented": contains,
            "coherence": result["coherence"],
            "telemetry": result["telemetry"],
        }
    )


def _window_contains(window: dict, minute: int) -> bool:
    sh, sm = map(int, window["start"].split(":"))
    eh, em = map(int, window["end"].split(":"))
    start, end = sh * 60 + sm, eh * 60 + em
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end  # wraps midnight
