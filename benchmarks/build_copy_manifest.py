"""Emit every copy key the engine can ask, and bind each to its Russian text.

The direction of this script reversed in v3.3. Through v3.2 it *generated*
`docs/copy_drafts.md` from templates held in this file, and the owner was
expected to correct the output. The copy is now authored: `docs/copy_drafts.md`
is the council-approved file and this script **reads** it, resolving every
engine key to the Russian row behind it.

Two artefacts, both derived:

  * `astro_engine/data/copy_manifest.json` - every key, per channel, with the
    distinction it draws and the approved Russian text that fills it.
  * a coverage verdict on stdout, and a non-zero exit if any key the engine
    can emit has no approved Russian row.

The engine owns the key list; the council owns the text; this script is the
join, and it fails rather than let the two drift apart silently.

    python benchmarks/build_copy_manifest.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from astro_engine import core, interview  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "astro_engine" / "data" / "copy_manifest.json"
DRAFTS = ROOT / "docs" / "copy_drafts.md"

# Russian is the only locale the web imports. The en / uk / de columns in the
# drafts file are v3.2 drafts carried forward and carry no status of their own;
# the translation task replaces them from the approved Russian.
MASTER_LOCALE = "ru"
LOCALES = ("en", "ru", "uk", "de")

# Keys the approved copy file does not claim to cover, with the reason. The
# coverage check treats this set as exact: a key missing from the file and
# absent from here fails the build, and a key listed here that the file *does*
# cover also fails it, so an exemption cannot quietly outlive its reason.
#
# `portrait.window.N` labels one surviving time window against another. The
# client renders it from the placements the engine returns in
# `distinguishing_placements` rather than from a fixed sentence, which is why
# the council's file has no row for it. If that ever changes, this fires.
UNCOVERED = {f"portrait.window.{i}" for i in range(interview.MAX_PORTRAIT_OPTIONS)}

DECAN_ORDINAL = {"first": "the first third", "second": "the middle third",
                 "third": "the last third"}

HOUSE_MEANING = {
    1: ("the body and first impression", "how you come across before you speak"),
    2: ("what you own and earn", "money, possessions, and what you value"),
    3: ("everyday exchange", "siblings, short trips, talk and study"),
    4: ("home and origins", "family, the place you come from, the end of things"),
    5: ("what you make and enjoy", "children, play, romance, performance"),
    6: ("work and health", "daily duty, service, illness and routine"),
    7: ("one-to-one", "partnership, marriage, open opponents"),
    8: ("what is shared or lost", "other people's money, crisis, death, the hidden"),
    9: ("the far and the abstract", "long journeys, belief, higher study, law"),
    10: ("standing in the world", "career, reputation, the public role"),
    11: ("the wider circle", "friends, groups, hopes and alliances"),
    12: ("what is withdrawn", "seclusion, hospitals, confinement, private undoing"),
}

PLANET_MEANING = {
    "sun": "vitality and purpose",
    "moon": "feeling, habit and need",
    "mercury": "thinking and talking",
    "venus": "affection, taste and worth",
    "mars": "drive, anger and effort",
    "jupiter": "growth, luck and belief",
    "saturn": "limit, duty and time",
    "uranus": "disruption and independence",
    "neptune": "dissolution, longing and imagination",
    "pluto": "compulsion, power and remaking",
}


# --------------------------------------------------------------------------
# Reading the approved file
# --------------------------------------------------------------------------


def _rows(text: str) -> list[list[str]]:
    """Every markdown table row in the file, as trimmed cells."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(c and set(c) <= {"-", ":"} for c in cells):
            continue  # separator row
        out.append(cells)
    return out


