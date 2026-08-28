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
  answer is unrecoverable. `cannot_choose` multiplies nothing at all.
* **Every numeric decision lives here.** The calling client's only job is to
  phrase a question and map free text onto one of the enumerated answer ids
  this module emits. Answers are enum ids and nothing else; anything else is
  rejected by the schema. This project has twice been burned by a host model
  quietly making a numeric decision, and the contract is shaped so that it
  cannot happen again.
* **Windows, never bare times.** A Tier 1 or Tier 2 answer always carries its
  bounds. The measured ceiling for this architecture is a median of about six
  minutes with roughly half of cases inside +/-5, so a bare minute would be a
  confident wrong answer roughly half the time.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Iterable

import swisseph as swe

from . import core

GRID_STEP_MINUTES = 1
GRID_MINUTES = list(range(0, 24 * 60, GRID_STEP_MINUTES))
N_GRID = len(GRID_MINUTES)

# Planet longitudes are sampled hourly and linearly interpolated to the minute.
# The fastest body, the Moon, moves about 0.55 degrees per hour, so the
# interpolation error over a one-hour span is below a thousandth of a degree -
# far under the resolution at which a house boundary matters. House cusps are
# NOT interpolated: they move about a quarter degree per minute and are
# computed exactly at every candidate.
LONGITUDE_SAMPLE_MINUTES = 60

CHANNELS = ("rising_sign", "decan", "mover_house", "portrait")

DECAN_NAMES = ("first", "second", "third")


