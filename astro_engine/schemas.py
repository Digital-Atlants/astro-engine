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


class RectificationConfig(BaseModel):
    house_system: HouseSystem = "whole_sign"
    techniques: list[
        Literal[
            "transits_to_angles",
            "secondary_progressions",
            "solar_arc",
            "profections",
        ]
    ] = [
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


class RectificationRequest(BaseModel):
    birth_date: dt.date
    place: Place
    candidate_window: CandidateWindow
    events: list[RectificationEvent]
    config: RectificationConfig = RectificationConfig()
