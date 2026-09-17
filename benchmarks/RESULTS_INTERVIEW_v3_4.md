# Interview v3.4: G7 fixed on holdout, and what fixing it actually cost

**G7 passes on holdout at 40 seeds for the first time — worst model 4.37%
(random), down from 6.04% (sun-attributor) — and it cost the perfect answerer
nothing: the median shortlist is 36 minutes before and after.**

**G1 still fails on holdout at 5.42%,** unchanged by this work and unchanged
at 40 seeds from the 26-run figure that prompted the re-measurement.

Ranked verdicts **on holdout at 40 seeds**, which is the v3.4 change:

| Rank | Gate | Required | Baseline | **Chosen** |
|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | 5.42% **FAIL** | 5.42% **FAIL** |
| 2 | G7 Tier-2 window | ≤5% per model | 6.04% **FAIL** | **4.37% PASS** |
| 3 | G3 refusal | random T4 ≥90% | 94.8% PASS | 95.6% PASS |
| 4 | G9 shortlist width | perfect median ≤90 min | 36.0 min PASS | 36.0 min PASS |
| 5 | G2 usefulness | perfect T1 ≥90% | 83.3% FAIL | 83.3% FAIL |
| 6 | G5 sign recovery | perfect ≥90%, iid ≥60% | PASS | PASS |
| 7 | G4 cost | perfect median ≤10 | 10 PASS | 10 PASS |

The retune was **spent**, on one parameter: `tier2_window_minutes` 90 → 50.

---

## 1. The finding that matters most: G7 has no accuracy lever

The spec's reasoning was that "the honest direction for a shortlist that
misses is wider windows, not stricter admission". The measurement says there
was nothing to widen. **The shortlists Tier 2 issues already contain the
truth.**

`tier2_contains_truth_rate` for the perfect answerer is **1.0 in every one of
the 18 sweep cells, including the baseline that fails G7.** Not 0.99 —
every shortlist, every cell, including the configuration under which the gate
was failing.

So G7's failures do not come from windows that are slightly too narrow around
a correct centre. They come from answerers whose shortlists are wrong
wholesale, and every cell in the sweep improves G7 by **issuing fewer
shortlists to them**, not by issuing better ones. The two move together
almost exactly:

| | baseline | w50 | w40 | w30 |
|---|---|---|---|---|
| G7 worst (train) | 5.86% | 3.97% | 3.28% | 2.93% |
| dont-know-heavy Tier 2 rate | 35.9% | 32.2% | 22.6% | 14.0% |
| perfect Tier 2 rate | 13.8% | 13.8% | 10.3% | **0.0%** |

**This is abstention, not accuracy, and the report should not dress it up as
anything else.** The gate is satisfied because fewer people are given an
answer, and the people no longer given one are mostly people who would have
been given a correct one.

## 2. Six cells passed G9 vacuously and were disqualified

Every `w30` cell issues the perfect answerer **zero** Tier 2 shortlists. With
G9 written as `(median or 0) <= 90`, an undefined median read as a pass — so
the three narrowest width caps "passed" a shortlist-usefulness gate by never
producing a shortlist.

That is the exact shape of the v3.2 failure, where a wrong-sign gate passed on
an empty set and it took two versions to notice. **G9 now fails when no
shortlist is issued**, the six `w30` cells are disqualified on that basis
rather than on their G7 numbers, and the corrected rule was re-applied to the
stored cells before the choice was made.

## 3. `tier2_max_windows` is inert

`n2` and `n3` produce **byte-identical results in all nine pairs**. Tier 2
never produced three windows in any cell, so the count cap decides nothing.

That is the second parameter in two tasks — after `tier2_chance_p` in v3.3.1 —
that turns out not to be a lever at all. It is kept explicit rather than
deleted, because the code path is real and a different posterior could reach
it, but it should not be offered as a tuning knob again without new evidence
that it moves something.

---

## 4. The sweep (train only, 29 cases × 20 seeds × 6 gated models)

Frozen grid, in the spec's order of preference: width cap {30, 40, 50} ×
count cap {2, 3} × `tier2_mass` {0.60, 0.70, 0.80}. The pre-v3.4
configuration (cap 90, count 3, mass 0.60) is a reference row, not a
candidate — the grid was fixed at 30/40/50.

