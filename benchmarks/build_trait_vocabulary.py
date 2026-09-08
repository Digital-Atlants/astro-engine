"""Generate the frozen trait vocabulary fixture.

A trait tag is not a label for one sign. It is an observable the person can
recognise about themselves, which fits several signs at different strengths.
That is the whole point: a 12-way "which of these is you" question is answered
unreliably, while "do any of these four describe you" is answered well and
carries the same bits across two or three rounds.

Likelihoods are generated from a declarative rule rather than hand-typed per
sign, so the fixture is auditable and reproducible:

    likelihood(tag, sign) = element_profile[element(sign)]
                          * modality_profile[modality(sign)]

clipped into [FLOOR, CEILING]. A purely elemental tag carries a flat modality
profile and vice versa. Nothing here is fitted to the corpus - there is no
corpus in this step - and the fixture is frozen before any measurement.

    python benchmarks/build_trait_vocabulary.py
"""

from __future__ import annotations

import json
import pathlib

OUT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "astro_engine" / "data" / "trait_vocabulary.json"
)
SEP_OUT = (
    pathlib.Path(__file__).resolve().parent
    / "fixtures" / "trait_vocabulary_separation.json"
)

SIGN_ATTRS = {
    "aries": ("fire", "cardinal"),
    "taurus": ("earth", "fixed"),
    "gemini": ("air", "mutable"),
    "cancer": ("water", "cardinal"),
    "leo": ("fire", "fixed"),
    "virgo": ("earth", "mutable"),
    "libra": ("air", "cardinal"),
    "scorpio": ("water", "fixed"),
    "sagittarius": ("fire", "mutable"),
    "capricorn": ("earth", "cardinal"),
    "aquarius": ("air", "fixed"),
    "pisces": ("water", "mutable"),
}
SIGNS = list(SIGN_ATTRS)

FLOOR, CEILING = 0.08, 0.94
FLAT = {"cardinal": 1.0, "fixed": 1.0, "mutable": 1.0}
FLAT_E = {"fire": 1.0, "earth": 1.0, "air": 1.0, "water": 1.0}


def E(fire, earth, air, water):
    return {"fire": fire, "earth": earth, "air": air, "water": water}


def M(cardinal, fixed, mutable):
    return {"cardinal": cardinal, "fixed": fixed, "mutable": mutable}


# (tag_id, channel, element_profile, modality_profile)
TAGS = [
    # ---- temperament -----------------------------------------------------
    ("acts_before_thinking", "temperament", E(.95, .30, .55, .30), M(1.15, .85, 1.0)),
    ("slow_to_start_hard_to_stop", "temperament", E(.25, .95, .35, .60), M(.80, 1.25, .75)),
    ("thinks_out_loud", "temperament", E(.60, .30, .95, .30), M(1.0, .85, 1.20)),
    ("reads_the_room_first", "temperament", E(.25, .55, .45, .95), M(1.0, 1.05, 1.0)),
    ("needs_a_cause_to_push", "temperament", E(.85, .45, .60, .45), M(1.30, .95, .75)),
    ("holds_a_position", "temperament", E(.55, .85, .50, .80), M(.70, 1.35, .60)),
    ("changes_tack_easily", "temperament", E(.65, .45, .80, .55), M(.70, .55, 1.45)),
    ("keeps_feeling_private", "temperament", E(.30, .70, .35, .90), M(.95, 1.20, .85)),
    ("plans_the_long_way_round", "temperament", E(.30, .90, .50, .50), M(1.20, 1.05, .70)),
    ("runs_on_enthusiasm", "temperament", E(.90, .30, .65, .40), M(1.05, .90, 1.10)),
    # ---- social ----------------------------------------------------------
    ("starts_the_conversation", "social", E(.85, .40, .80, .35), M(1.30, .85, .95)),
    ("waits_to_be_approached", "social", E(.30, .80, .40, .85), M(.75, 1.15, 1.0)),
    ("keeps_a_wide_circle", "social", E(.70, .40, .90, .35), M(1.05, .80, 1.25)),
    ("keeps_a_few_close", "social", E(.35, .85, .35, .90), M(.90, 1.25, .85)),
    ("takes_charge_uninvited", "social", E(.90, .55, .55, .35), M(1.35, 1.10, .60)),
    ("smooths_a_disagreement", "social", E(.35, .60, .85, .70), M(1.20, .80, 1.05)),
    ("says_the_unwelcome_thing", "social", E(.80, .60, .60, .55), M(1.05, 1.20, .80)),
    ("prefers_to_work_alone", "social", E(.40, .80, .50, .75), M(.85, 1.20, .90)),
    ("drawn_to_the_unfamiliar", "social", E(.85, .25, .80, .45), M(.90, .65, 1.45)),
    ("keeps_the_routine", "social", E(.25, .95, .35, .55), M(1.0, 1.30, .60)),
    # ---- appearance ------------------------------------------------------
    ("carries_weight_low_and_solid", "appearance", E(.30, .95, .35, .60), M(1.0, 1.20, .80)),
    ("long_limbed_light_framed", "appearance", E(.65, .30, .95, .45), M(.95, .75, 1.30)),
    ("strong_jaw_direct_gaze", "appearance", E(.95, .60, .40, .35), M(1.25, 1.10, .65)),
    ("soft_features_wide_eyes", "appearance", E(.30, .45, .55, .95), M(.95, .90, 1.20)),
    ("upright_carriage_measured_step", "appearance", E(.55, .85, .45, .40), M(1.20, 1.15, .65)),
    ("quick_restless_movement", "appearance", E(.80, .25, .90, .40), M(.90, .60, 1.45)),
    ("heavy_brows_intent_look", "appearance", E(.55, .70, .35, .90), M(.95, 1.30, .70)),
    ("open_expressive_face", "appearance", E(.90, .35, .75, .50), M(1.10, .85, 1.10)),
    ("fine_boned_even_features", "appearance", E(.40, .55, .90, .60), M(1.25, .75, 1.0)),
    ("broad_shouldered_sturdy", "appearance", E(.75, .90, .30, .40), M(1.10, 1.25, .60)),
]


