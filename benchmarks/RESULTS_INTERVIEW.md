# Coherence-tiered interview core: gate results

**G1 (safety) FAIL. G2 (usefulness) FAIL on the 41-case corpus, PASS on the
post-retune holdout. G3 (refusal) PASS.**

The one permitted retune has been used and is logged below. It did not rescue
G1, and the threshold is not renegotiable, so G1 stands as a failure.

The headline number: **an answerer who is wrong 20% of the time is issued a
Tier 1 answer with the true time outside the stated window in 6.2% of runs,
against a 5% bar.** The interview correctly refuses random answers (98.4%) and
correctly degrades a wrong rising sign to Tier 3 (100%), but it cannot yet
detect the specific failure that matters: **several answers wrong in a
mutually consistent way.**

---

## What was built

A stateless interview core at `astro_engine/interview.py`, plus two endpoints.
`POST /v1/interview/step` takes the birth date, place and every answer so far,
and returns the posterior, the next question, the tier and the stated window.
Same input, same output; no randomness and no model anywhere in the path.

| Constraint | How it is enforced |
|---|---|
| One-minute grid | 1440 candidates. The 4-minute grid cost a corpus case outright (`jobs_steve`, true time off-grid). |
| Reweight, never filter | Every answer multiplies weights by a strictly positive factor; `cannot_choose` multiplies nothing. Asserted by `test_reweighting_never_reaches_zero` and `test_many_wrong_answers_still_leave_the_truth_positive`. |
| Every numeric decision in the engine | Answers are enum ids matching `^[a-z0-9_]{1,32}$`; the request model is `extra: forbid`. A caller cannot send a time, a number or a window. Asserted by `test_answer_ids_must_be_enum_tokens` and `test_unknown_fields_are_rejected`. |
| Windows, never bare times | Every Tier 1/2 window carries `start`, `end`, `midpoint`, `width_minutes`, `mass`. |
| Scoring untouched | `git diff main -- astro_engine/rectification.py astro_engine/core.py astro_engine/charts.py` is **empty**. The only engine changes are additive: new models in `schemas.py`, new endpoints in `main.py`. |

Questions come from geometry, not a fixed questionnaire: stage 1 the rising
sign with its exact spans, stage 2 the decan, stage 3 mover-house questions
chosen by greedy expected information gain over the current posterior, stage 4
a portrait choice between surviving windows. Descriptions are returned as
structured keys (`sign.leo.appearance`), never prose.

**Performance: 0.13 s for a cold step and 0.07 s warm, against a 1-second
budget.** The harness runs 4,920 full interviews in 142 s.

---

## The frozen thresholds, and the retune log

| Parameter | Proposed | Final | Changed by |
|---|---|---|---|
| `tier1_mass` (T1) | 0.60 | **0.60** | - |
| `tier2_mass` (T2) | 0.60 | **0.60** | - |
| `tier1_chance_p` (P1) | 0.05 | **0.002** | the one retune |
| `tier2_chance_p` | 0.20 | 0.20 | - |
| `tier1_window_minutes` | 30 | 30 | - |
| `min_information_bits` | 0.15 | 0.15 | - |
| `channel_reliability` (r) | 0.75 | 0.75 | never tuned, by instruction |

**Retune log - one entry, none remaining.**

- *Trigger*: frozen defaults failed G1 (iid-noisy Tier-1 wrong-window 7.8% >
  5%) and G2 (perfect Tier-1 rate 87.8% < 90%).
- *Search*: 9 candidates, `tier1_chance_p` in {0.05, 0.01, 0.002} crossed with
  `tier1_mass` in {0.60, 0.50, 0.40}, **on the 29-case train split only**.
- *Reasoning before running it*: G1 wants Tier 1 harder to reach and G2 wants
  it easier, so the lever had to be cross-channel agreement rather than width
  or mass - a good answerer's channels genuinely agree, a noisy one's agree by
  accident.
- *Result*: **the reasoning was wrong.** Across the whole search space the
  worst-model wrong-window rate moved only between 0.079 and 0.088, and no
  candidate passed more than one gate on train. Tightening agreement by a
  factor of 25 barely touched the number it was aimed at.