**Interpretation, accepted by the owner before the run:** `tier2_window_minutes`
is an *admission* limit — the widest single window Tier 2 will accept before
refusing. The windows themselves are built from the posterior at `tier2_mass`,
and raising that mass is what widens them.

| cell | G7 worst | G9 perfect median | perfect T2 | dont-know-heavy T2 | G3 |
|---|---|---|---|---|---|
| *baseline (w90, n3, m0.60)* | *5.86% FAIL* | *35 min* | *13.8%* | *35.9%* | *94.8%* |
| w30 · any n · m0.60 | 2.93% | **none issued** | **0.0%** | 14.0% | 97.4% |
| w30 · any n · m0.70 | 1.90% | **none issued** | **0.0%** | 12.4% | 98.1% |
| w30 · any n · m0.80 | 1.21% | **none issued** | **0.0%** | 10.3% | 98.8% |
| w40 · any n · m0.60 | 3.28% | 32 min | 10.3% | 22.6% | 96.7% |
| w40 · any n · m0.70 | 2.59% | 32 min | 10.3% | 21.9% | 97.4% |
| w40 · any n · m0.80 | 1.90% | 32 min | 10.3% | 19.3% | 98.1% |
| **w50 · n3 · m0.60** | **3.97%** | **35 min** | **13.8%** | **32.2%** | **96.0%** |
| w50 · any n · m0.70 | 3.45% | 35 min | 13.8% | 31.9% | 96.5% |
| w50 · any n · m0.80 | 2.41% | 35 min | 13.8% | 29.0% | 97.6% |

All eighteen cells pass G1, G3 and G7 on train; the six `w30` cells fail the
corrected G9. The twelve survivors tie on the ranking, so the choice fell to
the spec's stated order of preference — width first, then count, then mass.

**Chosen: `tier2_window_minutes = 50`, count and mass unchanged.** It moves
exactly one parameter, the most-preferred one, and of the twelve tied cells it
preserves the most shortlist coverage (dont-know-heavy 32.2% against 19.3% at
w40·m0.80) while leaving the perfect answerer's Tier 2 rate identical to
baseline. Cells with more G7 margin buy it with usefulness the bar does not
require.

### Retune log

| | before | after |
|---|---|---|
| `tier2_window_minutes` | 90 | **50** |
| `tier2_max_windows` | 3 | 3 (inert at every measured value) |
| `tier2_mass` | 0.60 | 0.60 |

Spent, train-only, on a grid frozen before running, re-evaluated on holdout.

---

## 5. Holdout at 40 seeds, before and after (Work item 2)

Per model, the numbers the definition of done asks for:

| Answerer | G7 baseline | **G7 chosen** | Tier 2 rate before → after | median shortlist before → after |
|---|---|---|---|---|
| perfect | 0.00% | **0.00%** | 8.3% → 8.3% | 36 → **36 min** |
| iid-noisy | 2.92% | **2.29%** | 27.7% → 25.0% | 32 → 30 min |
| adjacent-sign | 0.00% | **0.00%** | 0.0% → 0.0% | — |
| random | 5.21% | **4.37%** | 5.2% → 4.4% | 32 → 29 min |
| dont-know-heavy | 0.00% | **0.00%** | 35.8% → 30.6% | 37 → 35 min |
| sign-only | 0.00% | **0.00%** | 0.0% → 0.0% | — |
| **sun-attributor** | **6.04%** | **0.83%** | 8.1% → **2.3%** | 70 → 27 min |
| *correlated-noisy* | *1.87%* | *1.87%* | *10.4% → 9.2%* | *36.5 → 36 min* |
| *impostor* | *25.00%* | *25.00%* | *25.0% → 25.0%* | *34 → 34 min* |

**G7 worst goes 6.04% → 4.37%, inside the bar.** The gate was failing on the
sun-attributor, and the cap fixed it by cutting that model's Tier 2 rate from
8.1% to 2.3% — its median shortlist was 70 minutes, the widest of any model,
and those were the wide wrong shortlists the cap now refuses. Its
contains-truth rate among the shortlists it still gets rose from 0.26 to 0.64.
That is the one place in this task where the change improved the *quality* of
what is issued rather than only the quantity.

