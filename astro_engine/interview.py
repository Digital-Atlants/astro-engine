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
import math
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

CHANNELS = ("rising_sign", "decan", "mover_house", "portrait")
DECAN_NAMES = ("first", "second", "third")

# Two phrasings of the same underlying partition. The client renders them as
# different questions; the engine knows they are a pair.
VARIANTS = ("a", "b")
VARIANT_FACET = {
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
    )

    def __init__(
        self,
        channel_reliability: float = 0.60,
        tier1_mass: float = 0.60,
        tier2_mass: float = 0.60,
        tier1_chance_p: float = 0.002,
        tier2_chance_p: float = 0.20,
        tier1_window_minutes: int = 30,
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
    ):
        self.channel_reliability = channel_reliability
        self.tier1_mass = tier1_mass
        self.tier2_mass = tier2_mass
        self.tier1_chance_p = tier1_chance_p
        self.tier2_chance_p = tier2_chance_p
        self.tier1_window_minutes = tier1_window_minutes
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
        labels = partition_for(grid, channel, ans.get("subject"), windows_at_portrait)
        chosen = list(ans.get("answer_ids", []))
        r = answer_reliability(ans, session_r)

        before = normalise(weights)
        weights = apply_answer(weights, labels, chosen, r)
        after = normalise(weights)
        supported = [i for i in range(N_GRID) if labels[i] in set(chosen)] if chosen else []
        trace.append(
            {
                "channel": channel,
                "subject": ans.get("subject"),
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


def assign_tier(posterior: list[float], trace: list[dict], cfg: InterviewConfig,
                pairs: dict | None = None) -> dict:
    pairs = pairs or {"agreeing_pairs": 0, "disagreeing_pairs": 0,
                      "session_reliability": cfg.channel_reliability}
    chance_p, overlap = chance_agreement(trace)
    conc = concentration(posterior)
    agree = pairs["agreeing_pairs"]
    disagree = pairs["disagreeing_pairs"]

    # The pair requirement applies whenever the session actually produced
    # pairs, however they were formed. In the interview they come from two
    # phrasings; in professional single-pass they come from two *sources* for
    # the same partition. It is waived only when no second observation of any
    # kind exists, because there is then nothing to cross-check against.
    has_pairs = (agree + disagree) > 0
    enforce_pairs = cfg.repeat or has_pairs
    pair_ok_t1 = (not enforce_pairs) or (
        agree >= cfg.tier1_min_agreeing_pairs and disagree == 0
    )
    pair_ok_t2 = (not enforce_pairs) or agree >= cfg.tier2_min_agreeing_pairs

    t1 = credible_windows(posterior, cfg.tier1_mass)
    if (
        pair_ok_t1
        and len(t1) == 1
        and window_minutes(t1[0]) <= cfg.tier1_window_minutes
        and window_mass(posterior, t1[0]) >= cfg.tier1_mass
        and chance_p < cfg.tier1_chance_p
    ):
        return _tier_result(1, t1, posterior, conc, chance_p, overlap, pairs,
                            "single window, independent channel agreement, "
                            "and repeated phrasings agreed")

    t2 = credible_windows(posterior, cfg.tier2_mass)
    if (
        pair_ok_t2
        and 1 <= len(t2) <= 3
        and sum(window_mass(posterior, w) for w in t2) >= cfg.tier2_mass
        and chance_p < cfg.tier2_chance_p
        and max(window_minutes(w) for w in t2) <= cfg.tier1_window_minutes * 3
    ):
        return _tier_result(2, t2, posterior, conc, chance_p, overlap, pairs,
                            "two or three windows carry the mass")

    informative = [t for t in trace if t["answer_ids"]]
    if informative:
        labels = _rising_sign_labels(trace)
        sign_mass = _class_mass(posterior, labels) if labels else {}
        best_sign = max(sign_mass, key=sign_mass.get) if sign_mass else None
        return _tier_result(3, [], posterior, conc, chance_p, overlap, pairs,
                            "channels agree only at the level of the rising sign",
                            rising_sign=best_sign)

    return _tier_result(4, [], posterior, conc, chance_p, overlap, pairs,
                        "the method cannot work from these answers")


def _rising_sign_labels(trace) -> list[str]:
    for t in trace:
        if t["channel"] == "rising_sign":
            return t["labels"]
    return []


def _tier_result(tier, windows, posterior, conc, chance_p, overlap, pairs, reason,
                 rising_sign=None) -> dict:
    return {
        "tier": tier,
        "reason": reason,
        "rising_sign": rising_sign,
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
    """The next question, chosen by expected information gain over geometry.

    Primary phrasings first, then the repeat phrasings for the questions that
    carried the most information, then the portrait choice. The repeats come
    later in the sequence on purpose: adjacent repetition invites the person to
    recall their previous answer rather than answer again.
    """
    asked = {(a["channel"], a.get("subject"), a.get("variant", "a")) for a in answers}
    answered_keys = [
        (a["channel"], a.get("subject")) for a in answers
        if a.get("variant", "a") == "a"
    ]

    if ("rising_sign", None, "a") not in asked:
        return _sign_question(grid, posterior, partition_for(grid, "rising_sign", None), "a")

    if ("decan", None, "a") not in asked:
        labels = partition_for(grid, "decan", None)
        if _partition_gain(posterior, labels) >= cfg.min_information_bits:
            return _decan_question(grid, posterior, labels, "a")

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

    # Repeat phrasings, most informative questions first.
    if cfg.repeat:
        ranked = sorted(
            answered_keys,
            key=lambda k: -_partition_gain(
                [1.0 / N_GRID] * N_GRID, partition_for(grid, k[0], k[1])
            ),
        )
        for channel, subject in ranked[: cfg.repeat_pairs]:
            if (channel, subject, "b") in asked:
                continue
            labels = partition_for(grid, channel, subject)
            if channel == "rising_sign":
                return _sign_question(grid, posterior, labels, "b")
            if channel == "decan":
                return _decan_question(grid, posterior, labels, "b")
            if channel == "mover_house":
                return _mover_question(
                    grid, posterior, subject, _partition_gain(posterior, labels), "b"
                )

    windows = credible_windows(posterior, cfg.tier2_mass)
    if 2 <= len(windows) <= 4 and ("portrait", None, "a") not in asked:
        return _portrait_question(grid, posterior, windows, "a")

    return None


def _live_classes(posterior: list[float], labels: list[str], floor: float = 1e-4):
    mass = _class_mass(posterior, labels)
    return {k: v for k, v in mass.items() if v >= floor}


def _class_windows(labels: list[str], cls: str) -> list[tuple[int, int]]:
    return _runs([i for i in range(N_GRID) if labels[i] == cls])


def _spans(labels, cls):
    return [
        {"start": minute_to_time(a), "end": minute_to_time(b)}
        for a, b in _class_windows(labels, cls)
    ]


def _sign_question(grid, posterior, labels, variant) -> dict:
    facet = VARIANT_FACET["rising_sign"][variant]
    live = _live_classes(posterior, labels)
    options = [
        {
            "answer_id": sign,
            "mass": round(live[sign], 6),
            "spans": _spans(labels, sign),
            "description_keys": [f"sign.{sign}.{facet}"],
        }
        for sign in sorted(live, key=lambda s: -live[s])
    ]
    return {
        "question_id": f"stage1_rising_sign_{variant}",
        "channel": "rising_sign",
        "subject": None,
        "variant": variant,
        "facet": facet,
        "stage": 1,
        "select": "one_or_two",
        "information_bits": round(_partition_gain(posterior, labels), 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _decan_question(grid, posterior, labels, variant) -> dict:
    facet = VARIANT_FACET["decan"][variant]
    live = _live_classes(posterior, labels)
    options = []
    for cls in sorted(live, key=lambda s: -live[s]):
        sign, decan = cls.rsplit("_", 1)
        options.append(
            {
                "answer_id": cls,
                "mass": round(live[cls], 6),
                "spans": _spans(labels, cls),
                "description_keys": [f"decan.{sign}.{decan}.{facet}"],
            }
        )
    return {
        "question_id": f"stage2_decan_{variant}",
        "channel": "decan",
        "subject": None,
        "variant": variant,
        "facet": facet,
        "stage": 2,
        "select": "one",
        "information_bits": round(_partition_gain(posterior, labels), 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _mover_question(grid, posterior, planet, gain, variant) -> dict:
    facet = VARIANT_FACET["mover_house"][variant]
    labels = partition_for(grid, "mover_house", planet)
    live = _live_classes(posterior, labels)
    options = [
        {
            "answer_id": house,
            "mass": round(live[house], 6),
            "spans": _spans(labels, house),
            "description_keys": [f"planet.{planet}.house.{house}.{facet}"],
        }
        for house in sorted(live, key=lambda h: int(h))
    ]
    return {
        "question_id": f"stage3_mover_{planet}_{variant}",
        "channel": "mover_house",
        "subject": planet,
        "variant": variant,
        "facet": facet,
        "stage": 3,
        "select": "one",
        "information_bits": round(gain, 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _portrait_question(grid, posterior, windows, variant) -> dict:
    options = []
    for idx, w in enumerate(windows):
        mid = window_midpoint(w)
        options.append(
            {
                "answer_id": f"w{idx}",
                "mass": round(window_mass(posterior, w), 6),
                "spans": [{"start": minute_to_time(w[0]), "end": minute_to_time(w[1])}],
                "ascendant_sign": grid.asc_sign[mid],
                "planet_houses": {n: grid.planet_house[n][mid] for n, _ in core.PLANETS},
                "description_keys": [f"portrait.window.{idx}"],
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
        "select": "one",
        "information_bits": round(
            _entropy_bits({o["answer_id"]: o["mass"] for o in options}), 4
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
                  hypothesis: dict | None = None) -> dict:
    cfg = cfg or InterviewConfig()
    grid = ChartGrid(birth_date, lat, lon, tz, cfg.house_system)
    posterior, trace, pairs = build_posterior(
        grid, answers, cfg, known_bounds, claimed_time
    )
    tier = assign_tier(posterior, trace, cfg, pairs)
    question = next_question(grid, posterior, answers, cfg, sphere_inventory)

    answered = [t for t in trace if t["answer_ids"]]
    result = {
        "tier": tier["tier"],
        "tier_reason": tier["reason"],
        "rising_sign": tier["rising_sign"],
        "windows": tier["windows"],
        "coherence": tier["coherence"],
        "next_question": question,
        "posterior_summary": {
            "peak_time": minute_to_time(max(range(N_GRID), key=lambda i: posterior[i])),
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

    return result


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