- *Chosen*: `tier1_chance_p = 0.002`, `tier1_mass = 0.60` - the best G1 margin
  available.
- *Holdout re-evaluation (12 cases)*: G1 FAIL, G2 PASS, G3 PASS.

The retune is spent. Everything below is measured at the final configuration.

---

## Gate results

41 cases, 20 seeded runs per answerer per case, 820 runs per answerer.

| Answerer | Tier 1 | Tier 2 | Tier 3 | Tier 4 | **Tier-1 wrong-window** | Tier-1 median &#124;err&#124; | Tier-1 median window | median questions |
|---|---|---|---|---|---|---|---|---|
| perfect | 82.9% | 17.1% | 0.0% | 0.0% | **0.00%** | 3 min | 13.5 min | 4 |
| iid-noisy (p=0.2) | 37.0% | 9.6% | 53.4% | 0.0% | **6.22%** | 5 min | 15 min | 5 |
| adjacent-sign | 0.0% | 0.0% | 100.0% | 0.0% | **0.00%** | - | - | 5 |
| random | 1.1% | 0.5% | 98.4% | 0.0% | **1.10%** | - | 14 min | 5 |
| dont-know-heavy | 14.5% | 65.3% | 0.0% | 20.2% | **0.00%** | 7 min | 32 min | 5 |
| *impostor (not gated)* | *75.6%* | *0.0%* | *0.0%* | *0.0%* | *75.61%* | *358 min* | *14 min* | *4* |

### G1 - safety: **FAIL**

Required: Tier 1 issued with the true time outside the stated window in <= 5%
of runs, **per model and pooled**.

| Model | wrong-window rate |
|---|---|
| perfect | 0.00% |
| iid-noisy | **6.22%** |
| adjacent-sign | 0.00% |
| random | 1.10% |
| dont-know-heavy | 0.00% |
| **pooled** | 1.46% |

Pooled would have passed at 1.46%. The spec requires per-model as well, and
iid-noisy fails at 6.22%. Reporting the pooled figure alone would have hidden
exactly the case the gate exists to catch.

### G2 - usefulness: **FAIL on 41 cases, PASS on holdout**

| Condition | Required | All 41 | Holdout (post-retune) |
|---|---|---|---|
| perfect reaches Tier 1 | >= 90% | **82.9% FAIL** | PASS |
| stated window | <= 30 min | 30 min max PASS | PASS |
| window contains truth | >= 95% | **100% PASS** | PASS |
| midpoint median &#124;err&#124; | <= 8 min | **3 min PASS** | PASS |

Three of four conditions pass comfortably on the full corpus. The failure is
entirely the Tier 1 rate: 17.1% of perfect-answerer runs land in Tier 2
instead, because the agreed region is wider than 30 minutes and honestly
should be reported as a shortlist. **When it does issue Tier 1 it is never
wrong** - 100% window containment, median error 3 minutes.

The holdout pass is reported because the retune rule requires it, but it rests
on 12 cases and the all-41 figure is the one to believe.

### G3 - refusal: **PASS**

Random answering lands in Tier 3 or 4 in **98.4%** of runs, against a 95% bar.
The adjacent-sign answerer - a single plausible mistake at stage 1 - lands in
Tier 3 in **100%** of runs and never issues a time. That is the design working:
a wrong rising sign degrades to "here is your rising sign", not to a confident
wrong minute.

---

## The impostor floor, stated plainly

**75.6%.** An answerer who answers perfectly but for a different birth time is
issued a Tier 1 answer, with a median error of 358 minutes, in three quarters
of runs.

This is not a defect to be fixed. It is the irreducible limit of the method:
an interview has no channel that can distinguish a person answering
consistently about themselves from one answering consistently about someone
else. Any product built on this must treat "the person's answers describe the
person" as an assumption it cannot verify, and must not present Tier 1 as a
guarantee of correctness. It is excluded from G1 by the spec, and it is the
honest ceiling on what confidence any tier can carry.

The G1 failure is the same phenomenon in partial form. An answerer wrong 20%
of the time occasionally produces several answers that are wrong *together* in
a way that agrees on some wrong region. Cross-channel agreement cannot tell
that apart from several answers right together, because the two look
identical: channels concentrating on one region. This is the design limit the
gate found, and no threshold on agreement fixes it - which is what the retune
demonstrated.