**The cost, stated plainly:** the perfect answerer pays nothing (36 minutes
before and after, Tier 2 rate 8.3% unchanged), and the cost lands on
dont-know-heavy, which loses 5.2 points of shortlist coverage (35.8% → 30.6%)
despite a contains-truth rate of **1.0** both before and after. Those are
correct shortlists no longer being offered.

### G1 on holdout: 5.42% holds exactly

| | 40 seeds, baseline | 40 seeds, chosen | full corpus |
|---|---|---|---|
| G1 worst | **5.42%** (adjacent-sign) | **5.42%** (adjacent-sign) | 2.01% (iid-noisy) |

The v3.3.1 figure was not a small-sample artefact: at 40 seeds per model per
case it reproduces to the digit, because Tier 1 is untouched by this change.
G1 fails on holdout and passes on the full corpus, and adjacent-sign is the
driver in both.

**Where the truth sits relative to adjacent-sign's windows.** Its holdout Tier
1 windows contain the truth 0% of the time, and the diagnostic says why: the
median absolute error is **88 minutes** and the *minimum* is also 88 minutes.
There are no near misses. The error is the width of roughly one rising-sign
block — which is exactly the displacement the model is constructed from, not a
resolution failure. Widening a 30-minute Tier 1 window to catch an 88-minute
displacement would mean abandoning Tier 1's promise entirely.

So G1's holdout failure is **not fixable by window geometry**. It is the same
structural ceiling as the impostor: a person who describes themselves
coherently as the wrong sign produces a session indistinguishable from an
honest one, and the engine hands them a confident window about one time in
twenty on these charts.

---

## 6. Copy: zero uncovered keys (Work item 3)

`portrait.window` is now an approved template and the `UNCOVERED` set is
**empty**:

| Channel | keys | with approved Russian |
|---|---|---|
| element | 8 | 8 |
| modality | 6 | 6 |
| sign_portrait | 24 | 24 |
| decan | 72 | 72 |
| mover_house | 240 | 240 |
| **portrait** | **3** | **3** |
| **total** | **353** | **353** |

The stage-4 question distinguishes two surviving windows. Describing them by
rising sign would break the no-sign-names rule, and it does not need to:
windows inside one sign block differ by **house placements**, which compose
from the approved sphere and planet atoms. A test asserts no sign name appears
in the template.

The row arrived mis-encoded, as the v3.3 file did, and was reconstructed. This
time it was **verified against an owner-supplied SHA-256 and matches byte for
byte**; that hash is now pinned in a test, so a later edit to the row has to be
deliberate. The drift reference is `docs/interview_copy_drafts_ru_approved_v3_4.md`
(the v3.3 file plus this one row), and `docs/copy_drafts.md` is byte-identical
to it.

---

## 7. Constraints held

- `git diff main -- astro_engine/rectification.py astro_engine/core.py
  astro_engine/charts.py` is **empty**. Scoring untouched.
- Portrait mass threshold stays at **0.70** — it is a measured safety
  mechanism (v3.3: removing it took adjacent-sign's G1 from 1.04% to 32.50%).
- Grid frozen before measurement; sweep train-only; holdout scored afterwards.
- Reweight, never zero; ≤4 options; no clock time in any question.
- G6, G6-sun and G8 removed from the gate set — they were Tier 3 gates still
  emitting verdicts after Tier 3 was dropped, and G8 was reporting a
  meaningless "FAIL".
- No LLM; deterministic, SHA-256 seeded.
- 100 tests pass.

## 8. For the owner

1. **G7 is fixed on holdout, but understand what bought it.** Abstention. The
   engine now declines to offer some shortlists that would have been correct —
   dont-know-heavy loses 5.2 points of coverage at a contains-truth rate of
   1.0. If that trade is wrong, the lever to reverse it is the same one.
2. **G1's holdout failure is structural and should stop being treated as a
   tuning target.** Adjacent-sign's misses are 88 minutes — a whole sign block,
   with no near misses at all. No window geometry catches that.
3. **Two parameters are now known to be inert** — `tier2_chance_p` and
   `tier2_max_windows`. Three of the Tier 2 knobs have been swept and only one
   moves anything.
4. **The remaining real question is unchanged and needs live data.** Whether a
   person's self-description actually identifies their rising sign is what
   `/v1/interview/compare` exists to measure, and every ceiling in this report
   — impostor 87.8%, adjacent-sign, sun-attribution — is a version of that one
   question.
