"""FastAPI application: bearer-authenticated astrology endpoints."""

from __future__ import annotations

import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import __version__, charts, rectification
from .schemas import DerivedChartRequest, NatalRequest, RectificationRequest

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