---

## Sensitivity over channel reliability r

`r` was **not tuned**, per the hard constraint. This row is reported only.

| r | G1 worst-model | G1 | G2 Tier-1 rate | G2 | G3 | impostor floor |
|---|---|---|---|---|---|---|
| 0.60 | **2.2%** | **PASS** | 82.9% | FAIL | 99.5% PASS | 88% |
| **0.75 (shipped)** | 6.2% | FAIL | 82.9% | FAIL | 98.4% PASS | 76% |
| 0.90 | 14.9% | FAIL | 78.0% | FAIL | 94.6% FAIL | 71% |

This is the most useful row in the report. **`r` - not any tier threshold - is
the parameter that controls G1.** At r = 0.60 the safety gate passes; at 0.90
it fails badly and even the refusal gate collapses. The mechanism is direct: a
lower assumed reliability downweights non-matching candidates less, the
posterior stays broader, and fewer confident-but-wrong Tier 1s are issued.

Two things follow. First, the retune was aimed at the wrong parameter, and the
sensitivity row says so plainly. Second, **r is an empirical quantity about
real people, not a knob**: the honest way to set it is to measure how often
live answerers are actually right, which is exactly what the calibration
endpoint below exists to collect. Setting r = 0.60 now to make G1 pass would be
choosing a number to pass a gate rather than because it is true.

---

## How many questions a perfect answerer needs

| Questions | Runs | Share |
|---|---|---|
| 3 | 100 | 12.2% |
| 4 | 340 | 41.5% |
| 5 | 380 | 46.3% |

**Median 4, mean 4.34.** Consistent with the earlier geometry result that two
mover questions saturate: one rising sign, one decan, two movers, occasionally
a portrait choice.

---

## Telemetry and the calibration contract

Every step returns a PII-free telemetry block: tier, concentration,
chance-agreement probability, channel overlap, answer and `cannot_choose`
counts, window widths, grid size, selection mode and compute time. **It never
contains an answer, a candidate time or a birth time.**

`POST /v1/interview/compare` closes the calibration loop. The contract is
structural rather than procedural: `InterviewRequest` has no field for a
documented birth time and rejects unknown fields, so a blind session *cannot*
leak the answer into the interview even by mistake. The documented time is
submitted once, afterwards, to the compare endpoint, which returns the error
in minutes, whether the window contained it, the tier and the coherence
numbers - and captures only the telemetry.

`test_compare_endpoint_returns_error_and_captures_no_pii` asserts the response
contains neither the documented time nor any answer;
`test_interview_step_has_no_field_for_a_documented_time` asserts the
structural half.

This is how the study that could not be run on celebrities gets run: on live
answerers with documented times, continuously, and it is also the only honest
way to set `r`.

---

## On simulated answerers

The prohibition on validating against self-generated data stands and is not
violated here. Astrological accuracy is not what this harness measures - that
inherits from the ceiling measurements made against 41 known birth times in
`RESULTS_SUBSIGN.md`, which found a median of about 6 minutes and roughly half
of cases inside +/-5 under perfect oracles.

What this harness measures is **detection logic**: whether the tiers respond
correctly to answer quality. Answer quality is precisely the variable being
simulated, so simulating it is the only way to measure the thing. A synthetic
answerer cannot tell you whether astrology works; it can tell you whether the
system notices when its inputs are bad. On that question the answer is: it
notices random noise (G3 passes at 98.4%), it notices a wrong rising sign
(100% Tier 3), and it does not reliably notice consistent partial error (G1
fails at 6.2%).

---

## Where this leaves the product

- **Do not ship Tier 1 as a guarantee.** Its wrong-window rate under a
  realistically noisy answerer is 6.2%, and under an impostor 75.6%.
- **Tier 2 is doing more work than expected and doing it well.** 17.1% of
  perfect runs and 65.3% of don't-know-heavy runs land there, correctly, with
  the truth inside the shortlist.
- **The refusal path works.** Random input refuses 98.4% of the time and a
  single wrong sign never produces a time.
- **The next measurement is `r`, from live calibration sessions**, not another
  threshold search. The sensitivity row shows `r` is the lever; the retune
  showed the thresholds are not.
