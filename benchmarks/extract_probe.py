"""Work item 3: surface candidate evidence sentences for each predisposition.

This does not decide anything. For each case and each kept item it pulls the
sentences from the redacted biography that mention the item's subject matter,
so that a human-readable answer can be recorded with a real quotation attached
rather than from recall. An item with no matching sentence has no evidence and
its answer is `unknown` by default.

The probes are keyword lists for the *subject matter* of each item. They are
not part of the mapping and carry no house information; changing a probe can
only change which sentences are surfaced for reading, never which house an
item tests.

    python benchmarks/extract_probe.py            # write the evidence bundle
    python benchmarks/extract_probe.py CASE_ID    # print one case for reading
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.harness import corpus  # noqa: E402

BIO_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "biographies"
MAPPING = pathlib.Path(__file__).resolve().parent / "fixtures" / "predisposition_mapping.json"
OUT = pathlib.Path(__file__).resolve().parent / "fixtures" / "predisposition_evidence.json"

PROBES = {
    "many marriages": [
        r"\bmarried\b", r"\bmarriage\b", r"\bwife\b", r"\bhusband\b",
        r"\bdivorce", r"\bremarri", r"\bannul",
    ],
    "childlessness or a late child": [
        r"\bchildless\b", r"\bno children\b", r"\bchildren\b", r"\bhad a (?:son|daughter)\b",
        r"\binfertil", r"\bmiscarri",
    ],
    "adopted children": [r"\badopt"],
    "separation from a child": [
        r"\bcustody\b", r"\bestranged\b", r"\bseparated from (?:his|her|their) (?:son|daughter|child)",
        r"\bfoster\b", r"\borphan",
    ],
    "death of a child": [
        r"\b(?:son|daughter|child)[^.]{0,80}\bdied\b",
        r"\bdeath of (?:his|her|their) (?:son|daughter|child)",
        r"\bstillborn\b", r"\bmiscarriage\b",
    ],
    "emigration": [
        r"\bemigrat", r"\bimmigrat", r"\bmoved to\b", r"\bsettled in\b",
        r"\bdefect(?:ed|ion)\b", r"\bexile\b", r"\bfled\b", r"\bnaturalis|naturaliz",
    ],
    "success in science": [
        r"\bscien(?:ce|tist|tific)\b", r"\bresearch\b", r"\bphysic(?:s|ist)\b",
        r"\bmathemat", r"\bpatent\b", r"\bengineer",
    ],
    "success in religious work": [
        r"\breligio", r"\bchurch\b", r"\bclergy\b", r"\bpreach", r"\bminister of\b",
        r"\bmissionar", r"\bpastor\b", r"\bordain",
    ],
    "unemployment": [
        r"\bunemploy", r"\bout of work\b", r"\bjobless\b", r"\bfired\b", r"\bdismissed\b",
        r"\bsacked\b", r"\bredundan",
    ],
    "high material wealth": [
        r"\bmillionaire\b", r"\bbillionaire\b", r"\bfortune\b", r"\bnet worth\b",
        r"\bwealth", r"\brichest\b", r"\bmillion\b",
    ],
    "poverty": [
        r"\bpoverty\b", r"\bpoor\b", r"\bdestitute\b", r"\bbankrupt", r"\bimpoverish",
        r"\bbreadline\b", r"\bwelfare\b",
    ],
    "homelessness": [
        r"\bhomeless\b", r"\bevict", r"\bslept in\b", r"\bno fixed abode\b",
        r"\bforeclos",
    ],
    "prolonged hospital isolation": [
        r"\bhospitali[sz]", r"\bsanatorium\b", r"\basylum\b", r"\bconvalesc",
        r"\bin hospital for\b", r"\bimprison", r"\bincarcerat", r"\bjail\b", r"\bprison\b",
    ],
}

SENT = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT.split(text) if s.strip()]


def evidence_for(text: str, patterns: list[str], limit: int = 6) -> list[str]:
    hits: list[str] = []
    for sent in sentences(text):
        if any(re.search(p, sent, re.I) for p in patterns):
            clean = " ".join(sent.split())
            if len(clean) <= 400 and clean not in hits:
                hits.append(clean)
            if len(hits) >= limit:
                break
    return hits


def main() -> None:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    items = [k["item"] for k in mapping["kept"]]
    assert set(items) <= set(PROBES), set(items) - set(PROBES)

    bundle = {}
    for case in corpus.load_corpus():
        text = (BIO_DIR / f"{case['case_id']}.txt").read_text(encoding="utf-8")
        bundle[case["case_id"]] = {
            item: evidence_for(text, PROBES[item]) for item in items
        }

    if len(sys.argv) > 1:
        cid = sys.argv[1]
        print(json.dumps(bundle[cid], indent=2)[:20000])
        return

    OUT.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    total = sum(len(v) for c in bundle.values() for v in c.values())
    with_ev = sum(1 for c in bundle.values() for v in c.values() if v)
    print(f"{len(bundle)} cases x {len(items)} items")
    print(f"{with_ev} case-item pairs have at least one candidate sentence")
    print(f"{len(bundle) * len(items) - with_ev} have none and default to 'unknown'")
    print(f"{total} candidate sentences total")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
