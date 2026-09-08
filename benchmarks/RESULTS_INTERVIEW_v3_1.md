# Interview v3.1: structured stage 1, two-portrait confirmation, every tier gated

**Gates in priority order — G1 PASS, G6 PASS, G7 PASS, G3 PASS, G2 FAIL,
G5 FAIL, G4 PASS.**

The four highest-priority gates all pass, including both gates introduced by
this spec. The two failures are the two lowest-ranked ones.

Two headline movements against v3:

> **The adjacent-sign answerer's Tier-1 wrong-window rate fell from 5.24% to
> 1.34%**, which is what failed G1 in v3. Making stage 1 two independent axes
> means reaching a neighbouring sign takes two errors instead of one.
>
> **Sign recovery after stage 1 rose from 75.6% to 92.7%** for the perfect
> answerer — clearing G5's 90% bar for the first time.

**The v3.1 retune was not spent**, for a reason given below: no parameter in
its scope can move either failing gate.

---

## Gate results (41 cases × 20 runs × 7 models)

| Answerer | T1 | T2 | T3 | T4 | **G1** T1 wrong window | **G7** T2 wrong window | **G6** T3 wrong sign | sign recovery | conflict | questions |
|---|---|---|---|---|---|---|---|---|---|---|
| perfect | 82.9% | 12.2% | 0.0% | 4.9% | **0.00%** | **0.00%** | **0.00%** | 92.7% | 0.0% | 10 |
| iid-noisy | 12.6% | 24.1% | 22.9% | 40.4% | **2.80%** | **2.56%** | **1.10%** | 59.0% | 20.4% | 10 |
| adjacent-sign | 1.3% | 4.5% | 0.0% | 94.2% | **1.34%** | **4.51%** | **0.00%** | 0.0% | 38.3% | 9 |
| random | 0.1% | 4.5% | 24.4% | 71.0% | **0.12%** | **4.39%** | *21.59%* | 13.1% | 35.2% | 10 |
| dont-know-heavy | 2.4% | 38.8% | 16.0% | 42.8% | **0.00%** | **0.00%** | **0.00%** | 51.2% | 0.2% | 10 |
| *correlated-noisy* | *22.8%* | *13.3%* | *27.2%* | *36.7%* | *5.12%* | *1.71%* | *0.98%* | *59.9%* | *17.4%* | *10* |
| *impostor* | *90.2%* | *7.3%* | *0.0%* | *2.4%* | *90.24%* | *7.32%* | *0.00%* | *0.0%* | *0.0%* | *10* |

| Rank | Gate | Required | Worst measured | Verdict |
|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | 2.80% (iid-noisy) | **PASS** |
| 2 | G6 Tier-3 wrong sign | ≤5% per model | 1.10% (iid-noisy) | **PASS** |
| 3 | G7 Tier-2 wrong window | ≤5% per model | 4.51% (adjacent-sign) | **PASS** |
| 4 | G3 refusal | random Tier 3/4 ≥95% | 95.37% | **PASS** |
| 5 | G2 usefulness | perfect Tier 1 ≥90% | 82.93% | **FAIL** |
| 6 | G5 sign recovery | perfect ≥90%, iid ≥60% | 92.68% / **59.02%** | **FAIL** |
| 7 | G4 cost | perfect median ≤10 | 10 | **PASS** |

---

## v2 → v3 → v3.1

| | v2 | v3 | **v3.1** |
|---|---|---|---|
| stage 1 | one 12-way sign choice | greedy ≤4-tag trait splits | **element, then modality** |
| iid-noisy G1 | 0.37% | 3.17% | **2.80%** |
| adjacent-sign G1 | 0.00% | 5.24% | **1.34%** |
| correlated-noisy G1 | 1.59% | 5.73% | **5.12%** |
| sign recovery, perfect | — (direct choice) | 75.6% | **92.7%** |
| sign recovery, iid-noisy | — | 65.5% | **59.0%** |
| perfect Tier 1 | 82.9% | 78.0% | **82.9%** |
| questions | 8 | 9 | **10** |
| Tier 3 measured? | no | no | **yes (G6)** |
| Tier 2 measured? | no | no | **yes (G7)** |

v3.1 recovers most of what v3 lost on safety without giving back the
user-experience gain: questions are still capped at four options and still
carry no time spans. It costs one more question than v3 and two more than v2,
which the raised G4 bound was designed to buy.

**The structural claim held.** Adjacent signs differ in *both* element and
modality — asserted directly by `test_adjacent_signs_differ_on_both_axes` —
so an adjacent-sign answerer must err on two independent axes to land on the
neighbour. It now refuses in 94.2% of runs and reaches Tier 1 in 1.3%.

---

## The two new gates found real things

**G6 — Tier 3 delivers a rising sign, and v1–v3 never checked it.** Under the
new rule a sign is only delivered when a portrait has been confirmed, nothing
conflicts, and one sign genuinely holds the mass; otherwise the answer is
Tier 4. Every gated model is at or below 1.10%.

**But look at the random row: 21.59%.** The spec excludes `random` from G6 and
reports it, and the reported number is the most important caveat in this
document. Random answering reaches Tier 3 in 24.4% of runs, and **88.5% of
those delivered signs are wrong**. G3 counts Tier 3 as an acceptable landing
place for a random answerer — but Tier 3 is a *delivered answer*, not a
refusal. A person who answers noise still walks away with a rising sign, and
it is the wrong one nearly nine times in ten.

That is exactly the class of failure rule 2 of this spec was written to
surface, and it surfaces it. The gate as specified does not catch it because
random is excluded by name. **If the product delivers Tier 3 to people whose
answers do not cohere, G3's definition needs revisiting — Tier 4 and Tier 3
are not interchangeable.**

