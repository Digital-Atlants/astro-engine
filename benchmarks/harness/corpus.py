"""Load and validate the ground-truth corpus fixtures."""

from __future__ import annotations

import datetime as dt
import json
import pathlib

CORPUS_DIR = pathlib.Path(__file__).resolve().parent.parent / "corpus"

VALID_PRECISION = {"day", "month", "year"}
VALID_TYPES = {
    "marriage",
    "relocation",
    "death_of_close",
    "career_break",
    "child_birth",
    "accident",
    "surgery",
    "other",
}


class Case(dict):
    """A corpus case. Dict subclass so it stays trivially JSON-serialisable."""

    @property
    def case_id(self) -> str:
        return self["case_id"]

    @property
    def known_minute(self) -> int:
        hh, mm = map(int, self["known_time"].split(":"))
        return hh * 60 + mm

    @property
    def birth_date(self) -> dt.date:
        return dt.date.fromisoformat(self["birth_date"])

    def lifespan_bounds(self) -> tuple[dt.date, dt.date]:
        """Earliest and latest event date, used to draw null-arm dates."""
        dates = [dt.date.fromisoformat(e["date"]) for e in self["events"]]
        return min(dates), max(dates)


def _validate(case: dict, path: pathlib.Path) -> None:
    required = {
        "case_id",
        "name",
        "birth_date",
        "known_time",
        "rodden_rating",
        "rodden_source",
        "source_url",
        "place",
        "events",
        "known_time_is_round",
        "spread_flags",
    }
    missing = required - case.keys()
    if missing:
        raise ValueError(f"{path.name}: missing keys {sorted(missing)}")
    if case["rodden_rating"] != "AA":
        raise ValueError(f"{path.name}: Rodden rating {case['rodden_rating']!r}, only AA is admitted")
    if not 6 <= len(case["events"]) <= 12:
        raise ValueError(f"{path.name}: {len(case['events'])} events, must be 6..12")
    for key in ("lat", "lon", "tz"):
        if key not in case["place"]:
            raise ValueError(f"{path.name}: place is missing {key!r}")
    seen = set()
    for e in case["events"]:
        if e["date_precision"] not in VALID_PRECISION:
            raise ValueError(f"{path.name}: bad date_precision {e['date_precision']!r}")
        if e["type"] not in VALID_TYPES:
            raise ValueError(f"{path.name}: bad event type {e['type']!r}")
        dt.date.fromisoformat(e["date"])
        if e["id"] in seen:
            raise ValueError(f"{path.name}: duplicate event id {e['id']!r}")
        seen.add(e["id"])


def load_corpus(corpus_dir: pathlib.Path | None = None) -> list[Case]:
    """Every case in the corpus, ordered by case_id for determinism."""
    directory = corpus_dir or CORPUS_DIR
    cases = []
    for path in sorted(directory.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        _validate(case, path)
        cases.append(Case(case))
    if not cases:
        raise ValueError(f"no corpus fixtures found in {directory}")
    return cases


def spread_summary(cases: list[Case]) -> dict:
    """Counts behind the Work-item-1.3 spread rules."""
    return {
        "cases": len(cases),
        "night_births": sum(1 for c in cases if c["spread_flags"]["night_birth"]),
        "high_latitude": sum(1 for c in cases if c["spread_flags"]["high_latitude"]),
        "near_equator": sum(1 for c in cases if c["spread_flags"]["near_equator"]),
        "round_known_times": sum(1 for c in cases if c["known_time_is_round"]),
    }