def likelihood(element_profile, modality_profile, sign) -> float:
    el, mod = SIGN_ATTRS[sign]
    return round(
        min(CEILING, max(FLOOR, element_profile[el] * modality_profile[mod])), 4
    )


def build() -> dict:
    tags = []
    for tag_id, channel, ep, mp in TAGS:
        tags.append(
            {
                "tag_id": tag_id,
                "channel": channel,
                "label_key": f"trait.{tag_id}.label",
                "paraphrase_key": f"trait.{tag_id}.paraphrase",
                "likelihood": {s: likelihood(ep, mp, s) for s in SIGNS},
            }
        )
    return {
        "_README": (
            "FROZEN BEFORE MEASUREMENT. Any change to a tag or a likelihood "
            "invalidates every v3 result and requires a rerun from scratch. "
            "Generated by benchmarks/build_trait_vocabulary.py."
        ),
        "frozen_on": "2026-09-08",
        "generation_rule": (
            "likelihood(tag, sign) = element_profile[element(sign)] * "
            "modality_profile[modality(sign)], clipped to "
            f"[{FLOOR}, {CEILING}]. Not fitted to any corpus."
        ),
        "signs": SIGNS,
        "sign_attributes": {s: {"element": e, "modality": m}
                            for s, (e, m) in SIGN_ATTRS.items()},
        "channels": ["temperament", "social", "appearance"],
        "tags": tags,
    }


def separation_report(vocab: dict, threshold: float = 0.20) -> dict:
    """How many tags tell each sign apart from each of its two neighbours.

    A sign with no distinguishing tag against a neighbour cannot be resolved
    from it by this vocabulary at all. That is a finding about the vocabulary,
    reported rather than smoothed over.
    """
    tags = vocab["tags"]
    rows = {}
    for i, sign in enumerate(SIGNS):
        prev_sign = SIGNS[(i - 1) % 12]
        next_sign = SIGNS[(i + 1) % 12]
        row = {}
        for other in (prev_sign, next_sign):
            n = sum(
                1 for t in tags
                if abs(t["likelihood"][sign] - t["likelihood"][other]) >= threshold
            )
            row[other] = n
        # And against every sign, the worst case.
        worst = min(
            (
                sum(1 for t in tags
                    if abs(t["likelihood"][sign] - t["likelihood"][o]) >= threshold)
                for o in SIGNS if o != sign
            )
        )
        row["worst_against_any_sign"] = worst
        rows[sign] = row
    return {
        "threshold": threshold,
        "per_sign": rows,
        "signs_with_no_separating_tag": [
            s for s, r in rows.items() if r["worst_against_any_sign"] == 0
        ],
    }


def main() -> None:
    vocab = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(vocab, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rep = separation_report(vocab)
    SEP_OUT.parent.mkdir(parents=True, exist_ok=True)
    SEP_OUT.write_text(
        json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"tags: {len(vocab['tags'])}")
    for ch in vocab["channels"]:
        print(f"  {ch}: {sum(1 for t in vocab['tags'] if t['channel'] == ch)}")
    print(f"\nseparation at |dL| >= {rep['threshold']}")
    for sign, row in rep["per_sign"].items():
        nb = [k for k in row if k != "worst_against_any_sign"]
        print(f"  {sign:12} vs {nb[0][:4]} {row[nb[0]]:>3}  vs {nb[1][:4]} {row[nb[1]]:>3}"
              f"   worst-vs-any {row['worst_against_any_sign']:>3}")
    print(f"\nsigns with no separating tag against some sign: "
          f"{rep['signs_with_no_separating_tag'] or 'none'}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
