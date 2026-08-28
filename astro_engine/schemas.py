"""Pydantic request/response models. All JSON keys are snake_case."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

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

    # Below this width the engine stops trusting its own ordering and returns
    # the midpoint of the surviving interval instead of the score argmax.
    # Measured: once the candidate set is this narrow the argmax is
    # anti-correlated with the truth (AUC 0.422 all / 0.420 holdout) and loses
    # to a blind pick 20 times against 13. The default is 26 minutes, which is
    # where the engine's measured usefulness ends. Set 0 to disable.
    # See benchmarks/RESULTS_SUBSIGN.md.
    midpoint_below_minutes: int = Field(default=26, ge=0, le=1440)

    # Below this permutation percentile the engine refuses to name a time.
    refusal_percentile: float = Field(default=0.90, ge=0, le=1)
    # ...and it also refuses when the top candidates are not separable.
    refusal_min_separation: float = Field(default=0.05, ge=0, le=1)


InterviewChannel = Literal["rising_sign", "decan", "mover_house", "portrait"]

# Answer ids are enumerated tokens emitted by the engine and echoed back. The
# pattern is deliberately narrow: the calling client phrases questions and maps
# free text onto these ids, and it must not be able to smuggle a number, a time
# or a window through this field. Every numeric decision belongs to the engine.
ANSWER_ID = r"^[a-z0-9_]{1,32}$"


class InterviewAnswer(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(pattern=r"^[a-z0-9_]{1,48}$")
    channel: InterviewChannel
    subject: Optional[str] = Field(default=None, pattern=r"^[a-z_]{1,16}$")
    # Empty means `cannot_choose`: it multiplies no weights at all.
    answer_ids: list[str] = Field(default_factory=list, max_length=4)
    # Echoed back for the portrait channel so the partition can be rebuilt.
    windows: list[list[int]] = Field(default_factory=list, max_length=4)

    @field_validator("answer_ids")
    @classmethod
    def _ids_are_enum_tokens(cls, v: list[str]) -> list[str]:
        for item in v:
            if not re.match(ANSWER_ID, item):
                raise ValueError(
                    f"answer id {item!r} is not an enumerated token; the engine "
                    "makes every numeric decision, clients only echo ids"
                )
        return v


class InterviewConfigModel(BaseModel):
    model_config = {"extra": "forbid"}

    channel_reliability: float = Field(default=0.75, gt=0, lt=1)
    tier1_mass: float = Field(default=0.60, gt=0, le=1)
    tier2_mass: float = Field(default=0.60, gt=0, le=1)
    tier1_chance_p: float = Field(default=0.002, gt=0, le=1)
    tier2_chance_p: float = Field(default=0.20, gt=0, le=1)
    tier1_window_minutes: int = Field(default=30, ge=1, le=1440)
    min_information_bits: float = Field(default=0.15, ge=0, le=8)
    max_mover_questions: int = Field(default=3, ge=0, le=10)
    house_system: HouseSystem = "placidus"


class InterviewRequest(BaseModel):
    model_config = {"extra": "forbid"}

    birth_date: dt.date
    place: Place
    answers: list[InterviewAnswer] = Field(default_factory=list, max_length=24)
    config: InterviewConfigModel = InterviewConfigModel()


class InterviewCompareRequest(BaseModel):
    """Calibration mode: the documented time arrives only here, never during
    the interview. See `docs` in main.py for the contract."""

    model_config = {"extra": "forbid"}

    birth_date: dt.date
    place: Place
    answers: list[InterviewAnswer] = Field(default_factory=list, max_length=24)
    config: InterviewConfigModel = InterviewConfigModel()
    documented_time: str = Field(pattern=r"^\d{2}:\d{2}$")


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
