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


InterviewChannel = Literal[
    "element", "modality", "sign_portrait", "trait", "rising_sign",
    "decan", "mover_house", "portrait",
]

# Answer ids are enumerated tokens emitted by the engine and echoed back. The
# pattern is deliberately narrow: the calling client phrases questions and maps
# free text onto these ids, and it must not be able to smuggle a number, a time
# or a window through this field. Every numeric decision belongs to the engine.
ANSWER_ID = r"^[a-z0-9_]{1,32}$"


AnswerSource = Literal[
    "document", "observed", "client_report", "free_text_confirmed", "inferred"
]
HouseStatus = Literal["dominant", "present", "absent", "unknown"]


class InterviewAnswer(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(pattern=r"^[a-z0-9_]{1,48}$")
    channel: InterviewChannel
    subject: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]{1,16}$")
    # Which phrasing of the pair this answers. Two answers to the same
    # (channel, subject) are one question asked twice.
    variant: Literal["a", "b"] = "a"
    # Where the answer came from. Trust is set per source; `client_report`
    # uses the reliability estimated for this session from pair agreement.
    source: AnswerSource = "client_report"
    # Empty means `cannot_choose`: it multiplies no weights at all.
    answer_ids: list[str] = Field(default_factory=list, max_length=4)
    # Echoed back for the portrait channel so the partition can be rebuilt.
    windows: list[list[int]] = Field(default_factory=list, max_length=4)
    # Echoed back for trait questions so a repeat phrasing can offer the same
    # tags, and so an unticked tag is distinguishable from one never offered.
    offered_tag_ids: list[str] = Field(default_factory=list, max_length=4)

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


class TimeBounds(BaseModel):
    model_config = {"extra": "forbid"}

    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


class SphereEntry(BaseModel):
    model_config = {"extra": "forbid"}

    status: HouseStatus = "unknown"
    source: AnswerSource = "client_report"


class Hypothesis(BaseModel):
    """An astrologer's own time or range. Never enters the posterior."""

    model_config = {"extra": "forbid"}

    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")


class InterviewConfigModel(BaseModel):
    model_config = {"extra": "forbid"}

    # 0.60, not a fitted value: see docs/trust_default.md.
    channel_reliability: float = Field(default=0.60, gt=0, lt=1)
    repeat: bool = True
    repeat_pairs: int = Field(default=2, ge=0, le=6)
    disagreement_penalty: float = Field(default=0.15, ge=0, le=0.5)
    min_session_reliability: float = Field(default=0.30, gt=0, lt=1)
    tier1_min_agreeing_pairs: int = Field(default=2, ge=0, le=6)
    tier2_min_agreeing_pairs: int = Field(default=1, ge=0, le=6)
    claimed_time_weight: float = Field(default=0.5, ge=0, le=5)
    mode: Literal["standard", "professional"] = "standard"
    max_trait_questions: int = Field(default=4, ge=0, le=8)
    max_tags_per_question: int = Field(default=4, ge=2, le=4)
    sign_mass_stop: float = Field(default=0.45, gt=0, le=1)
    # There is no Tier 3: a rising sign is never delivered on its own. v3.3
    # made the tier reachable and measured it handing the adjacent sign to an
    # adjacent-sign answerer 38.5% of the time, so the spec's pre-registered
    # fallback was taken. Kept as an accepted field so a v3.2-era client is
    # not rejected; it decides nothing.
    tier3_sign_mass: float = Field(default=0.50, gt=0, le=1)
    portrait_sign_threshold: float = Field(default=0.70, gt=0, le=1)
    # Below the sign channels by design: a decan rises in 18-57 minutes at 51
    # degrees latitude and a self-report of appearance cannot resolve that.
    # See docs/trust_default.md.
    decan_reliability: float = Field(default=0.50, gt=0, lt=1)
    # Sun-sign self-attribution detector (van Rooij 1994). On by default
    # since v3.3.1: under the shipped tier ladder it costs the perfect
    # answerer nothing, and an answerer who describes itself by its Sun sign
    # is otherwise the second-largest source of confident wrong answers.
    sun_sign_detector: bool = True
    min_trait_bits: float = Field(default=0.01, ge=0, le=4)
    tier1_mass: float = Field(default=0.60, gt=0, le=1)
    tier2_mass: float = Field(default=0.60, gt=0, le=1)
    tier1_chance_p: float = Field(default=0.002, gt=0, le=1)
    tier2_chance_p: float = Field(default=0.20, gt=0, le=1)
    tier1_window_minutes: int = Field(default=30, ge=1, le=1440)
    # Tier 2's admission limits, explicit since v3.4 so the shortlist's width
    # can be traded against its accuracy without moving Tier 1. 50 is the
    # v3.4 retune; `tier2_max_windows` is inert at every measured value.
    tier2_window_minutes: int = Field(default=50, ge=1, le=1440)
    tier2_max_windows: int = Field(default=3, ge=1, le=4)
    min_information_bits: float = Field(default=0.15, ge=0, le=8)
    max_mover_questions: int = Field(default=3, ge=0, le=10)
    house_system: HouseSystem = "placidus"


class InterviewRequest(BaseModel):
    model_config = {"extra": "forbid"}

    birth_date: dt.date
    place: Place
    answers: list[InterviewAnswer] = Field(default_factory=list, max_length=32)
    config: InterviewConfigModel = InterviewConfigModel()
    # Documentary bounds on the birth time. Candidates outside are multiplied
    # by 0.02, never zero: a certificate can be misread or mistranscribed.
    known_bounds: Optional[TimeBounds] = None
    # A remembered or claimed approximate time. A soft prior only - the
    # owner's own confidently held time was 18 minutes out.
    claimed_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    # Pre-answers for mover-house questions, keyed by house number "1".."12".
    sphere_inventory: dict[str, SphereEntry] = Field(default_factory=dict)
    # Reported against the result, never mixed into it.
    hypothesis: Optional[Hypothesis] = None
    # Trait tags the client extracted from the person's own words and the
    # person confirmed on screen. The engine never sees free text: the mapping
    # from words to tags is the client's, and it exists only because the
    # person agreed with it. Unknown tag ids are rejected.
    trait_tags: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("trait_tags")
    @classmethod
    def _tags_are_known(cls, v: list[str]) -> list[str]:
        from .interview import TRAIT_TAGS

        for tag in v:
            if tag not in TRAIT_TAGS:
                raise ValueError(f"unknown trait tag {tag!r}")
        return v


class InterviewCompareRequest(BaseModel):
    """Calibration mode: the documented time arrives only here, never during
    the interview. See `docs` in main.py for the contract."""

    model_config = {"extra": "forbid"}

    birth_date: dt.date
    place: Place
    answers: list[InterviewAnswer] = Field(default_factory=list, max_length=32)
    config: InterviewConfigModel = InterviewConfigModel()
    known_bounds: Optional[TimeBounds] = None
    claimed_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    sphere_inventory: dict[str, SphereEntry] = Field(default_factory=dict)
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