class ApprovedCopy:
    """The council's Russian atoms, parsed out of `docs/copy_drafts.md`.

    Sections are recognised by their shape - column count and what the first
    cell is - rather than by heading text, so re-wording a heading does not
    silently drop a block of copy.
    """

    def __init__(self, text: str):
        self.direct: dict[str, dict[str, str]] = {}   # key -> {locale: text}
        self.houses: dict[int, str] = {}
        self.planets: dict[str, str] = {}
        self.decans: dict[tuple[str, str], str] = {}
        self.templates: dict[str, str] = {}

        signs = set(interview.TRAIT_SIGNS)
        thirds = set(interview.DECAN_NAMES)
        planets = {name for name, _ in core.PLANETS}

        for cells in _rows(text):
            if cells[-1] != "approved":
                continue
            head = cells[0].strip("`")
            if len(cells) == 7 and "." in head:
                # Stage 1 and portraits: key | distinguishes | en | ru | uk | de
                self.direct[head] = dict(zip(LOCALES, cells[2:6]))
            elif (len(cells) == 4 and head in signs
                    and cells[1].split()[0] in thirds):
                self.decans[(head, cells[1].split()[0])] = cells[2]
            elif len(cells) == 3 and head.isdigit():
                self.houses[int(head)] = cells[1]
            elif len(cells) == 3 and head in planets:
                self.planets[head] = cells[1]
            elif len(cells) == 3 and "." in head:
                self.templates[head] = cells[1]

    def atom_count(self) -> int:
        return (len(self.direct) + len(self.houses) + len(self.planets)
                + len(self.decans) + len(self.templates))

    def russian_for(self, entry: dict) -> str | None:
        """The approved Russian for one engine key, composed where needed.

        Only the A slot of each template is filled here. A live question pairs
        two atoms from the same channel, and which two depends on the
        posterior, so the manifest records the half that is fixed: this key's
        own atom in its own template.
        """
        key, channel = entry["key"], entry["channel"]
        if channel in ("element", "modality", "sign_portrait"):
            return (self.direct.get(key) or {}).get(MASTER_LOCALE) or None
        if channel == "decan":
            _, sign, third, facet = key.split(".")
            atom = self.decans.get((sign, third))
            template = self.templates.get(f"decan.{facet}")
            if not atom or not template:
                return None
            return template.replace("[черта декана A]", atom)
        if channel == "mover_house":
            _, planet, _, house, facet = key.split(".")
            theme = self.planets.get(planet)
            sphere = self.houses.get(int(house))
            template = self.templates.get(f"mover_house.{facet}")
            if not theme or not sphere or not template:
                return None
            return (template.replace("[тема планеты]", theme)
                            .replace("[сфера A]", sphere))
        return None


# --------------------------------------------------------------------------
# The key list, which the engine owns
# --------------------------------------------------------------------------


def build_entries() -> list[dict]:
    entries: list[dict] = []

    for tag_id in interview.ELEMENT_TAGS + interview.MODALITY_TAGS:
        tag = interview.TRAIT_TAGS[tag_id]
        strong = sorted(s for s, v in tag["likelihood"].items() if v >= 0.6)
        for kind in ("label_key", "paraphrase_key"):
            entries.append({
                "key": tag[kind],
                "channel": tag["channel"],
                "variant": "a" if kind == "label_key" else "b",
                "answer_id": tag_id,
                "distinguishes": f"{', '.join(strong)} from the other signs",
            })

    for sign in interview.TRAIT_SIGNS:
        for facet in ("portrait", "portrait_contrast"):
            entries.append({
                "key": f"sign.{sign}.{facet}",
                "channel": "sign_portrait",
                "variant": "a" if facet == "portrait" else "b",
                "answer_id": sign,
                "distinguishes": f"{sign} rising from the one other sign offered",
            })

    for sign in interview.TRAIT_SIGNS:
        for decan in interview.DECAN_NAMES:
            for facet in ("manner", "appearance"):
                entries.append({
                    "key": f"decan.{sign}.{decan}.{facet}",
                    "channel": "decan",
                    "variant": "a" if facet == "manner" else "b",
                    "answer_id": f"{sign}_{decan}",
                    "distinguishes": (
                        f"{DECAN_ORDINAL[decan]} of {sign} rising from the "
                        "other thirds of the same sign"
                    ),
                })

    for planet, _ in core.PLANETS:
        for house in range(1, 13):
            area, detail = HOUSE_MEANING[house]
            for facet in ("life_area", "episode"):
                entries.append({
                    "key": f"planet.{planet}.house.{house}.{facet}",
                    "channel": "mover_house",
                    "variant": "a" if facet == "life_area" else "b",
                    "answer_id": str(house),
                    "distinguishes": (
                        f"{planet} ({PLANET_MEANING[planet]}) in house {house} "
                        f"- {area}: {detail} - from the same planet in the "
                        "one or two neighbouring houses"
                    ),
                })

    for idx in range(interview.MAX_PORTRAIT_OPTIONS):
        entries.append({
            "key": f"portrait.window.{idx}",
            "channel": "portrait",
            "variant": "a",
            "answer_id": f"w{idx}",
            "distinguishes": (
                "one surviving time window from the others, by the placements "
                "returned in `distinguishing_placements`"
            ),
        })

    return entries


