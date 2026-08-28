"""Pydantic request/response models. All JSON keys are snake_case."""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

HouseSystem = Literal["whole_sign", "placidus"]


class Place(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str


class NatalRequest(BaseModel):
    birth_datetime: dt.datetime
    place: Place
    house_system: HouseSystem = "whole_sign"


class DerivedChartRequest(NatalRequest):
    target_date: dt.date


class CandidateWindow(BaseModel):
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    step_minutes: int = Field(default=4, ge=1, le=60)


EventType = Literal[
    "marriage",
    "relocation",
    "death_of_close",
    "career_break",
    "child_birth",
    "accident",
    "surgery",
    "other",
]


class RectificationEvent(BaseModel):
    id: str
    date: dt.date
    date_precision: Literal["day", "month", "year"] = "day"
    type: EventType = "other"
    weight: float = 1.0


# Four techniques, not eight. Quadrant cusps, directed angles, primary
# directions, eclipse-on-angle and event-to-technique matching were built,
# measured and reverted: none improved the held-out in-block error, and two
# roughly doubled it. See benchmarks/RESULTS_SUBSIGN.md for the ablation and
# benchmarks/harness/candidate_engine.py for the frozen experiment.
Technique = Literal[
    "transits_to_angles",
    "secondary_progressions",
    "solar_arc",
    "profections",
]

ZODIAC_SIGNS = Literal[
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]


class RectificationConfig(BaseModel):
    house_system: HouseSystem = "whole_sign"
    techniques: list[Technique] = [
        "transits_to_angles",
        "secondary_progressions",
        "solar_arc",
        "profections",
    ]
    orbs: dict[str, float] = {
        "transits_to_angles": 1.0,
        "secondary_progressions": 1.0,
        "solar_arc": 1.0,
    }
    technique_weights: dict[str, float] = {
        "transits_to_angles": 1.0,
        "secondary_progressions": 1.2,
        "solar_arc": 0.8,
        "profections": 0.6,
    }
    precision_weights: dict[str, float] = {"day": 1.0, "month": 0.5, "year": 0.25}
    plateau_ratio: float = Field(default=0.9, gt=0, le=1)

    # Permutation null: shuffle event dates within the subject's own span,
    # rescore, and report where the real peak sits in that distribution.
    # 0 disables it.
    permutation_trials: int = Field(default=12, ge=0, le=200)

    # Below this permutation percentile the engine refuses to name a time.
    refusal_percentile: float = Field(default=0.90, ge=0, le=1)
    # ...and it also refuses when the top candidates are not separable.
    refusal_min_separation: float = Field(default=0.05, ge=0, le=1)


class RectificationRequest(BaseModel):
    birth_date: dt.date
    place: Place
    candidate_window: CandidateWindow
    events: list[RectificationEvent]
    config: RectificationConfig = RectificationConfig()
    # Stage 1 narrows the birth time to a rising sign. Candidates outside it
    # are marked excluded rather than dropped, so the density curve stays a
    # complete picture of the window.
    ascendant_sign: Optional[ZODIAC_SIGNS] = None