**G7 — Tier 2 windows.** All gated models ≤4.51%. The adjacent-sign answerer
is the worst at 4.51%, inside the bar but the closest to it: when it does get
a shortlist, that shortlist is sometimes a sign away.

---

## Why the retune was not spent

The v3.1 parameters are `tier3_sign_mass`, `portrait_sign_threshold`,
`repeat_pairs`, and the leftovers `max_trait_questions` / `sign_mass_stop`.

**None of them can move either failing gate.**

- **G5 measures the posterior after stage 1 alone.** Stage 1 is now two fixed
  questions whose likelihoods come from the frozen vocabulary. No parameter in
  scope is consulted before the second structural answer is applied, so no
  setting of them changes sign recovery by a single run. The lever would be
  the element/modality likelihoods, and those are frozen before measurement by
  the spec's own rule.
- **G2 has failed at 78–83% in every version measured**, for a reason that is
  not a trust or threshold problem: in roughly one run in six the region the
  answers genuinely agree on is wider than the 30-minute Tier 1 cap, and a
  Tier 2 shortlist is the correct answer. Reaching 90% means widening that
  cap — buying the lowest-ranked-but-one gate with the promise Tier 1 makes,
  in direct violation of the ranking that puts G1 first.

Spending a retune that cannot change the outcome would only make the log look
busier. It is recorded as **unspent, with one retune remaining** for a future
spec that introduces parameters capable of moving these numbers.

### A knife-edge to be honest about

G5's iid-noisy leg is **59.02%** against a 60% bar. An earlier run of the same
configuration, differing only in the random seeds used for the answerer
models, measured **61.95%** — i.e. a pass. The gate outcome for that leg sits
inside seed noise at n=820 runs, and it should not be read as a stable
finding either way. The perfect leg (92.68%) is not marginal and passes
clearly.

---

## Bits per question, by stage

| Stage | mean bits (perfect answerer) | v3 comparison |
|---|---|---|
| element | 0.036 | — |
| modality | 0.034 | — |
| trait (v3's stage 1) | — | 0.02 |
| sign_portrait | 0.206 | — |
| decan | 2.649 | 4.95 |
| mover_house | 0.961 | 1.55 |

The structural questions carry slightly more expected information than v3's
trait splits (0.036 and 0.034 against 0.02), but the honest reading is that
all three numbers are small for the same reason: the update is positive-only,
so the branch where the person picks nothing contributes zero and drags the
expectation down. What matters is the realised effect, and there the change is
large — sign recovery went from 75.6% to 92.7%.

**The decan figure fell from 4.95 to 2.65 bits, and that is the improvement,
not a regression.** A high number there meant many sign-decan classes were
still live when the decan question was asked — i.e. stage 1 had not narrowed
the sign. Halving it means stage 1 is now doing its job.

Question-count distribution for the perfect answerer: 8 questions in 7% of
runs, 9 in 19%, 10 in 74%. Median 10, at the G4 bound.

---

## The honest floors, unchanged in character

**Impostor: 90.24%.** Someone answering consistently for a different birth
time is still handed a confident wrong window nine times in ten, with a median
error of about six hours. They confirm the portrait for the sign they are
answering *as*, so nothing conflicts and no pair breaks. Their Tier-3 wrong-sign
rate is 0.00% only because they never land in Tier 3 — they go straight to a
confidently wrong Tier 1.

**Correlated-noisy: 5.12%**, marginally over the 5% line it is not held to.
This is the model closest to a real client — someone who holds a partially
wrong belief about themselves and repeats it consistently. It is better than
v3's 5.73% but the mechanism is untouched: paraphrase cannot catch a belief a
person actually holds, and the two-portrait step cannot either when the wrong
belief is what they confirm.

---

## Copy scaffolding — the blocking owner action

The web client auto-skips any question whose keys have no authored copy, so a
live interview ends at the sign: the decan and mover-house channels have no
text at all. The engine cannot fix this, but it is the only thing that knows
the complete key list and what each key must *distinguish*.

- `astro_engine/data/copy_manifest.json` — **353 keys**: element 8, modality 6,
  sign_portrait 24, decan 72, mover_house 240, portrait 3. Each carries the
  distinction it draws (for example, `planet.mars.house.7.life_area` →
  "mars (drive, anger and effort) in house 7 — one-to-one: partnership,
  marriage, open opponents — from the same planet in the neighbouring houses").
- `docs/copy_drafts.md` — one table to read and correct. **38 rows drafted in
  all four locales** (en, ru, uk, de) covering element, modality and the twelve
  sign portraits; **315 rows drafted in English only** for decan and
  mover-house.

The English-only limitation is deliberate and stated in the file rather than
left as empty cells: those 315 rows are template-generated, and a translator
should work from corrected English rather than from four machine drafts. The
web imports only rows marked `approved`.

`test_copy_manifest_covers_every_channel_the_engine_asks` walks a whole
interview and fails if the engine can ask a channel the manifest does not
cover — so this file cannot silently fall behind the engine.

---

## Constraints held

- `git diff main -- astro_engine/rectification.py core.py charts.py` is
  **empty**. Scoring untouched.
- ≤4 options and no clock time in any question — the v3 tests still run and
  still pass, now over the v3.1 question set.
- Reweight, never zero; `cannot_choose` multiplies nothing.
- Vocabulary restructured and frozen before measurement.
- No LLM in the path; deterministic and seeded.
- **Step latency 0.196 s** at the 1-minute grid, against a 1-second budget.