def build_manifest(copy: ApprovedCopy) -> tuple[dict, list[str], list[str]]:
    entries = build_entries()
    missing: list[str] = []
    unexpected: list[str] = []
    for e in entries:
        ru = copy.russian_for(e)
        e["ru"] = ru or ""
        e["status"] = "approved" if ru else "no_russian_row"
        if ru and e["key"] in UNCOVERED:
            unexpected.append(e["key"])
        if not ru and e["key"] not in UNCOVERED:
            missing.append(e["key"])

    by_channel: dict[str, int] = {}
    for e in entries:
        by_channel[e["channel"]] = by_channel.get(e["channel"], 0) + 1

    manifest = {
        "_README": (
            "Every copy key the interview engine can emit, with the approved "
            "Russian text behind it. The web client auto-skips a question "
            "whose keys have no authored copy, so a key with status "
            "no_russian_row is a question the live interview cannot ask. "
            "Generated by benchmarks/build_copy_manifest.py from "
            "docs/copy_drafts.md, which is the council-approved source."
        ),
        "master_locale": MASTER_LOCALE,
        "locales": list(LOCALES),
        "total_keys": len(entries),
        "keys_by_channel": by_channel,
        "approved_keys": sum(1 for e in entries if e["status"] == "approved"),
        "keys_without_russian": sorted(
            e["key"] for e in entries if e["status"] != "approved"
        ),
        "entries": entries,
    }
    return manifest, missing, unexpected


def main() -> int:
    copy = ApprovedCopy(DRAFTS.read_text(encoding="utf-8"))
    manifest, missing, unexpected = build_manifest(copy)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"approved Russian atoms read: {copy.atom_count()}")
    print(f"  stage 1 and portraits {len(copy.direct)}, houses {len(copy.houses)}, "
          f"planet themes {len(copy.planets)}, decans {len(copy.decans)}, "
          f"templates {len(copy.templates)}")
    print(f"engine keys: {manifest['total_keys']}, "
          f"with approved Russian: {manifest['approved_keys']}")
    for ch, n in sorted(manifest["keys_by_channel"].items()):
        covered = sum(
            1 for e in manifest["entries"]
            if e["channel"] == ch and e["status"] == "approved"
        )
        print(f"  {ch:16} {covered}/{n}")
    print(f"declared uncovered: {sorted(UNCOVERED)}")
    print(f"wrote {MANIFEST}")

    if missing:
        print(f"\nFAIL: {len(missing)} engine key(s) have no approved Russian "
              "row and are not declared uncovered:", file=sys.stderr)
        for key in missing[:20]:
            print(f"  {key}", file=sys.stderr)
        return 1
    if unexpected:
        print(f"\nFAIL: {len(unexpected)} key(s) are declared uncovered but the "
              "copy file now covers them; remove them from UNCOVERED:",
              file=sys.stderr)
        for key in unexpected:
            print(f"  {key}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