class InterviewConfig:
    """Frozen numeric policy. Defaults are the values the gates were run at.

    `tier1_chance_p` was moved from 0.05 to 0.002 by the single permitted
    retune, searched on the train split only and logged in
    `benchmarks/interview_retune.json`. It did not rescue G1; the retune is
    spent and the threshold is not renegotiable. See RESULTS_INTERVIEW.md.
    """

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
    )

    def __init__(
        self,
        channel_reliability: float = 0.75,
        tier1_mass: float = 0.60,
        tier2_mass: float = 0.60,
        tier1_chance_p: float = 0.002,
        tier2_chance_p: float = 0.20,
        tier1_window_minutes: int = 30,
        min_information_bits: float = 0.15,
        max_mover_questions: int = 3,
        house_system: str = "placidus",
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
            # Unwrap so interpolation does not cross the 360/0 boundary.
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
# Posterior
# --------------------------------------------------------------------------


def _partition_rising_sign(grid: ChartGrid) -> list[str]:
    return grid.asc_sign


def _partition_decan(grid: ChartGrid) -> list[str]:
    return [f"{grid.asc_sign[i]}_{DECAN_NAMES[grid.asc_decan[i]]}" for i in range(N_GRID)]


def _partition_mover(grid: ChartGrid, planet: str) -> list[str]:
    return [str(h) for h in grid.planet_house[planet]]


def partition_for(grid: ChartGrid, channel: str, subject: str | None,
                  windows: list[tuple[int, int]] | None = None) -> list[str]:
    """The class label of every candidate under one channel."""
    if channel == "rising_sign":
        return _partition_rising_sign(grid)
    if channel == "decan":
        return _partition_decan(grid)
    if channel == "mover_house":
        return _partition_mover(grid, subject or "")
    if channel == "portrait":
        labels = ["none"] * N_GRID
        for idx, (lo, hi) in enumerate(windows or []):
            # A window that spans midnight is stored with hi >= N_GRID, so the
            # index must wrap rather than run off the end of the day.
            for i in range(lo, hi + 1):
                labels[i % N_GRID] = f"w{idx}"
        return labels
    raise ValueError(f"unknown channel {channel!r}")


def apply_answer(weights: list[float], labels: list[str], chosen: list[str],
                 reliability: float) -> list[float]:
    """Multiply weights by the likelihood of this answer.

    The likelihood is the standard one for an answerer who is right with
    probability `reliability` and otherwise picks uniformly among the other
    classes. Written as a ratio against the matching case, so matching
    candidates keep their weight and non-matching ones are multiplied by a
    strictly positive factor below one. Nothing ever reaches zero.

    An empty `chosen` - the `cannot_choose` answer - multiplies nothing.
    """
    if not chosen:
        return list(weights)

    classes = set(labels)
    k = len(classes)
    picked = set(chosen) & classes
    others = k - len(picked)
    if not picked or others <= 0:
        # The answer names no class present, or every class: no information.
        return list(weights)

    r = min(max(reliability, 1e-6), 1.0 - 1e-6)
    factor = (1.0 - r) / (r * others)
    return [
        w if labels[i] in picked else w * factor for i, w in enumerate(weights)
    ]


def normalise(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return [1.0 / len(weights)] * len(weights)
    return [w / total for w in weights]


def build_posterior(grid: ChartGrid, answers: Iterable[dict], cfg: InterviewConfig):
    """Replay every answer over a uniform prior. Returns (posterior, trace)."""
    weights = [1.0] * N_GRID
    trace = []
    windows_at_portrait: list[tuple[int, int]] | None = None

    for ans in answers:
        channel = ans["channel"]
        if channel == "portrait":
            windows_at_portrait = [tuple(w) for w in ans.get("windows", [])]
        labels = partition_for(
            grid, channel, ans.get("subject"), windows_at_portrait
        )
        chosen = list(ans.get("answer_ids", []))
        before = normalise(weights)
        weights = apply_answer(weights, labels, chosen, cfg.channel_reliability)
        supported = [i for i in range(N_GRID) if labels[i] in set(chosen)] if chosen else []
        trace.append(
            {
                "channel": channel,
                "subject": ans.get("subject"),
                "answer_ids": chosen,
                "class_count": len(set(labels)),
                "supported_fraction": len(supported) / N_GRID,
                "supported": supported,
                "labels": labels,
                "prior_entropy_bits": _entropy_bits(_class_mass(before, labels)),
            }
        )
    return normalise(weights), trace


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


# --------------------------------------------------------------------------
# Windows and credible sets
# --------------------------------------------------------------------------


def credible_windows(posterior: list[float], mass: float) -> list[tuple[int, int]]:
    """Highest-weight-first credible set, grouped into contiguous runs.

    Ties are taken whole. Answers partition the grid, so every candidate the
    answers agree on carries *exactly* the same weight - a perfect answerer
    produces one flat plateau, not a peak. Cutting such a plateau at whatever
    index the running mass happens to cross the threshold would drop part of
    the agreed region arbitrarily, and can exclude the true minute even when
    every answer was correct. That was a real failure before this was fixed.
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
    # Join a run touching midnight at both ends of the day.
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

    Each answered channel partitions the grid. A random answerer picks one
    class per channel uniformly. Enumerating every profile - the product of the
    class counts, a few hundred at most - gives the exact distribution of the
    intersection size. The reported probability is the fraction of profiles
    whose intersection is non-empty and no larger than the observed one.

    A small observed intersection is only evidence of agreement if random
    answers rarely produce one. This is the number that says whether they do.
    """
    informative = [t for t in trace if t["answer_ids"] and t["supported"]]
    if not informative:
        return 1.0, 0

    observed = set(range(N_GRID))
    for t in informative:
        observed &= set(t["supported"])
    observed_size = len(observed)

    # An empty intersection is the *absence* of agreement, not a very sharp
    # one. Scoring it as agreement was letting random answers through as
    # Tier 1: inconsistent answers agree nowhere, which is the opposite of
    # evidence.
    if observed_size == 0:
        return 1.0, 0

    # Enumerating answer profiles is exponential and needlessly so. A profile
    # produces a non-empty intersection if and only if it equals the signature
    # of some candidate minute - the tuple of that minute's class in every
    # channel - and the intersection is then exactly that signature's cell.
    # So the whole distribution is read off the joint partition in one pass,
    # and each cell has the same probability, the product of 1/k over channels.
    signature_sizes: dict[tuple, int] = {}
    for i in range(N_GRID):
        sig = tuple(t["labels"][i] for t in informative)
        signature_sizes[sig] = signature_sizes.get(sig, 0) + 1

    profile_probability = 1.0
    for t in informative:
        profile_probability /= max(t["class_count"], 1)

    reachable = sum(
        1 for size in signature_sizes.values() if size <= max(observed_size, 1)
    )
    return min(reachable * profile_probability, 1.0), observed_size


def concentration(posterior: list[float]) -> float:
    """1 - normalised entropy. 0 is a flat day, 1 is a single minute."""
    h = -sum(p * math.log2(p) for p in posterior if p > 0)
    return 1.0 - h / math.log2(N_GRID)


# --------------------------------------------------------------------------
# Tiers
# --------------------------------------------------------------------------


def assign_tier(posterior: list[float], trace: list[dict], cfg: InterviewConfig) -> dict:
    chance_p, overlap = chance_agreement(trace)
    conc = concentration(posterior)

    t1 = credible_windows(posterior, cfg.tier1_mass)
    single_ok = (
        len(t1) == 1
        and window_minutes(t1[0]) <= cfg.tier1_window_minutes
        and window_mass(posterior, t1[0]) >= cfg.tier1_mass
        and not math.isnan(chance_p)
        and chance_p < cfg.tier1_chance_p
    )
    if single_ok:
        return _tier_result(1, t1, posterior, conc, chance_p, overlap,
                            "single window with independent channel agreement")

    # Tier 2 needs agreement too, only looser. Without it "two or three narrow
    # windows carry the mass" is a statement about concentration alone, which
    # random answering also produces - it was the route by which the random
    # answerer was being handed a shortlist.
    t2 = credible_windows(posterior, cfg.tier2_mass)
    if (
        1 <= len(t2) <= 3
        and sum(window_mass(posterior, w) for w in t2) >= cfg.tier2_mass
        and not math.isnan(chance_p)
        and chance_p < cfg.tier2_chance_p
    ):
        widths = [window_minutes(w) for w in t2]
        if max(widths) <= cfg.tier1_window_minutes * 3:
            return _tier_result(2, t2, posterior, conc, chance_p, overlap,
                                "two or three windows carry the mass")

    # Tier 3 needs some information, from any channel - not specifically the
    # rising-sign question. A `cannot_choose` on stage 1 must not push someone
    # to refusal when their other answers still say something; the hard
    # constraint is that declining to answer never costs more than the
    # information that answer would have carried.
    informative = [t for t in trace if t["answer_ids"]]
    if informative:
        labels = _partition_rising_sign_labels(posterior, trace)
        sign_mass = _class_mass(posterior, labels) if labels else {}
        best_sign = max(sign_mass, key=sign_mass.get) if sign_mass else None
        return _tier_result(
            3, [], posterior, conc, chance_p, overlap,
            "channels agree only at the level of the rising sign",
            rising_sign=best_sign,
        )

    return _tier_result(4, [], posterior, conc, chance_p, overlap,
                        "the method cannot work from these answers")


def _partition_rising_sign_labels(posterior, trace) -> list[str]:
    for t in trace:
        if t["channel"] == "rising_sign":
            return t["labels"]
    return []


def _tier_result(tier, windows, posterior, conc, chance_p, overlap, reason,
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
            "chance_agreement_p": None if math.isnan(chance_p) else round(chance_p, 6),
            "channel_overlap_minutes": overlap,
        },
    }


# --------------------------------------------------------------------------
# Question generation
# --------------------------------------------------------------------------


def _partition_gain(posterior: list[float], labels: list[str]) -> float:
    return _entropy_bits(_class_mass(posterior, labels))


def next_question(grid: ChartGrid, posterior: list[float], answers: list[dict],
                  cfg: InterviewConfig) -> dict | None:
    """The next question, chosen by expected information gain over geometry."""
    asked = {(a["channel"], a.get("subject")) for a in answers}

    if ("rising_sign", None) not in asked:
        labels = partition_for(grid, "rising_sign", None)
        return _sign_question(grid, posterior, labels)

    if ("decan", None) not in asked:
        labels = partition_for(grid, "decan", None)
        if _partition_gain(posterior, labels) >= cfg.min_information_bits:
            return _decan_question(grid, posterior, labels)

    movers = [a for a in answers if a["channel"] == "mover_house"]
    if len(movers) < cfg.max_mover_questions:
        best, best_gain = None, 0.0
        for name, _ in core.PLANETS:
            if ("mover_house", name) in asked:
                continue
            labels = partition_for(grid, "mover_house", name)
            gain = _partition_gain(posterior, labels)
            if gain > best_gain:
                best, best_gain = name, gain
        if best and best_gain >= cfg.min_information_bits:
            return _mover_question(grid, posterior, best, best_gain)

    windows = credible_windows(posterior, cfg.tier2_mass)
    if 2 <= len(windows) <= 4 and ("portrait", None) not in asked:
        return _portrait_question(grid, posterior, windows)

    return None


def _live_classes(posterior: list[float], labels: list[str], floor: float = 1e-4):
    mass = _class_mass(posterior, labels)
    return {k: v for k, v in mass.items() if v >= floor}


def _class_windows(labels: list[str], cls: str) -> list[tuple[int, int]]:
    return _runs([i for i in range(N_GRID) if labels[i] == cls])


def _sign_question(grid, posterior, labels) -> dict:
    live = _live_classes(posterior, labels)
    options = []
    for sign in sorted(live, key=lambda s: -live[s]):
        spans = _class_windows(labels, sign)
        options.append(
            {
                "answer_id": sign,
                "mass": round(live[sign], 6),
                "spans": [
                    {"start": minute_to_time(a), "end": minute_to_time(b)}
                    for a, b in spans
                ],
                "description_keys": [
                    f"sign.{sign}.psychological",
                    f"sign.{sign}.appearance",
                    f"sign.{sign}.values",
                ],
            }
        )
    return {
        "question_id": "stage1_rising_sign",
        "channel": "rising_sign",
        "subject": None,
        "stage": 1,
        "select": "one_or_two",
        "information_bits": round(_partition_gain(posterior, labels), 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _decan_question(grid, posterior, labels) -> dict:
    live = _live_classes(posterior, labels)
    options = []
    for cls in sorted(live, key=lambda s: -live[s]):
        sign, decan = cls.rsplit("_", 1)
        spans = _class_windows(labels, cls)
        options.append(
            {
                "answer_id": cls,
                "mass": round(live[cls], 6),
                "spans": [
                    {"start": minute_to_time(a), "end": minute_to_time(b)}
                    for a, b in spans
                ],
                "description_keys": [
                    f"decan.{sign}.{decan}.appearance",
                    f"decan.{sign}.{decan}.manner",
                ],
            }
        )
    return {
        "question_id": "stage2_decan",
        "channel": "decan",
        "subject": None,
        "stage": 2,
        "select": "one",
        "information_bits": round(_partition_gain(posterior, labels), 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _mover_question(grid, posterior, planet, gain) -> dict:
    labels = partition_for(grid, "mover_house", planet)
    live = _live_classes(posterior, labels)
    options = []
    for house in sorted(live, key=lambda h: int(h)):
        spans = _class_windows(labels, house)
        options.append(
            {
                "answer_id": house,
                "mass": round(live[house], 6),
                "spans": [
                    {"start": minute_to_time(a), "end": minute_to_time(b)}
                    for a, b in spans
                ],
                "description_keys": [
                    f"planet.{planet}.house.{house}.life_area",
                    f"planet.{planet}.house.{house}.expression",
                ],
            }
        )
    return {
        "question_id": f"stage3_mover_{planet}",
        "channel": "mover_house",
        "subject": planet,
        "stage": 3,
        "select": "one",
        "information_bits": round(gain, 4),
        "options": options,
        "allow_cannot_choose": True,
    }


def _portrait_question(grid, posterior, windows) -> dict:
    options = []
    for idx, w in enumerate(windows):
        mid = window_midpoint(w)
        placements = {
            name: grid.planet_house[name][mid] for name, _ in core.PLANETS
        }
        options.append(
            {
                "answer_id": f"w{idx}",
                "mass": round(window_mass(posterior, w), 6),
                "spans": [{"start": minute_to_time(w[0]), "end": minute_to_time(w[1])}],
                "ascendant_sign": grid.asc_sign[mid],
                "planet_houses": placements,
                "description_keys": [f"portrait.window.{idx}"],
            }
        )
    # Only the placements that actually differ are worth showing.
    differing = [
        name
        for name, _ in core.PLANETS
        if len({o["planet_houses"][name] for o in options}) > 1
    ]
    for o in options:
        o["distinguishing_placements"] = {
            n: o["planet_houses"][n] for n in differing
        }
    return {
        "question_id": "stage4_portrait",
        "channel": "portrait",
        "subject": None,
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
                  answers: list[dict], cfg: InterviewConfig | None = None) -> dict:
    cfg = cfg or InterviewConfig()
    grid = ChartGrid(birth_date, lat, lon, tz, cfg.house_system)
    posterior, trace = build_posterior(grid, answers, cfg)
    tier = assign_tier(posterior, trace, cfg)
    question = next_question(grid, posterior, answers, cfg)

    answered = [t for t in trace if t["answer_ids"]]
    telemetry = {
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
        "window_widths": [w["width_minutes"] for w in tier["windows"]],
        "selection": "interval_midpoint",
    }

    return {
        "tier": tier["tier"],
        "tier_reason": tier["reason"],
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
                "supported_minutes": len(t["supported"]),
                "class_count": t["class_count"],
            }
            for t in trace
        ],
        "telemetry": telemetry,
    }
