"""Deterministic interview core for birth-time rectification.

Stateless: the caller replays every answer given so far and receives the
posterior, the next question, the tier and the stated window. The same input
always produces the same output - there is no randomness and no model here.

Design constraints, each of which comes from a measurement rather than a
preference:

* **One-minute grid.** The 4-minute grid cost a corpus case outright
  (`jobs_steve`, whose true time fell between grid points and could not be
  reached by any answer). 1440 candidates is affordable.
* **Reweight, never filter.** Every answer multiplies candidate weights. A
  wrong answer degrades the truth's weight; it can never set it to zero, so no
  answer is unrecoverable. `cannot_choose` multiplies nothing at all. Even a
  documentary time bound only multiplies by `DOCUMENT_BOUND_FACTOR`, because a
  certificate can be misread.
* **Conservative trust.** The default channel reliability is 0.60, not a
  fitted value. See `docs/trust_default.md`.
* **Reliability is measured per session, not assumed.** Every key question is
  asked twice in different words. Two independent one-in-five errors coincide
  about one time in twenty-five, so agreement between the two phrasings is
  real evidence about *this* answerer; disagreement voids the question and
  lowers the trust applied to everything else they said.
* **Every numeric decision lives here.** The calling client's only job is to
  phrase a question and map free text onto one of the enumerated answer ids
  this module emits. Answers are enum ids and nothing else; anything else is
  rejected by the schema. This project has twice been burned by a host model
  quietly making a numeric decision, and the contract is shaped so that it
  cannot happen again.
* **Windows, never bare times.** A Tier 1 or Tier 2 answer always carries its
  bounds.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
from typing import Iterable

from . import core

GRID_STEP_MINUTES = 1
GRID_MINUTES = list(range(0, 24 * 60, GRID_STEP_MINUTES))
N_GRID = len(GRID_MINUTES)

# Planet longitudes are sampled hourly and linearly interpolated to the minute.
# The fastest body, the Moon, moves about 0.55 degrees per hour, so the
# interpolation error over a one-hour span is below a thousandth of a degree.
# House cusps are NOT interpolated: they move about a quarter degree per minute
# and are computed exactly at every candidate.
LONGITUDE_SAMPLE_MINUTES = 60

CHANNELS = ("element", "modality", "sign_portrait", "trait", "decan",
            "mover_house", "portrait")
DECAN_NAMES = ("first", "second", "third")

# The owner's rule, now a contract:
#   * a question never offers more than MAX_OPTIONS choices (+ cannot_choose);
#   * a question payload never contains a clock time or a span.
# Narrowing is the engine's job. Stage 1 arrived live as a 12-way choice
# rendered as twelve time spans, which asked the person to pick the very thing
# they came to find out. Sign blocks are an *output* and live in the result.
MAX_OPTIONS = 4
MAX_MOVER_OPTIONS = 3
MAX_PORTRAIT_OPTIONS = 3

_VOCAB_PATH = pathlib.Path(__file__).resolve().parent / "data" / "trait_vocabulary.json"
_VOCAB = json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))
TRAIT_TAGS = {t["tag_id"]: t for t in _VOCAB["tags"]}
TRAIT_SIGNS = _VOCAB["signs"]
_SIGN_AXIS = _VOCAB["sign_attributes"]
ELEMENT_TAGS = _VOCAB["structural_tags"]["element"]
MODALITY_TAGS = _VOCAB["structural_tags"]["modality"]
# The two-portrait confirmation never offers more than this many signs.
MAX_PORTRAIT_SIGNS = 2

# Stage 1 is these three questions in this order: the element axis, the
# modality axis, then a two-portrait confirmation between the leaders.
# Tier 3 delivers the sign these three agreed on, so all three are what
# its bar is written against.
STAGE1_CHANNELS = ("element", "modality", "sign_portrait")

# Two phrasings of the same underlying partition. The client renders them as
# different questions; the engine knows they are a pair.
VARIANTS = ("a", "b")
VARIANT_FACET = {
    "element": {"a": "temperament", "b": "drive"},
    "modality": {"a": "pace", "b": "approach"},
    "sign_portrait": {"a": "portrait", "b": "portrait_contrast"},
    "rising_sign": {"a": "temperament", "b": "build"},
    "decan": {"a": "manner", "b": "appearance"},
    "mover_house": {"a": "life_area", "b": "episode"},
    "portrait": {"a": "portrait", "b": "portrait_contrast"},
}

# A documentary bound is strong evidence, not proof: certificates are misread,
# transcribed wrongly and occasionally refer to the registration rather than
# the birth. Outside the bounds candidates are multiplied by this, never zero.
DOCUMENT_BOUND_FACTOR = 0.02

# Trust by where an answer came from. Frozen before the v2 harness ran.
SOURCE_TRUST = {
    "document": 0.90,
    "observed": 0.80,
    "client_report": None,  # means "use the session reliability"
    # Tags the client extracted from the person's own words and the person
    # then confirmed on screen. Slightly below a direct chip choice: the
    # person agreed with a reading of what they said, which is a weaker act
    # than picking the thing themselves.
    "free_text_confirmed": 0.55,
    "inferred": 0.50,
}

CLAIMED_TIME_KERNEL_MINUTES = 60


class InterviewConfig:
    """Frozen numeric policy. Defaults are the values the gates were run at."""

    __slots__ = (
        "channel_reliability",
        "tier1_mass",
        "tier2_mass",
        "tier1_chance_p",
        "tier2_chance_p",
        "tier1_window_minutes",
        "tier2_window_minutes",
        "tier2_max_windows",
        "min_information_bits",
        "max_mover_questions",
        "house_system",
        "repeat",
        "repeat_pairs",
        "disagreement_penalty",
        "min_session_reliability",
        "tier1_min_agreeing_pairs",
        "tier2_min_agreeing_pairs",
        "claimed_time_weight",
        "mode",
        "max_trait_questions",
        "max_tags_per_question",
        "sign_mass_stop",
        "min_trait_bits",
        "tier3_sign_mass",
        "portrait_sign_threshold",
        "decan_reliability",
        "sun_sign_detector",
    )

    def __init__(
        self,
        channel_reliability: float = 0.60,
        tier1_mass: float = 0.60,
        tier2_mass: float = 0.60,
        tier1_chance_p: float = 0.002,
        tier2_chance_p: float = 0.20,
        tier1_window_minutes: int = 30,
        # Tier 2's own admission limits, explicit since v3.4. They were
        # `tier1_window_minutes * 3` and a literal 3, which made the two
        # tiers' widths impossible to move independently - and Tier 2 is the
        # flagship now, so its width is the thing G7 and G9 trade against.
        #
        # 50 is the v3.4 retune, spent train-only over a frozen grid and
        # re-evaluated on holdout. It is the widest single window Tier 2 will
        # admit before refusing. Read the report before moving it: G7 improves
        # here by *issuing fewer shortlists*, not by issuing better ones - the
        # shortlists Tier 2 does issue already contain the truth 100% of the
        # time for a perfect answerer at every setting measured, including the
        # old 90.
        #
        # `tier2_max_windows` is inert at every value measured: Tier 2 never
        # produced three windows in 18 sweep cells, so 2 and 3 gave identical
        # numbers throughout. Kept explicit rather than removed, because the
        # code path is real and a future posterior could reach it.
        tier2_window_minutes: int = 50,
        tier2_max_windows: int = 3,
        min_information_bits: float = 0.15,
        max_mover_questions: int = 3,
        house_system: str = "placidus",
        repeat: bool = True,
        repeat_pairs: int = 3,
        disagreement_penalty: float = 0.15,
        min_session_reliability: float = 0.30,
        tier1_min_agreeing_pairs: int = 2,
        tier2_min_agreeing_pairs: int = 1,
        claimed_time_weight: float = 0.5,
        mode: str = "standard",
        max_trait_questions: int = 4,
        max_tags_per_question: int = 4,
        sign_mass_stop: float = 0.45,
        # Stage 1 has its own floor. A trait question's *expected* gain is
        # small by construction: the update is positive-only, so the large
        # "ticked nothing" branch contributes zero and dilutes the average,
        # even though the realised update when a tag is ticked is decisive.
        # Reusing the 0.15-bit partition floor here stopped stage 1 from ever
        # running. Frozen before measurement.
        min_trait_bits: float = 0.01,
        # Tier 3 delivers a rising sign and nothing else, so its bar is
        # about the sign and not about the time: every stage-1 pair agreed,
        # nothing disagreed anywhere, and one sign carries this much mass.
        #
        # v3.2 bolted a chance-agreement test and a >=2-pair count onto Tier 3
        # and made it *stricter* than Tier 2, which is tested first. Tier 3
        # then became unreachable - 0.0% of runs for six of seven answerer
        # models - and its wrong-sign gate was passing on an empty set. A sign
        # is a weaker claim than a 30-minute window and carries a looser bar.
        tier3_sign_mass: float = 0.50,
        # When the two-portrait confirmation fires. Measured as load-bearing
        # for G1: see the comment at the call site in `next_question`.
        portrait_sign_threshold: float = 0.70,
        # Trust for the decan channel, deliberately below the sign channels.
        # At 51 degrees latitude a decan rises in 18-57 minutes and a
        # self-report of appearance does not carry that precision. A design
        # constant, not a fitted one: see docs/trust_default.md.
        decan_reliability: float = 0.50,
        # Sun-sign self-attribution detector (van Rooij 1994). People who
        # know their Sun sign describe themselves by its stereotype; the
        # engine knows the Sun sign from the birth date and honest stage-1
        # answers land on it only about one time in twelve.
        #
        # **On by default since v3.3.1.** In v3.3 it defaulted off on a
        # pre-registered 3-point allowance, which it breached by costing the
        # perfect answerer 7.3 points of Tier 1. That measurement was taken
        # against the ladder v3.3 then abandoned. Under the shipped ladder -
        # no Tier 3, portrait threshold restored - it costs the perfect
        # answerer **nothing** (82.93% either way), because the discount only
        # bites when stage 1 is the session's sole source of agreeing pairs.
        # See benchmarks/RESULTS_INTERVIEW_v3_3_1.md.
        sun_sign_detector: bool = True,
    ):
        self.channel_reliability = channel_reliability
        self.tier1_mass = tier1_mass
        self.tier2_mass = tier2_mass
        self.tier1_chance_p = tier1_chance_p
        self.tier2_chance_p = tier2_chance_p
        self.tier1_window_minutes = tier1_window_minutes
        self.tier2_window_minutes = tier2_window_minutes
        self.tier2_max_windows = tier2_max_windows
        self.min_information_bits = min_information_bits
        self.max_mover_questions = max_mover_questions
        self.house_system = house_system
        self.repeat = repeat
        self.repeat_pairs = repeat_pairs
        self.disagreement_penalty = disagreement_penalty
        self.min_session_reliability = min_session_reliability
        self.tier1_min_agreeing_pairs = tier1_min_agreeing_pairs
        self.tier2_min_agreeing_pairs = tier2_min_agreeing_pairs
        self.claimed_time_weight = claimed_time_weight
        self.mode = mode
        self.max_trait_questions = max_trait_questions
        self.max_tags_per_question = max_tags_per_question
        self.sign_mass_stop = sign_mass_stop
        self.min_trait_bits = min_trait_bits
        self.tier3_sign_mass = tier3_sign_mass
        self.portrait_sign_threshold = portrait_sign_threshold
        self.decan_reliability = decan_reliability
        self.sun_sign_detector = sun_sign_detector


# --------------------------------------------------------------------------
# Chart geometry
# --------------------------------------------------------------------------


class ChartGrid:
    """Per-minute chart facts for one birth date and place."""

    def __init__(self, birth_date: dt.date, lat: float, lon: float, tz: str,
                 house_system: str = "placidus"):
        self.birth_date = birth_date
        self.lat, self.lon, self.tz = lat, lon, tz
        self.house_system = house_system

        self.jd = [self._jd(m) for m in GRID_MINUTES]
        self.asc: list[float] = []
        self.cusps: list[list[float]] = []
        for jd in self.jd:
            cusps, asc, _ = core.houses_and_angles(jd, lat, lon, house_system)
            self.asc.append(asc)
            self.cusps.append(cusps)

        self.asc_sign = [core.sign_of(a) for a in self.asc]
        self.asc_decan = [int((a % 30.0) // 10.0) for a in self.asc]

        lons = self._planet_longitudes()
        # The Sun moves about a degree a day, so its sign is a fact about the
        # date rather than the minute; noon is representative and the
        # self-attribution detector needs no more than that.
        self.sun_sign = core.sign_of(lons["sun"][N_GRID // 2])
        self.planet_house: dict[str, list[int]] = {}
        for name, _ in core.PLANETS:
            series = lons[name]
            self.planet_house[name] = [
                core.house_of(series[i], self.cusps[i]) for i in range(N_GRID)
            ]

    def _jd(self, minute: int) -> float:
        hh, mm = divmod(minute, 60)
        return core.to_julian_day(
            core.localize_to_utc(
                dt.datetime(
                    self.birth_date.year, self.birth_date.month,
                    self.birth_date.day, hh, mm,
                ),
                self.tz,
            )
        )

    def _planet_longitudes(self) -> dict[str, list[float]]:
        anchors = list(range(0, N_GRID, LONGITUDE_SAMPLE_MINUTES)) + [N_GRID - 1]
        out: dict[str, list[float]] = {}
        for name, pid in core.PLANETS:
            sampled = [core.planet_position(self.jd[i], pid)[0] for i in anchors]
            unwrapped = [sampled[0]]
            for v in sampled[1:]:
                prev = unwrapped[-1]
                while v - prev > 180.0:
                    v -= 360.0
                while prev - v > 180.0:
                    v += 360.0
                unwrapped.append(v)
            series = [0.0] * N_GRID
            for k in range(len(anchors) - 1):
                i0, i1 = anchors[k], anchors[k + 1]
                v0, v1 = unwrapped[k], unwrapped[k + 1]
                span = i1 - i0
                for i in range(i0, i1 + 1):
                    t = (i - i0) / span if span else 0.0
                    series[i] = core.norm360(v0 + (v1 - v0) * t)
            out[name] = series
        return out


# --------------------------------------------------------------------------
# Partitions
# --------------------------------------------------------------------------


def _partition_rising_sign(grid: ChartGrid) -> list[str]:
    return grid.asc_sign


def _partition_decan(grid: ChartGrid) -> list[str]:
    return [f"{grid.asc_sign[i]}_{DECAN_NAMES[grid.asc_decan[i]]}" for i in range(N_GRID)]


def _partition_mover(grid: ChartGrid, planet: str) -> list[str]:
    return [str(h) for h in grid.planet_house[planet]]


def partition_for(grid: ChartGrid, channel: str, subject: str | None,
                  windows: list[tuple[int, int]] | None = None) -> list[str]:
    if channel == "rising_sign":
        return _partition_rising_sign(grid)
    if channel == "decan":
        return _partition_decan(grid)
    if channel == "mover_house":
        return _partition_mover(grid, subject or "")
    if channel == "portrait":
        labels = ["none"] * N_GRID
        for idx, (lo, hi) in enumerate(windows or []):
            for i in range(lo, hi + 1):
                labels[i % N_GRID] = f"w{idx}"
        return labels
    raise ValueError(f"unknown channel {channel!r}")


def apply_answer(weights: list[float], labels: list[str], chosen: list[str],
                 reliability: float) -> list[float]:
    """Multiply weights by the likelihood of this answer.

    Standard likelihood for an answerer right with probability `reliability`
    and otherwise picking uniformly among the other classes, expressed as a
    ratio against the matching case. Matching candidates keep their weight;
    non-matching ones are multiplied by a strictly positive factor below one.
    Nothing ever reaches zero. An empty `chosen` multiplies nothing.
    """
    if not chosen:
        return list(weights)

    classes = set(labels)
    k = len(classes)
    picked = set(chosen) & classes
    others = k - len(picked)
    if not picked or others <= 0:
        return list(weights)

    r = min(max(reliability, 1e-6), 1.0 - 1e-6)
    factor = (1.0 - r) / (r * others)
    return [w if labels[i] in picked else w * factor for i, w in enumerate(weights)]


def apply_trait_answer(weights: list[float], asc_signs: list[str],
                       selected: list[str], trust: float) -> list[float]:
    """Reweight by the per-sign likelihood of every *selected* tag.

    Unselected tags do not penalise. A person who ticks two of four boxes has
    told us those two fit; not ticking the others is not a denial, it is
    silence, and treating it as a "no" would punish the honest answerer who
    only ticks what they are sure of.

    `trust` blends the likelihood toward 1, so a low-trust source moves the
    posterior less. The factor is never zero for any candidate.
    """
    if not selected:
        return list(weights)
    t = min(max(trust, 0.0), 1.0)
    factors = {}
    for sign in set(asc_signs):
        f = 1.0
        for tag_id in selected:
            tag = TRAIT_TAGS.get(tag_id)
            if tag:
                f *= (1.0 - t) + t * tag["likelihood"][sign]
        factors[sign] = f
    return [w * factors[asc_signs[i]] for i, w in enumerate(weights)]


def sign_mass(weights: list[float], asc_signs: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    total = sum(weights) or 1.0
    for i, w in enumerate(weights):
        out[asc_signs[i]] = out.get(asc_signs[i], 0.0) + w / total
    return out


def _trait_expected_gain(prior: dict[str, float], tag_ids: list[str],
                         trust: float) -> float:
    """Expected bits from asking about this tag set, under the actual update.

    Enumerates every subset the person could tick (at most 2**4). The subset
    probability uses the generative model - each tag is ticked with its own
    likelihood - while the posterior is formed with the *asymmetric* update
    the engine really applies. Measuring the gain we will actually realise,
    rather than the gain a symmetric update would have given, keeps the
    question chooser honest.
    """
    signs = [s for s, m in prior.items() if m > 0]
    if not signs:
        return 0.0
    before = _entropy_bits(prior)
    t = min(max(trust, 0.0), 1.0)
    expected = 0.0
    n = len(tag_ids)
    for mask in range(1 << n):
        picked = [tag_ids[i] for i in range(n) if mask & (1 << i)]
        unpicked = [tag_ids[i] for i in range(n) if not mask & (1 << i)]
        p_subset = 0.0
        post: dict[str, float] = {}
        for sign in signs:
            lik = 1.0
            for tag_id in picked:
                lik *= TRAIT_TAGS[tag_id]["likelihood"][sign]
            for tag_id in unpicked:
                lik *= 1.0 - TRAIT_TAGS[tag_id]["likelihood"][sign]
            joint = prior[sign] * lik
            p_subset += joint
            factor = 1.0
            for tag_id in picked:
                factor *= (1.0 - t) + t * TRAIT_TAGS[tag_id]["likelihood"][sign]
            post[sign] = prior[sign] * factor
        if p_subset <= 0:
            continue
        expected += p_subset * _entropy_bits(post)
    return max(0.0, before - expected)


def normalise(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return [1.0 / len(weights)] * len(weights)
    return [w / total for w in weights]


# --------------------------------------------------------------------------
# Pair combination and session reliability
# --------------------------------------------------------------------------


def pair_key(answer: dict) -> tuple:
    return (answer["channel"], answer.get("subject"))


def combine_pairs(answers: list[dict], cfg: InterviewConfig) -> dict:
    """Fold repeated phrasings into one observation each, and price the session.

    Two phrasings of the same partition are one question asked twice. If the
    person gives the same class both times, that is evidence about *them* - two
    independent one-in-five errors coincide about one time in twenty-five - and
    the answer is applied once at full trust. If they disagree, the question is
    void: it contributes nothing, and the trust applied to everything else they
    said drops, because we have just watched them be inconsistent.

    A `cannot_choose` on one phrasing is not a disagreement. Declining to
    answer must never cost more than the information that answer would have
    carried.
    """
    groups: dict[tuple, list[dict]] = {}
    for a in answers:
        groups.setdefault(pair_key(a), []).append(a)

    effective: list[dict] = []
    agreeing = disagreeing = incomplete = 0

    for key, group in groups.items():
        answered = [a for a in group if a.get("answer_ids")]
        if len(group) >= 2 and len(answered) >= 2:
            first, second = answered[0], answered[1]
            # Two observations agree when they are *consistent*, not when they
            # are textually identical. A paraphrase pair is single-select both
            # times, so consistency and equality coincide there. A source pair
            # need not: a sphere inventory answers with the set of houses it
            # has not ruled out, and the client picks one of them. Testing for
            # equality marked every such pair a disagreement - including for a
            # perfect answerer - and collapsed professional mode to Tier 3.
            #
            # The effective answer is the intersection: the conjunction of two
            # consistent observations is what both of them support.
            overlap = set(first["answer_ids"]) & set(second["answer_ids"])
            if overlap:
                agreeing += 1
                merged = dict(first)
                merged["answer_ids"] = sorted(overlap)
                merged["pair_state"] = "agree"
                effective.append(merged)
            else:
                disagreeing += 1
                voided = dict(first)
                voided["answer_ids"] = []
                voided["pair_state"] = "disagree"
                effective.append(voided)
        elif answered:
            single = dict(answered[0])
            single["pair_state"] = "single"
            incomplete += 1
            effective.append(single)
        else:
            blank = dict(group[0])
            blank["answer_ids"] = []
            blank["pair_state"] = "cannot_choose"
            effective.append(blank)

    session_r = max(
        cfg.min_session_reliability,
        cfg.channel_reliability - cfg.disagreement_penalty * disagreeing,
    )
    return {
        "effective": effective,
        "agreeing_pairs": agreeing,
        "disagreeing_pairs": disagreeing,
        "unpaired_answers": incomplete,
        "session_reliability": round(session_r, 6),
    }


def answer_reliability(answer: dict, session_r: float) -> float:
    """Trust for one answer: by source where the source is known, else the
    session estimate."""
    source = answer.get("source") or "client_report"
    fixed = SOURCE_TRUST.get(source)
    return session_r if fixed is None else fixed


# --------------------------------------------------------------------------
# Posterior
# --------------------------------------------------------------------------


def build_posterior(grid: ChartGrid, answers: Iterable[dict],
                    cfg: InterviewConfig, known_bounds: dict | None = None,
                    claimed_time: str | None = None):
    """Replay every answer over a uniform prior. Returns (posterior, trace, pairs)."""
    answers = list(answers)
    pairs = combine_pairs(answers, cfg)
    session_r = pairs["session_reliability"]

    weights = [1.0] * N_GRID

    if known_bounds:
        lo = _to_minute(known_bounds["start"])
        hi = _to_minute(known_bounds["end"])
        inside = _minutes_between(lo, hi)
        weights = [
            w if i in inside else w * DOCUMENT_BOUND_FACTOR
            for i, w in enumerate(weights)
        ]

    if claimed_time is not None:
        centre = _to_minute(claimed_time)
        kernel = []
        for i in range(N_GRID):
            d = abs(i - centre) % N_GRID
            d = min(d, N_GRID - d)
            kernel.append(1.0 if d <= CLAIMED_TIME_KERNEL_MINUTES else 0.0)
        # A soft prior at a fraction of the weight of a real answer.
        lift = cfg.claimed_time_weight
        weights = [w * (1.0 + lift * kernel[i]) for i, w in enumerate(weights)]

    trace = []
    windows_at_portrait: list[tuple[int, int]] | None = None

    for ans in pairs["effective"]:
        channel = ans["channel"]
        if channel == "portrait":
            windows_at_portrait = [tuple(w) for w in ans.get("windows", [])]
        chosen = list(ans.get("answer_ids", []))
        r = answer_reliability(ans, session_r)
        if channel == "decan":
            # Design constant, not a fit: a decan rises in well under an hour
            # at high latitude and a self-report of appearance cannot resolve
            # it. Capped rather than replaced, so a document-sourced answer is
            # not *promoted* by the cap.
            r = min(r, cfg.decan_reliability)
        before = normalise(weights)
        contradicts = False

        if channel in ("trait", "element", "modality"):
            # Tags reweight by per-sign likelihood; there is no partition and
            # no class the answer "belongs to".
            weights = apply_trait_answer(weights, grid.asc_sign, chosen, r)
            labels = grid.asc_sign
            supported = _trait_supported(grid.asc_sign, chosen)
        elif channel == "sign_portrait":
            prior_top = None
            if chosen:
                masses = _class_mass(before, grid.asc_sign)
                prior_top = max(masses, key=masses.get) if masses else None
                contradicts = bool(prior_top and prior_top not in set(chosen))
            # A direct "which of these two is you". The answer names a sign,
            # so it is a partition over the Ascendant sign.
            labels = grid.asc_sign
            weights = apply_answer(weights, labels, chosen, r)
            supported = [
                i for i in range(N_GRID) if labels[i] in set(chosen)
            ] if chosen else []
        else:
            labels = partition_for(grid, channel, ans.get("subject"),
                                   windows_at_portrait)
            weights = apply_answer(weights, labels, chosen, r)
            supported = (
                [i for i in range(N_GRID) if labels[i] in set(chosen)]
                if chosen else []
            )
        after = normalise(weights)
        trace.append(
            {
                "contradicts_prior": (
                    contradicts if channel == "sign_portrait" and chosen else False
                ),
                "channel": channel,
                "subject": ans.get("subject"),
                # Internal only: `/compare` reports which phrasing an answer
                # was. The public `per_channel` list is unchanged.
                "variant": ans.get("variant"),
                "answer_ids": chosen,
                "source": ans.get("source") or "client_report",
                "reliability_used": round(r, 6),
                "pair_state": ans.get("pair_state", "single"),
                "class_count": len(set(labels)),
                "supported_fraction": len(supported) / N_GRID,
                "supported": supported,
                "labels": labels,
                "information_bits": round(_kl_bits(after, before), 4),
            }
        )
    return normalise(weights), trace, pairs


def _trait_supported(asc_signs: list[str], selected: list[str]) -> list[int]:
    """Minutes whose sign the selected tags favour above even odds.

    Trait answers are soft, so "supported" is a threshold rather than a class
    membership. It feeds the cross-channel agreement test, which needs a
    region per channel.
    """
    if not selected:
        return []
    favoured = set()
    for sign in set(asc_signs):
        f = 1.0
        for tag_id in selected:
            tag = TRAIT_TAGS.get(tag_id)
            if tag:
                f *= tag["likelihood"][sign]
        if f >= 0.5 ** len(selected):
            favoured.add(sign)
    return [i for i, sg in enumerate(asc_signs) if sg in favoured]


def _to_minute(hhmm: str) -> int:
    hh, mm = map(int, hhmm.split(":")[:2])
    return (hh * 60 + mm) % N_GRID


def _minutes_between(lo: int, hi: int) -> set[int]:
    if lo <= hi:
        return set(range(lo, hi + 1))
    return set(range(lo, N_GRID)) | set(range(0, hi + 1))


def _class_mass(weights: list[float], labels: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for i, w in enumerate(weights):
        out[labels[i]] = out.get(labels[i], 0.0) + w
    return out


def _entropy_bits(mass: dict[str, float]) -> float:
    total = sum(mass.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for v in mass.values():
        p = v / total
        if p > 0:
            h -= p * math.log2(p)
    return h


def _kl_bits(after: list[float], before: list[float]) -> float:
    """Information this answer actually contributed, in bits."""
    total = 0.0
    for p, q in zip(after, before):
        if p > 0 and q > 0:
            total += p * math.log2(p / q)
    return total


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------


def credible_windows(posterior: list[float], mass: float) -> list[tuple[int, int]]:
    """Highest-weight-first credible set, grouped into contiguous runs.

    Ties are taken whole. Answers partition the grid, so every candidate the
    answers agree on carries exactly the same weight - a perfect answerer
    produces a flat plateau, not a peak. Cutting the plateau wherever the
    running mass happens to cross the threshold can drop the true minute even
    when every answer was correct.
    """
    order = sorted(range(N_GRID), key=lambda i: (-posterior[i], i))
    chosen: set[int] = set()
    acc = 0.0
    cutoff: float | None = None
    for i in order:
        if cutoff is not None and posterior[i] < cutoff:
            break
        chosen.add(i)
        acc += posterior[i]
        if acc >= mass and cutoff is None:
            cutoff = posterior[i]
    return _runs(sorted(chosen))


def _runs(indices: list[int]) -> list[tuple[int, int]]:
    if not indices:
        return []
    runs = []
    start = prev = indices[0]
    for i in indices[1:]:
        if i == prev + 1:
            prev = i
            continue
        runs.append((start, prev))
        start = prev = i
    runs.append((start, prev))
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == N_GRID - 1:
        first = runs.pop(0)
        last = runs.pop()
        runs.insert(0, (last[0], first[1] + N_GRID))
    return runs


def window_minutes(window: tuple[int, int]) -> int:
    return window[1] - window[0] + 1


def window_mass(posterior: list[float], window: tuple[int, int]) -> float:
    return sum(posterior[i % N_GRID] for i in range(window[0], window[1] + 1))


def window_midpoint(window: tuple[int, int]) -> int:
    return ((window[0] + window[1]) // 2) % N_GRID


def plateau_midpoint(posterior: list[float]) -> int:
    """Midpoint of the longest contiguous run at the posterior maximum.

    `max(range(N_GRID), key=...)` returns the FIRST minute of a flat maximum,
    which biases a single reported time toward the early edge of the plateau.
    A posterior with few informative answers is very nearly flat, so that bias
    is largest exactly when the engine knows least. Ties in run length go to
    the earliest start.

    Output only: nothing inside the engine reads this.
    """
    top = max(posterior)
    floor = top * (1.0 - 1e-9)
    runs = _runs([i for i in range(N_GRID) if posterior[i] >= floor])
    if not runs:
        return 0
    # `_runs` merges a run that wraps midnight by extending past N_GRID, so
    # length is end - start + 1 in both cases and `window_midpoint` wraps.
    best = max(runs, key=lambda r: (r[1] - r[0], -r[0]))
    return window_midpoint(best)


def minute_to_time(minute: int) -> str:
    hh, mm = divmod(minute % N_GRID, 60)
    return f"{hh:02d}:{mm:02d}"


# --------------------------------------------------------------------------
# Coherence
# --------------------------------------------------------------------------


def chance_agreement(trace: list[dict]) -> tuple[float, int]:
    """Exact probability that random answering agrees at least this well.

    A profile of random answers produces a non-empty intersection if and only
    if it equals the signature of some candidate minute, and the intersection
    is then that signature's cell. So the distribution is read off the joint
    partition in one pass rather than by enumerating profiles.
    """
    informative = [t for t in trace if t["answer_ids"] and t["supported"]]
    if not informative:
        return 1.0, 0

    observed = set(range(N_GRID))
    for t in informative:
        observed &= set(t["supported"])
    observed_size = len(observed)

    # An empty intersection is the absence of agreement, not a very sharp one.
    if observed_size == 0:
        return 1.0, 0

    signature_sizes: dict[tuple, int] = {}
    for i in range(N_GRID):
        sig = tuple(t["labels"][i] for t in informative)
        signature_sizes[sig] = signature_sizes.get(sig, 0) + 1

    profile_probability = 1.0
    for t in informative:
        profile_probability /= max(t["class_count"], 1)

    reachable = sum(1 for size in signature_sizes.values() if size <= observed_size)
    return min(reachable * profile_probability, 1.0), observed_size


def concentration(posterior: list[float]) -> float:
    h = -sum(p * math.log2(p) for p in posterior if p > 0)
    return 1.0 - h / math.log2(N_GRID)


# --------------------------------------------------------------------------
# Tiers
# --------------------------------------------------------------------------


def channel_conflict(trace: list[dict], sign_labels: list[str]) -> bool:
    """Did the portrait answer contradict what the structural answers implied?

    Measured against the posterior as it stood *before* the portrait answer,
    so a person who confirms a portrait that the element and modality answers
    did not point at is flagged - which is exactly the adjacent-sign case.
    """
    portrait = next(
        (t for t in trace if t["channel"] == "sign_portrait" and t["answer_ids"]),
        None,
    )
    if portrait is None:
        return False
    return portrait.get("contradicts_prior", False)


def _pair_states(trace: list[dict]) -> dict[str, str]:
    """Pair state per channel, for the channels that carry one."""
    out: dict[str, str] = {}
    for t in trace:
        out[t["channel"]] = t.get("pair_state", "single")
    return out


def stage1_pairs_agree(trace: list[dict]) -> bool:
    """Did every stage-1 question get asked twice and answered the same way?

    This is Tier 3's whole coherence requirement. A random answerer meets it
    about one time in twenty-four - one element in four, one modality in
    three, one portrait in two - which is why G6 has to keep including
    random rather than treating it as out of scope.
    """
    states = _pair_states(trace)
    return all(states.get(c) == "agree" for c in STAGE1_CHANNELS)


def stage1_favours_sun_sign(trace: list[dict], sun_sign: str | None) -> bool:
    """Did the stage-1 answers concentrate on the Sun sign?

    The stereotype test, frozen before measurement: the element answer, the
    modality answer and the confirmed portrait all name the Sun sign. Honest
    answers land there about one time in twelve; a self-describer lands there
    every time. Nothing is filtered on the strength of this - it only raises
    what Tier 3 and Tier 1 have to show.
    """
    if not sun_sign:
        return False
    axis = _SIGN_AXIS.get(sun_sign)
    if not axis:
        return False
    want = {
        "element": f"element_{axis['element']}",
        "modality": f"modality_{axis['modality']}",
        "sign_portrait": sun_sign,
    }
    seen = 0
    for t in trace:
        expected = want.get(t["channel"])
        if expected is None or not t["answer_ids"]:
            continue
        if expected not in set(t["answer_ids"]):
            return False
        seen += 1
    return seen == len(want)


def assign_tier(posterior: list[float], trace: list[dict], cfg: InterviewConfig,
                pairs: dict | None = None, sign_labels: list[str] | None = None,
                sun_sign: str | None = None) -> dict:
    pairs = pairs or {"agreeing_pairs": 0, "disagreeing_pairs": 0,
                      "session_reliability": cfg.channel_reliability}
    chance_p, overlap = chance_agreement(trace)
    conc = concentration(posterior)
    agree = pairs["agreeing_pairs"]
    disagree = pairs["disagreeing_pairs"]
    labels = sign_labels or _rising_sign_labels(trace)
    conflict = channel_conflict(trace, labels)
    portrait_given = any(
        t["channel"] == "sign_portrait" and t["answer_ids"] for t in trace
    )

    # The pair requirement applies whenever the session actually produced
    # pairs, however they were formed. In the interview they come from two
    # phrasings; in professional single-pass they come from two *sources* for
    # the same partition. It is waived only when no second observation of any
    # kind exists, because there is then nothing to cross-check against.
    has_pairs = (agree + disagree) > 0
    enforce_pairs = cfg.repeat or has_pairs

    # Sun-sign self-attribution. When stage 1 lands exactly on the Sun sign,
    # the three stage-1 pairs are no longer three independent confirmations:
    # they can all be one recalled stereotype, so for Tier 1 they count as one
    # pair rather than three. The detector's other clause - requiring the
    # decan channel to corroborate before a sign was delivered - went with
    # Tier 3, because no sign is delivered any more. Off by default; see
    # `InterviewConfig.sun_sign_detector`.
    sun_attributed = cfg.sun_sign_detector and stage1_favours_sun_sign(
        trace, sun_sign
    )
    stage1_agreeing = sum(
        1 for c in STAGE1_CHANNELS if _pair_states(trace).get(c) == "agree"
    )
    agree_t1 = agree - max(0, stage1_agreeing - 1) if sun_attributed else agree

    pair_ok_t1 = (not enforce_pairs) or (
        agree_t1 >= cfg.tier1_min_agreeing_pairs and disagree == 0
    )
    pair_ok_t2 = (not enforce_pairs) or agree >= cfg.tier2_min_agreeing_pairs

    t1 = credible_windows(posterior, cfg.tier1_mass)
    if (
        not conflict
        and portrait_given
        and pair_ok_t1
        and len(t1) == 1
        and window_minutes(t1[0]) <= cfg.tier1_window_minutes
        and window_mass(posterior, t1[0]) >= cfg.tier1_mass
        and chance_p < cfg.tier1_chance_p
    ):
        return _tier_result(1, t1, posterior, conc, chance_p, overlap, pairs,
                            "single window, independent channel agreement, "
                            "and repeated phrasings agreed",
                            sun_attributed=sun_attributed)

    t2 = credible_windows(posterior, cfg.tier2_mass)
    if (
        not conflict
        and pair_ok_t2
        and 1 <= len(t2) <= cfg.tier2_max_windows
        and sum(window_mass(posterior, w) for w in t2) >= cfg.tier2_mass
        and chance_p < cfg.tier2_chance_p
        and max(window_minutes(w) for w in t2) <= cfg.tier2_window_minutes
    ):
        return _tier_result(2, t2, posterior, conc, chance_p, overlap, pairs,
                            "two or three windows carry the mass",
                            sun_attributed=sun_attributed)

    # There is no Tier 3. A rising sign is never delivered on its own.
    #
    # This is the v3.3 spec's own pre-registered fallback, taken because its
    # gates failed. Reordering the tiers by strength of claim made Tier 3
    # reachable for the first time, and it was immediately and badly wrong: an
    # answerer who describes themselves consistently one sign over satisfies
    # every condition a sign-only session can be asked to satisfy - all three
    # stage-1 pairs agree with themselves, nothing contradicts anything, and
    # the mass concentrates hard on the neighbouring sign. That session is
    # numerically indistinguishable from an honest one, so no threshold
    # separates them. Measured: 38.5% of adjacent-sign runs were handed a
    # Tier 3 sign and 80.2% of those signs were wrong, against G6's 5% bar.
    #
    # Tier 2's shortlist and Tier 4's refusal carry the whole range. The
    # posterior over signs is still returned as `sign_blocks` - a mass per
    # sign, which describes what the answers support rather than claiming
    # which sign it is. See benchmarks/RESULTS_INTERVIEW_v3_3.md.
    # Ordered most fundamental first: a session with nothing in it should be
    # told the mass never concentrated, not that a pair was missing.
    reason = "the method cannot work from these answers"
    if conflict:
        reason = "the confirmed portrait contradicts the earlier answers"
    elif not portrait_given:
        reason = "the mass never concentrated enough to confirm a portrait"
    elif disagree:
        reason = "the repeated phrasings did not agree"
    elif not pair_ok_t2:
        reason = "no question was confirmed by a second phrasing"
    return _tier_result(4, [], posterior, conc, chance_p, overlap, pairs,
                        reason, conflict=conflict,
                        sun_attributed=sun_attributed)


def _rising_sign_labels(trace) -> list[str]:
    for t in trace:
        if t["channel"] in ("rising_sign", "trait"):
            return t["labels"]
    return []


def _tier_result(tier, windows, posterior, conc, chance_p, overlap, pairs, reason,
                 rising_sign=None, conflict=False, sun_attributed=False) -> dict:
    return {
        "tier": tier,
        "reason": reason,
        "rising_sign": rising_sign,
        "channel_conflict": conflict,
        "sun_sign_attribution": sun_attributed,
        "windows": [
            {
                "start": minute_to_time(w[0]),
                "end": minute_to_time(w[1]),
                "midpoint": minute_to_time(window_midpoint(w)),
                "width_minutes": window_minutes(w),
                "mass": round(window_mass(posterior, w), 6),
            }
            for w in windows
        ],
        "coherence": {
            "concentration": round(conc, 6),
            "chance_agreement_p": round(chance_p, 8),
            "channel_overlap_minutes": overlap,
            "agreeing_pairs": pairs["agreeing_pairs"],
            "disagreeing_pairs": pairs["disagreeing_pairs"],
            "session_reliability": pairs["session_reliability"],
        },
    }


# --------------------------------------------------------------------------
# Question generation
# --------------------------------------------------------------------------


def _partition_gain(posterior: list[float], labels: list[str]) -> float:
    return _entropy_bits(_class_mass(posterior, labels))


def _inventory_answer(inventory: dict, options: list[str]) -> list[str]:
    """Read a mover-house answer off a sphere inventory, if it decides one.

    The inventory says which life areas are dominant, present or absent. A
    planet must sit in a *tenanted* house, so what the inventory rules out is
    the `absent` ones; the answer is the union of the rest.

    Preferring `dominant` over `present` was tried first and was wrong: a
    planet often sits alone in a merely `present` house, so taking only the
    dominant options excluded the truth and produced a 12% wrong-window rate
    for an otherwise perfect answerer. Ruling out only what the inventory
    positively denies keeps the truth in the set.
    """
    if not inventory:
        return []
    picked = [
        h for h in options
        if inventory.get(h, {}).get("status") in ("dominant", "present")
    ]
    if picked and len(picked) < len(options):
        return picked
    return []


def next_question(grid: ChartGrid, posterior: list[float], answers: list[dict],
                  cfg: InterviewConfig, inventory: dict | None = None) -> dict | None:
    """The next question, chosen by expected information gain.

    Stage 1 is a *sequence* of small trait questions rather than one 12-way
    choice. At each step the engine picks the set of at most four tags whose
    answer partitions the remaining sign mass best, and stops when the sign
    mass concentrates or the next split stops paying.
    """
    asked = {(a["channel"], a.get("subject"), a.get("variant", "a")) for a in answers}
    answered_keys = [
        (a["channel"], a.get("subject")) for a in answers
        if a.get("variant", "a") == "a"
    ]
    trait_rounds = sum(
        1 for a in answers
        if a["channel"] == "trait" and a.get("variant", "a") == "a"
    )

    prior = sign_mass(posterior, grid.asc_sign)
    top_sign_mass = max(prior.values()) if prior else 0.0

    # ---- stage 1: two structured questions, not a trait soup ----------
    # Element, then modality. Adjacent signs differ in BOTH, so reaching a
    # neighbour by mistake takes two errors rather than one - which is the
    # failure that broke G1 in v3, where neighbouring signs shared most of
    # their trait likelihoods and one confident mistake was enough.
    if ("element", None, "a") not in asked:
        return _structural_question("element", ELEMENT_TAGS, prior, "a")
    if ("modality", None, "a") not in asked:
        return _structural_question("modality", MODALITY_TAGS, prior, "a")

    # ---- two-portrait confirmation ------------------------------------
    ranked = sorted(prior.items(), key=lambda kv: -kv[1])
    lead = [s_ for s_, _ in ranked[:MAX_PORTRAIT_SIGNS]]
    lead_mass = sum(m for _, m in ranked[:MAX_PORTRAIT_SIGNS])
    top3_mass = sum(m for _, m in ranked[:3])
    # Fire once the leading signs carry the mass. Three signs qualify too -
    # the rule is to offer the top two of them and let `cannot_choose` stand
    # for "neither".
    #
    # This threshold is load-bearing for safety, which v3.3 established by
    # removing it and measuring the result. Asking the portrait
    # unconditionally at the end of the structural questions - when the top
    # sign still carries only about 0.23 of the mass - lets an answerer
    # confirm a portrait the earlier answers did not point at, which
    # concentrates the posterior hard on that sign before any independent
    # channel has spoken. The adjacent-sign answerer's Tier 1 wrong-window
    # rate went from 1.04% to 32.50%, with *every* such window wrong. Waiting
    # for the mass means the portrait can only confirm what something else
    # already suggested. See benchmarks/RESULTS_INTERVIEW_v3_3.md.
    if ("sign_portrait", None, "a") not in asked and (
        lead_mass >= cfg.portrait_sign_threshold
        or top3_mass >= cfg.portrait_sign_threshold
    ):
        return _sign_portrait_question(lead, prior, "a")

    if ("decan", None, "a") not in asked:
        labels = partition_for(grid, "decan", None)
        if _partition_gain(posterior, labels) >= cfg.min_information_bits:
            return _decan_question(posterior, labels, "a")

    movers = [a for a in answers if a["channel"] == "mover_house"
              and a.get("variant", "a") == "a"]
    if len(movers) < cfg.max_mover_questions:
        best, best_gain = None, 0.0
        for name, _ in core.PLANETS:
            if ("mover_house", name, "a") in asked:
                continue
            labels = partition_for(grid, "mover_house", name)
            gain = _partition_gain(posterior, labels)
            if gain > best_gain:
                best, best_gain = name, gain
        if best and best_gain >= cfg.min_information_bits:
            q = _mover_question(grid, posterior, best, best_gain, "a")
            if inventory:
                picked = _inventory_answer(
                    inventory, [o["answer_id"] for o in q["options"]]
                )
                if picked:
                    q["answered_from_inventory"] = picked
            return q

    # ---- repeat phrasings ----------------------------------------------
    if cfg.repeat:
        for channel, subject in answered_keys[: cfg.repeat_pairs]:
            if (channel, subject, "b") in asked:
                continue
            if channel in ("element", "modality"):
                tags = ELEMENT_TAGS if channel == "element" else MODALITY_TAGS
                return _structural_question(channel, tags, prior, "b")
            if channel == "sign_portrait":
                original = next(
                    (a for a in answers if a["channel"] == "sign_portrait"
                     and a.get("variant", "a") == "a"),
                    None,
                )
                offered = list((original or {}).get("offered_tag_ids") or [])
                if offered:
                    return _sign_portrait_question(offered, prior, "b")
                continue
            if channel == "trait":
                # Free-text tags were never asked as a question, so there is
                # no phrasing to repeat: they carry their own trust instead.
                digits = str(subject or "").lstrip("t")
                if not digits.isdigit():
                    continue
                original = next(
                    (a for a in answers
                     if a["channel"] == "trait" and a.get("subject") == subject
                     and a.get("variant", "a") == "a"),
                    None,
                )
                tags = list((original or {}).get("offered_tag_ids") or [])
                if tags:
                    return _trait_question(tags, 0.0, int(digits), "b")
                continue
            labels = partition_for(grid, channel, subject)
            if channel == "decan":
                return _decan_question(posterior, labels, "b")
            if channel == "mover_house":
                return _mover_question(
                    grid, posterior, subject, _partition_gain(posterior, labels), "b"
                )

    windows = credible_windows(posterior, cfg.tier2_mass)
    if 2 <= len(windows) <= MAX_PORTRAIT_OPTIONS and ("portrait", None, "a") not in asked:
        return _portrait_question(grid, posterior, windows, "a")

    return None


def _best_tag_set(prior: dict[str, float], exclude: set[str],
                  cfg: InterviewConfig) -> tuple[list[str], float]:
    """Greedily grow a set of at most MAX_OPTIONS tags by expected gain.

    Exhaustive search over 30-choose-4 would be 27,405 sets per step; greedy
    growth costs 30 + 29 + 28 + 27 evaluations and picks the same first tag by
    construction.
    """
    available = [t for t in TRAIT_TAGS if t not in exclude]
    if not available:
        return [], 0.0

    size = min(MAX_OPTIONS, cfg.max_tags_per_question)
    live = [s for s, m in prior.items() if m > 1e-6]
    if not live:
        return [], 0.0

    # One tag per live front-runner, each chosen to speak for that sign
    # *against the others on offer*. Grouping the signs by element or modality
    # instead was tried and measured worse on sign recovery (54% against 76%),
    # so the simpler rule stands.
    rivals = [s for s, _ in sorted(prior.items(), key=lambda kv: -kv[1])][:size]
    chosen: list[str] = []
    for sign in rivals:
        others = [s for s in rivals if s != sign]
        best, best_score = None, float("-inf")
        for tag_id in available:
            if tag_id in chosen:
                continue
            lik = TRAIT_TAGS[tag_id]["likelihood"]
            score = lik[sign] - (max(lik[o] for o in others) if others else 0.0)
            if score > best_score:
                best, best_score = tag_id, score
        if best is not None:
            chosen.append(best)

    return chosen, _trait_expected_gain(prior, chosen, cfg.channel_reliability)


def _live_classes(posterior: list[float], labels: list[str], floor: float = 1e-4):
    mass = _class_mass(posterior, labels)
    return {k: v for k, v in mass.items() if v >= floor}


def _class_windows(labels: list[str], cls: str) -> list[tuple[int, int]]:
    return _runs([i for i in range(N_GRID) if labels[i] == cls])


def _structural_question(channel: str, tag_ids: list[str],
                         prior: dict[str, float], variant: str) -> dict:
    """One of the two fixed stage-1 questions. Four options or three."""
    key = "paraphrase_key" if variant == "b" else "label_key"
    facet = VARIANT_FACET[channel][variant]
    return {
        "question_id": f"stage1_{channel}_{variant}",
        "channel": channel,
        "subject": None,
        "variant": variant,
        "facet": facet,
        "stage": 1,
        "select": "single",
        "max_select": 1,
        "information_bits": round(
            _trait_expected_gain(prior, tag_ids, 0.6), 4
        ),
        "options": [
            {"answer_id": t, "label_key": TRAIT_TAGS[t][key]} for t in tag_ids
        ],
        "offered_tag_ids": list(tag_ids),
        "allow_cannot_choose": True,
    }


def _sign_portrait_question(signs: list[str], prior: dict[str, float],
                            variant: str) -> dict:
    """Two portraits, one question: which of these two is you.

    Its own channel on purpose. Disagreement with what the structural answers
    already implied is a channel conflict, and a conflict blocks Tier 3 as
    well as Tier 1 - the v2 mechanism that caught the adjacent-sign answerer,
    now applied to the sign itself.
    """
    facet = VARIANT_FACET["sign_portrait"][variant]
    return {
        "question_id": f"stage2_sign_portrait_{variant}",
        "channel": "sign_portrait",
        "subject": None,
        "variant": variant,
        "facet": facet,
        "stage": 2,
        "select": "single",
        "max_select": 1,
        "information_bits": round(
            _entropy_bits({s_: prior.get(s_, 0.0) for s_ in signs}), 4
        ),
        "options": [
            {"answer_id": s_, "label_key": f"sign.{s_}.{facet}"} for s_ in signs
        ],
        "offered_tag_ids": list(signs),
        "allow_cannot_choose": True,
    }


def _trait_question(tag_ids: list[str], gain: float, round_index: int,
                    variant: str) -> dict:
    """At most four tags, multi-select, and no time span anywhere in it."""
    key = "paraphrase_key" if variant == "b" else "label_key"
    return {
        "question_id": f"stage1_trait_{round_index}_{variant}",
        "channel": "trait",
        "subject": f"t{round_index}",
        "variant": variant,
        "stage": 1,
        "select": "multi",
        "max_select": min(len(tag_ids), MAX_OPTIONS),
        "information_bits": round(gain, 4),
        "options": [
            {
                "answer_id": t,
                "trait_channel": TRAIT_TAGS[t]["channel"],
                "label_key": TRAIT_TAGS[t][key],
            }
            for t in tag_ids
        ],
        "offered_tag_ids": list(tag_ids),
        "allow_cannot_choose": True,
    }


def _decan_question(posterior, labels, variant) -> dict:
    facet = VARIANT_FACET["decan"][variant]
    live = _live_classes(posterior, labels)
    top = sorted(live, key=lambda s: -live[s])[:MAX_OPTIONS]
    options = []
    for cls in top:
        sign, decan = cls.rsplit("_", 1)
        options.append(
            {"answer_id": cls, "label_key": f"decan.{sign}.{decan}.{facet}"}
        )
    return {
        "question_id": f"stage2_decan_{variant}",
        "channel": "decan",
        "subject": None,
        "variant": variant,
        "facet": facet,
        "stage": 2,
        "select": "single",
        "max_select": 1,
        "information_bits": round(_partition_gain(posterior, labels), 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _mover_question(grid, posterior, planet, gain, variant) -> dict:
    facet = VARIANT_FACET["mover_house"][variant]
    labels = partition_for(grid, "mover_house", planet)
    live = _live_classes(posterior, labels)
    top = sorted(live, key=lambda h: -live[h])[:MAX_MOVER_OPTIONS]
    options = [
        {"answer_id": house, "label_key": f"planet.{planet}.house.{house}.{facet}"}
        for house in sorted(top, key=lambda h: int(h))
    ]
    return {
        "question_id": f"stage3_mover_{planet}_{variant}",
        "channel": "mover_house",
        "subject": planet,
        "variant": variant,
        "facet": facet,
        "stage": 3,
        "select": "single",
        "max_select": 1,
        "information_bits": round(gain, 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _portrait_question(grid, posterior, windows, variant) -> dict:
    windows = list(windows)[:MAX_PORTRAIT_OPTIONS]
    options = []
    for idx, w in enumerate(windows):
        mid = window_midpoint(w)
        options.append(
            {
                "answer_id": f"w{idx}",
                "ascendant_sign": grid.asc_sign[mid],
                "planet_houses": {n: grid.planet_house[n][mid] for n, _ in core.PLANETS},
                "label_key": f"portrait.window.{idx}",
            }
        )
    differing = [
        name for name, _ in core.PLANETS
        if len({o["planet_houses"][name] for o in options}) > 1
    ]
    for o in options:
        o["distinguishing_placements"] = {n: o["planet_houses"][n] for n in differing}
    return {
        "question_id": f"stage4_portrait_{variant}",
        "channel": "portrait",
        "subject": None,
        "variant": variant,
        "facet": VARIANT_FACET["portrait"][variant],
        "stage": 4,
        "select": "single",
        "max_select": 1,
        "information_bits": round(
            _entropy_bits({o["answer_id"]: window_mass(posterior, w)
                           for o, w in zip(options, windows)}), 4
        ),
        "options": options,
        "distinguishing_placements": differing,
        "windows": [list(w) for w in windows],
        "allow_cannot_choose": True,
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def run_interview(birth_date: dt.date, lat: float, lon: float, tz: str,
                  answers: list[dict], cfg: InterviewConfig | None = None,
                  known_bounds: dict | None = None,
                  claimed_time: str | None = None,
                  sphere_inventory: dict | None = None,
                  hypothesis: dict | None = None,
                  trait_tags: list[str] | None = None) -> dict:
    """The interview result. Unchanged public contract.

    Calibration needs the posterior and the trace as well, and widening this
    return value would put internals into the `/step` response where no client
    should be reading them. `_run_interview_internal` returns both; this stays
    the only thing the endpoint serialises.
    """
    return _run_interview_internal(
        birth_date, lat, lon, tz, answers, cfg, known_bounds, claimed_time,
        sphere_inventory, hypothesis, trait_tags,
    )[0]


def _run_interview_internal(
    birth_date: dt.date, lat: float, lon: float, tz: str,
    answers: list[dict], cfg: InterviewConfig | None = None,
    known_bounds: dict | None = None,
    claimed_time: str | None = None,
    sphere_inventory: dict | None = None,
    hypothesis: dict | None = None,
    trait_tags: list[str] | None = None,
) -> tuple[dict, list[float], list[dict], "ChartGrid"]:
    """`run_interview` plus the internals calibration needs.

    Returns `(result, posterior, trace, grid)`. Private: `/compare` is the
    only caller, and it uses them to build a record that names no time.
    """
    cfg = cfg or InterviewConfig()
    grid = ChartGrid(birth_date, lat, lon, tz, cfg.house_system)
    answers = list(answers)
    if trait_tags:
        # Confirmed free-text tags are one more observation of the same
        # vocabulary, at their own trust level. They arrive as an answer so
        # they pass through the identical path - pairing, trust, reweighting.
        answers = answers + [
            {
                "question_id": "free_text_traits",
                "channel": "trait",
                "subject": "free_text",
                "variant": "a",
                "source": "free_text_confirmed",
                "answer_ids": list(trait_tags),
                "offered_tag_ids": list(trait_tags),
            }
        ]
    posterior, trace, pairs = build_posterior(
        grid, answers, cfg, known_bounds, claimed_time
    )
    tier = assign_tier(posterior, trace, cfg, pairs, grid.asc_sign,
                       sun_sign=grid.sun_sign)
    question = next_question(grid, posterior, answers, cfg, sphere_inventory)

    answered = [t for t in trace if t["answer_ids"]]
    # Sign blocks are an OUTPUT. They used to be rendered inside the stage-1
    # question as twelve time spans, which asked the person to choose the very
    # thing they came to find out. They belong here.
    sign_labels = grid.asc_sign
    mass_by_sign = sign_mass(posterior, sign_labels)
    sign_blocks = []
    for sign in sorted(mass_by_sign, key=lambda s: -mass_by_sign[s]):
        for lo, hi in _runs([i for i in range(N_GRID) if sign_labels[i] == sign]):
            sign_blocks.append(
                {
                    "sign": sign,
                    "start": minute_to_time(lo),
                    "end": minute_to_time(hi),
                    "mass": round(mass_by_sign[sign], 6),
                }
            )

    # One unbiased time to work from, in every tier. When the engine has
    # named windows the midpoint of the heaviest is the honest single point;
    # with no windows it is the middle of the posterior's plateau rather than
    # its early edge.
    working_minute, working_source = _working_minute(posterior, tier["windows"])

    result = {
        "tier": tier["tier"],
        "tier_reason": tier["reason"],
        "rising_sign": tier["rising_sign"],
        "sign_blocks": sign_blocks,
        "windows": tier["windows"],
        "coherence": tier["coherence"],
        "next_question": question,
        "posterior_summary": {
            # `peak_time` is the FIRST minute of a flat maximum. It is kept
            # unchanged for backward compatibility; `working_time` is the one
            # to report to a person. See CLAUDE.md.
            "peak_time": minute_to_time(max(range(N_GRID), key=lambda i: posterior[i])),
            "best_time": minute_to_time(plateau_midpoint(posterior)),
            "working_time": minute_to_time(working_minute),
            "working_time_source": working_source,
            "top_mass": round(max(posterior), 6),
            "effective_candidates": round(
                2 ** (-sum(p * math.log2(p) for p in posterior if p > 0)), 2
            ),
        },
        "per_channel": [
            {
                "channel": t["channel"],
                "subject": t["subject"],
                "answer_ids": t["answer_ids"],
                "source": t["source"],
                "pair_state": t["pair_state"],
                "reliability_used": t["reliability_used"],
                "supported_minutes": len(t["supported"]),
                "class_count": t["class_count"],
                "information_bits": t["information_bits"],
            }
            for t in trace
        ],
        "telemetry": {
            "grid_minutes": N_GRID,
            "grid_step_minutes": GRID_STEP_MINUTES,
            "answers_total": len(trace),
            "answers_informative": len(answered),
            "cannot_choose_count": len(trace) - len(answered),
            "channels_used": sorted({t["channel"] for t in answered}),
            "tier": tier["tier"],
            "concentration": tier["coherence"]["concentration"],
            "chance_agreement_p": tier["coherence"]["chance_agreement_p"],
            "channel_overlap_minutes": tier["coherence"]["channel_overlap_minutes"],
            "agreeing_pairs": pairs["agreeing_pairs"],
            "disagreeing_pairs": pairs["disagreeing_pairs"],
            "session_reliability": pairs["session_reliability"],
            "window_widths": [w["width_minutes"] for w in tier["windows"]],
            "selection": "interval_midpoint",
            "mode": cfg.mode,
            "repeat": cfg.repeat,
        },
    }

    # The astrologer's own hypothesis never touches the posterior. It is
    # scored against the result, which is the only honest way to use it.
    if hypothesis:
        result["hypothesis_check"] = _check_hypothesis(hypothesis, tier["windows"])

    if cfg.mode == "professional":
        result["density"] = [
            {"time": minute_to_time(i), "weight": round(posterior[i], 9)}
            for i in range(N_GRID)
        ]
        result["decisive_questions"] = [
            {
                "channel": t["channel"],
                "subject": t["subject"],
                "information_bits": t["information_bits"],
                "pair_state": t["pair_state"],
            }
            for t in sorted(trace, key=lambda x: -x["information_bits"])
            if t["answer_ids"]
        ]

    return result, posterior, trace, grid


def compare_record(result: dict, posterior: list[float], trace: list[dict],
                   grid: "ChartGrid", documented_minute: int) -> dict:
    """The PII-free calibration record for one scored session.

    This exists so a labelled corpus can accumulate WITHOUT storing anything
    about the person. Nothing here is a clock time, an answer id, a tag id, a
    date or a place: every field is either a rank, a rate, a boolean or a
    channel name. `tests/test_interview_v3_5.py` enforces that structurally
    rather than trusting this docstring.

    What it answers that the old five keys could not:

    * how good the posterior was *in every tier*, including Tier 4, where
      there is no window and so was no error at all;
    * where the documented minute ranked in the posterior, which separates
      "wrong" from "nearly right" far better than a midpoint error;
    * WHICH answers agreed with the documented time, so a channel that is
      systematically misleading can be found without reading anyone's
      answers.
    """
    working_minute = _to_minute(result["posterior_summary"]["working_time"])
    p_truth = posterior[documented_minute]
    better = sum(1 for x in posterior if x > p_truth)
    equal = sum(1 for x in posterior if x == p_truth)
    # Mid-rank: ties share the average of the positions they span, so a flat
    # posterior scores 50 rather than 0 or 100.
    rank_pct = 100.0 * (better + 0.5 * (equal - 1)) / (N_GRID - 1)

    truth_sign = grid.asc_sign[documented_minute]
    masses = sign_mass(posterior, grid.asc_sign)
    top_sign = max(masses, key=masses.get) if masses else None

    return {
        "abs_error_minutes_working": _circular_minutes(
            working_minute, documented_minute),
        "working_time_source": result["posterior_summary"]["working_time_source"],
        "truth_rank_pct": round(rank_pct, 1),
        "truth_sign_correct": top_sign == truth_sign,
        "truth_sign_mass": round(masses.get(truth_sign, 0.0), 4),
        # Registrars round. A corpus that cannot see that will read the
        # rounding as engine error.
        "documented_minute_is_round": documented_minute % 5 == 0,
        "per_answer": [
            {
                "channel": t["channel"],
                "subject": t["subject"],
                "variant": t.get("variant"),
                "source": t["source"],
                "pair_state": t["pair_state"],
                "class_count": t["class_count"],
                "cannot_choose": not t["answer_ids"],
                "truth_in_choice": (
                    None if (not t["answer_ids"] or not t["supported"])
                    else documented_minute in set(t["supported"])
                ),
            }
            for t in trace
        ],
    }


def _circular_minutes(a: int, b: int) -> int:
    d = abs(a - b) % N_GRID
    return min(d, N_GRID - d)


def _working_minute(posterior: list[float],
                    windows: list[dict]) -> tuple[int, str]:
    """The single time to work from, and where it came from.

    Windows first: if the engine named regions, the heaviest one's midpoint is
    what it is actually asserting. Ties go to the engine's own list order.
    Otherwise the plateau midpoint, which is unbiased where `peak_time` is not.
    """
    if windows:
        best = max(windows, key=lambda w: w["mass"])
        return _to_minute(best["midpoint"]), "window_midpoint"
    return plateau_midpoint(posterior), "plateau_midpoint"


def _check_hypothesis(hypothesis: dict, windows: list[dict]) -> dict:
    start = _to_minute(hypothesis["start"])
    end = _to_minute(hypothesis.get("end") or hypothesis["start"])
    inside = False
    distance = None
    for w in windows:
        ws, we = _to_minute(w["start"]), _to_minute(w["end"])
        win = _minutes_between(ws, we)
        hyp = _minutes_between(start, end)
        if win & hyp:
            inside = True
            distance = 0
            break
        gaps = []
        for h in hyp:
            for x in (ws, we):
                d = abs(h - x) % N_GRID
                gaps.append(min(d, N_GRID - d))
        if gaps:
            best = min(gaps)
            distance = best if distance is None else min(distance, best)
    return {
        "inside_result_window": inside,
        "distance_minutes": distance,
        "excluded_from_posterior": True,
    }
