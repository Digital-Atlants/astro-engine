"""Work item 3.2/3.3: turn the evidence sentences into sourced answers.

Answers are derived by explicit committed rules over the redacted biography,
not from recall. Every `yes` and every `no` records the sentence that produced
it. This is mechanical extraction, and it is described as such in the report:
it is auditable and reproducible, which recall is not.

Two codings are produced, because the choice matters and should not be hidden:

* **strict** - the literal Work item 3.3 rule. An answer is `yes` or `no` only
  when a sentence in the biography states it. Everything else is `unknown`.
* **documented_absence** - additionally, for the rare-event items flagged
  below, a full biography that never mentions the event at all is read as
  `no`. For a public figure with a 40,000+ character biography, silence about
  emigration or the death of a child is weak evidence of absence rather than
  no evidence. Items where silence is genuinely uninformative (wealth,
  poverty, unemployment, childlessness) never take this route.

The gate is reported under both.

    python benchmarks/extract_answers.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.extract_probe import BIO_DIR, sentences  # noqa: E402
from benchmarks.harness import corpus  # noqa: E402

EVIDENCE = pathlib.Path(__file__).resolve().parent / "fixtures" / "predisposition_evidence.json"
OUT = pathlib.Path(__file__).resolve().parent / "fixtures" / "predisposition_answers.json"

# item -> (yes patterns, explicit-no patterns, silence_means_no)
RULES: dict[str, tuple[list[str], list[str], bool]] = {
    "many marriages": (
        [r"\b(?:third|fourth|fifth|sixth|seventh|eighth)\s+(?:wife|husband|marriage)\b",
         r"\bmarried\s+(?:for\s+the\s+)?(?:a\s+)?(?:third|fourth|fifth)\s+time\b"],
        [r"\bnever married\b", r"\bremained (?:un|single)", r"\bdid not marry\b"],
        True,
    ),
    "childlessness or a late child": (
        [r"\bchildless\b", r"\b(?:had|have) no children\b", r"\bno children\b"],
        [r"\b(?:their|his|her) (?:son|daughter|child|children)\b", r"\bgave birth\b"],
        False,
    ),
    "adopted children": (
        [r"\badopted\s+(?:a\s+|two\s+|three\s+|four\s+|his\s+|her\s+|their\s+|the\s+)?"
         r"(?:son|daughter|child|children|baby|girl|boy)\b",
         r"\badoption of (?:a|his|her|their)\b"],
        [],
        True,
    ),
    "separation from a child": (
        [r"\bcustody (?:battle|dispute|of)\b", r"\blost custody\b",
         r"\bestranged from (?:his|her|their) (?:son|daughter|child|children)\b",
         r"\bplaced (?:in|into) (?:an? )?(?:orphanage|foster)\b",
         r"\bsent to (?:an? )?orphanage\b"],
        [],
        True,
    ),
    "death of a child": (
        [r"\b(?:son|daughter|child)\b[^.]{0,80}\bdied\b",
         r"\bdeath of (?:his|her|their) (?:son|daughter|child)\b",
         r"\bstillborn\b"],
        [],
        True,
    ),
    "emigration": (
        [r"\bemigrat", r"\bimmigrated to\b", r"\bdefected\b", r"\bin exile\b",
         r"\bfled (?:to|the country)\b", r"\bnaturali[sz]ed\b"],
        [],
        True,
    ),
    "success in science": (
        [r"\bNobel Prize in (?:Physics|Chemistry|Physiology)\b",
         r"\bis an? (?:American |British |French )?scientist\b",
         r"\bhis scientific (?:work|research)\b", r"\bher scientific (?:work|research)\b"],
        [],
        True,
    ),
    "success in religious work": (
        [r"\bordained\b", r"\bas a (?:pastor|preacher|missionary|minister of religion)\b",
         r"\bmissionary\b"],
        [],
        True,
    ),
    "unemployment": (
        [r"\bunemployed\b", r"\bout of work\b", r"\bjobless\b"],
        [],
        False,
    ),
    "high material wealth": (
        [r"\bbillionaire\b", r"\bmillionaire\b", r"\bnet worth\b",
         r"\b(?:one of the )?(?:richest|wealthiest)\b", r"\bhis fortune\b", r"\bher fortune\b"],
        [],
        False,
    ),
    "poverty": (
        [r"\bin poverty\b", r"\bimpoverished\b", r"\bdestitute\b",
         r"\bpoor family\b", r"\bdeclared bankrupt", r"\bfiled for bankruptcy\b"],
        [],
        False,
    ),
    "homelessness": (
        [r"\bhomeless\b", r"\bevicted\b", r"\bno fixed abode\b"],
        [],
        True,
    ),
    "prolonged hospital isolation": (
        [r"\bsanatorium\b", r"\basylum\b", r"\bpsychiatric (?:hospital|clinic|institution)\b",
         r"\bimprisoned\b", r"\bincarcerated\b", r"\bserved .{0,20}\bin prison\b",
         r"\bsentenced to .{0,30}\bprison\b"],
        [],
        True,
    ),
}


# A keyword hit is worthless unless the sentence is about the subject. The
# first pass matched Springsteen's grandfather emigrating, an incarcerated
# stranger in a Depp lawsuit, and Kennedy's anti-poverty policy. These gates
# were added after auditing that pass and BEFORE any scoring run; they change
# only which sentences count as evidence, never any house mapping.
THIRD_PARTY = re.compile(
    r"\b(?:grandfather|grandmother|grandparents?|great-grand|ancestors?|"
    r"parents|father|mother|brothers?|sisters?|uncles?|aunts?|"
    r"cousins?|nephews?|nieces?|in-law|widow|stepfather|stepmother)",
    re.I,
)

# Sentences that are about a work of art, a policy or someone else's story.
NOT_ABOUT_SUBJECT = re.compile(
    r"\b(?:portray|plays|played the role|character|film in which|novel|"
    r"screenplay|lyrics|song about|documentary|biopic|programme|program|"
    r"policy|policies|legislation|campaign|act of congress|plagiari|"
    r"equivalent to about|inflation-adjusted)",
    re.I,
)


_PRONOUNS = {"He", "She", "His", "Her", "They", "By", "In", "After",
             "During", "When", "On", "At", "Following", "Despite", "Although",
             "The", "A", "An", "As", "From", "For", "With", "While", "Both"}


def _about_subject(sentence: str, surname: str) -> bool:
    if NOT_ABOUT_SUBJECT.search(sentence):
        return False
    if THIRD_PARTY.search(sentence):
        return False
    # "Freud's mother ... his third wife" is about the father, not the subject.
    if re.search(rf"{re.escape(surname)}(?:'s|s')", sentence):
        return False
    # A different person named earlier in the sentence usually owns the verb.
    other = re.match(r"^([A-Z][a-z]+(?:ano|ini|ova|sky|berg|stein)?)\b", sentence)
    if other and other.group(1) != surname and other.group(1) not in _PRONOUNS:
        if not re.search(rf"{re.escape(surname)}", sentence):
            return False
    if re.search(rf"\b{re.escape(surname)}\b", sentence):
        return True
    # A leading pronoun in running biography prose refers to the subject.
    return bool(re.match(r"^(?:He|She|His|Her|By \d{4}, he|By \d{4}, she)\b", sentence))


def first_match(sents: list[str], patterns: list[str], surname: str) -> str | None:
    for s in sents:
        if not _about_subject(s, surname):
            continue
        for p in patterns:
            if re.search(p, s, re.I):
                return " ".join(s.split())[:400]
    return None


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    out = {}
    tally = {"strict": {"yes": 0, "no": 0, "unknown": 0},
             "documented_absence": {"yes": 0, "no": 0, "unknown": 0}}

    for case in corpus.load_corpus():
        cid = case["case_id"]
        text = (BIO_DIR / f"{cid}.txt").read_text(encoding="utf-8")
        sents = sentences(text)
        surname = case["name"].split()[-1]
        row = {}
        for item, (yes_pat, no_pat, silence_no) in RULES.items():
            yq = first_match(sents, yes_pat, surname)
            nq = first_match(sents, no_pat, surname) if no_pat else None
            probe_hits = evidence[cid][item]

            if yq:
                strict = ("yes", yq)
            elif nq:
                strict = ("no", nq)
            else:
                strict = ("unknown", None)

            if strict[0] != "unknown":
                doc = strict
            elif silence_no and not probe_hits:
                doc = ("no", f"[documented absence: no sentence in {len(text)} "
                             f"characters of biography mentions this]")
            else:
                doc = ("unknown", None)

            row[item] = {
                "strict": strict[0],
                "strict_quote": strict[1],
                "documented_absence": doc[0],
                "documented_absence_basis": doc[1],
                "probe_sentences": len(probe_hits),
            }
            tally["strict"][strict[0]] += 1
            tally["documented_absence"][doc[0]] += 1
        out[cid] = row

    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    n = len(out) * len(RULES)
    print(f"{len(out)} cases x {len(RULES)} items = {n} answers")
    for coding, t in tally.items():
        print(
            f"  {coding:20} yes {t['yes']:>4} ({t['yes']/n:.0%})  "
            f"no {t['no']:>4} ({t['no']/n:.0%})  "
            f"unknown {t['unknown']:>4} ({t['unknown']/n:.0%})"
        )
    unsourced = [
        (c, i) for c, r in out.items() for i, v in r.items()
        if v["strict"] != "unknown" and not v["strict_quote"]
    ]
    print(f"unsourced non-unknown strict answers: {len(unsourced)} (must be 0)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
