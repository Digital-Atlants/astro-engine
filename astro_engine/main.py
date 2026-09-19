"""FastAPI application: bearer-authenticated astrology endpoints."""

from __future__ import annotations

import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import __version__, build_info, charts, interview, rectification
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
    """Liveness plus the build identity a client needs to refuse mismatches.

    `git_sha` is the commit this process was built from; `interview_contract`
    lists the field names `InterviewAnswer` accepts. A client that does not
    recognise the contract should decline to run the interview rather than
    send answers against an engine that will read them differently.
    """
    return {
        "status": "ok",
        "version": __version__,
        "git_sha": build_info.git_sha(),
        "interview_contract": {
            "answer_fields": build_info.interview_answer_fields(),
        },
    }


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
        known_bounds=req.known_bounds.model_dump() if req.known_bounds else None,
        claimed_time=req.claimed_time,
        sphere_inventory={k: v.model_dump() for k, v in req.sphere_inventory.items()},
        hypothesis=req.hypothesis.model_dump() if req.hypothesis else None,
        trait_tags=list(req.trait_tags),
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

    Since v3.5 it also returns a **per-answer agreement record**: for each
    replayed answer, whether the documented minute was inside the region that
    answer supported. That is what makes a channel which is systematically
    misleading findable without reading anybody's answers. It also scores
    every tier - `abs_error_minutes` is null when no window was named, so
    Tier 4 sessions used to produce no measurement at all, and
    `abs_error_minutes_working` is always present.

    `trait_tags` is accepted here because a session that cannot be replayed
    would be scored against a different posterior than the one the person saw.
    """
    result, posterior, trace, grid = interview._run_interview_internal(
        req.birth_date,
        req.place.lat,
        req.place.lon,
        req.place.tz,
        [a.model_dump() for a in req.answers],
        _interview_config(req.config),
        known_bounds=req.known_bounds.model_dump() if req.known_bounds else None,
        claimed_time=req.claimed_time,
        sphere_inventory={k: v.model_dump() for k, v in req.sphere_inventory.items()},
        trait_tags=list(req.trait_tags),
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
            **interview.compare_record(result, posterior, trace, grid, documented),
        }
    )


def _window_contains(window: dict, minute: int) -> bool:
    sh, sm = map(int, window["start"].split(":"))
    eh, em = map(int, window["end"].split(":"))
    start, end = sh * 60 + sm, eh * 60 + em
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end  # wraps midnight
