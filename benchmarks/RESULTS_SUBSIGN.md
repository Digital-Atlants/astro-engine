# Sub-sign resolution: the two missing bits were not found

**Gate verdict: FAIL.** On the held-out split of a 41-case Rodden AA corpus, the
median absolute error inside the correct rising-sign block is **23.0 minutes**,
against the pre-registered threshold of **6.0 minutes**. No configuration tried
in this task reached the threshold, and none beat the existing baseline.

Under the pre-registered rule, **variant B is dead**: stop, ship the shortlist
product, rewrite the promise.

Everything below is the evidence. Nothing here was tuned against the number it
is measured by: all parameter choices were made on `train` (29 cases) and the
gate was read once off `holdout` (12 cases).

---

## What was measured, and against what

| | |
|---|---|
| Corpus | 41 Rodden AA cases, `benchmarks/corpus/{train,holdout}/` |
| Split | 29 train / 12 holdout, stratified on night-birth and high-latitude |
| Window | 00:00-23:59, step 4 min, 360 candidates |
| Metric | absolute minutes between the in-block argmax and the known time |
| Gate | holdout in-block median <= 6 min |

The prior measurement on the 12-case corpus (median 12 min in-block) is not
contradicted; it is superseded. Those 12 cases are now distributed across both
splits, and 12 min was a full-corpus figure on a sample a third the size. On a
genuinely held-out sample of 12 the same engine measures **23.0**. That is what
a held-out number is for.

---

## Work item 2 - the within-block variance filter

Each candidate evaluator scored at every candidate time inside the *correct*
rising-sign block, on the 29 training cases. An evaluator that does not move
inside the block cannot reorder candidates inside the block, whatever its
astrological standing.

| Evaluator | median CV | mean distinct-value fraction | cases flat in block | median range | Decision |
|---|---|---|---|---|---|
| eclipse_on_angle | 1.193 | 0.64 | 0/29 | 2.341 | include |
| secondary_progressions | 0.974 | 0.78 | 0/29 | 3.153 | include (already shipped) |
| primary_directions | 0.880 | 0.73 | 0/29 | 2.560 | include |
| solar_arc | 0.649 | 0.88 | 0/29 | 3.580 | include (already shipped) |
| transits_to_angles | 0.618 | 0.96 | 0/29 | 3.546 | include (already shipped) |
| directed_angles | 0.437 | 0.99 | 0/29 | 6.515 | include |
| quadrant_cusps | 0.299 | 1.00 | 0/29 | 18.463 | include, **Placidus only** |
| **profections** | **0.000** | 0.03 | **29/29** | 0.000 | **exclude** |
| **sect** | **0.000** | 0.03 | **29/29** | 0.000 | **exclude** |
| **saros_family** | **0.000** | 0.03 | **29/29** | 0.000 | **exclude** |

Threshold for inclusion: median CV >= 0.05 and not flat in every case.

### The three exclusions, confirmed not assumed

**Sect is constant inside the block, in 29 of 29 cases.** Under whole-sign
houses the Sun's house follows the Ascendant sign, and the sign is by
definition fixed inside a block. Sect is a stage-1 block-level prior and
nothing else. The five-cell multiplier scheme was **not implemented**, because
the variance table did not justify it.

**Saros family is constant by construction.** It is a property of the birth
date. It cannot reorder candidates on its own and was given lowest priority;
since the eclipse evaluator itself failed its ablation (below), it was never
implemented at all.

**Profections is constant inside the block, in 29 of 29 cases.** This one was
not pre-registered and is the more useful finding, because profections is a
*currently shipped* technique. The profected house is a function of the
Ascendant sign, so profections contributes exactly zero to sub-sign
resolution. It is kept in the engine because it helps rank blocks, and its
role is now documented in the module docstring as a block-level prior rather
than a discriminator.

---

## Work item 3 - the ablation

In-block median absolute error. Decisions read off train; the gate off holdout.

### Individual: baseline plus one addition

| Configuration | train median | **holdout median** | holdout mean | holdout <=5 | holdout <=15 | holdout <=30 | holdout non-round median |
|---|---|---|---|---|---|---|---|
| baseline (four shipped techniques) | 29.0 | **23.0** | 38.8 | 0% | 33% | 58% | 31.0 |
| + 3.1 quadrant_cusps (whole_sign) | 29.0 | **23.0** | 38.8 | 0% | 33% | 58% | 31.0 |
| + 3.1 quadrant_cusps (placidus) | 28.0 | **46.5** | 61.5 | 8% | 8% | 17% | 52.0 |
| + 3.2 directed_angles | 32.0 | **36.0** | 49.5 | 0% | 25% | 50% | 36.0 |
| + 3.3 primary_directions | 29.0 | **23.0** | 39.5 | 0% | 25% | 67% | 26.0 |
| + 3.4 eclipse_on_angle | 29.0 | **31.0** | 41.8 | 0% | 25% | 50% | 45.0 |
| + 3.5 event_technique_matching | 37.0 | **36.5** | 49.5 | 8% | 25% | 42% | 48.5 |

### Cumulative

| Configuration | train median | **holdout median** | holdout mean | holdout <=15 |
|---|---|---|---|---|
| baseline | 29.0 | **23.0** | 38.8 | 33% |
| + 3.1 | 29.0 | **23.0** | 38.8 | 33% |
| + 3.1 + 3.2 | 32.0 | **36.0** | 49.5 | 25% |
| + 3.1 + 3.2 + 3.3 | 37.0 | **45.0** | 53.8 | 17% |
| + 3.1 ... 3.4 | 32.0 | **43.5** | 51.2 | 17% |
| + 3.1 ... 3.5 | 40.0 | **30.5** | 34.8 | 33% |

**The best number anywhere in this table is the baseline's 23.0.** Every
addition is neutral or harmful on holdout, and the cumulative stack is worse
than the baseline at every step.

### Each addition was given its best shot before being reverted

An addition can fail because its weight is wrong rather than because the idea
is wrong. Each was swept over six weights (0.2, 0.5, 1.0, 1.4, 2.0, 3.0) on
**train only**; the weight minimising train error was then evaluated **once**
on holdout.

| Addition | best weight on train | train at best | **holdout** | beats baseline 23.0? |
|---|---|---|---|---|
| quadrant_cusps (placidus) | 0.5 | 27.0 | **48.5** | no |
| directed_angles | **0.2** | 24.0 | **23.0** | no |
| primary_directions (Ptolemy) | **0.2** | 24.0 | **23.0** | no |
| primary_directions (Naibod) | **0.2** | 29.0 | **23.0** | no |
| eclipse_on_angle | 3.0 | 28.0 | **49.0** | no |

Three of five bottom out at **0.2, the lowest weight offered**. Train is
asking for the contribution to be turned down as far as the sweep allows,
which is what an evaluator that adds noise rather than signal looks like.

### Per-addition findings

**3.1 quadrant cusps - a no-op under the default house system, harmful under
the alternative.** The premise was right: `rectification.py` computed `cusps`
and never read them, so `config.house_system` had no effect on the result.
Scoring them does not fix it. Measured directly on a training case:

| House system | distinct cusp-2 positions across the block | cusp 2 movement across the block |
|---|---|---|
| whole_sign | 1 | **0.000 deg** |
| placidus | 37 | 31.598 deg |

Whole-sign cusps *are* sign boundaries, so inside a rising-sign block they are
exactly constant - the identical 23.0 in the table is a mathematical no-op,
not a coincidence. Under Placidus the cusps do sweep, and the evaluator then
doubles the holdout error. The idea fails in both directions, for two
different reasons.

**3.2 directed angles - implemented, measured, worse.** Solar-arc directed Asc
and MC were being computed and filtered out one line later. Scoring them moves
holdout from 23.0 to 36.0.

**3.3 primary directions - the most promising on paper, no better in fact.**
It passes the variance filter clearly (CV 0.880) and is the sharpest factor
available in principle. Its holdout median equals the baseline's, but the
median hides a small degradation underneath: mean 39.5 vs 38.8, and the +/-15
hit rate falls from 33% to 25%. An unchanged median on n=12 is a coarse
statistic, not evidence of neutrality. Cumulatively it is the single worst
step in the stack (45.0).

**3.4 eclipse on angle - borrowed, measured, did not earn its place.** It has
the highest within-block CV of anything measured (1.193) and passes the Work
item 2 filter by construction, exactly as predicted. It still makes holdout
worse (31.0), and worse again at its best train weight (49.0). Sharpness is
not the same as correctness.

**3.5 event-to-technique matching - worse, and worse on train too.** The
motivating observation stands - agreement at the shipped orb is nearly free -
but restricting fast significators to fast events and slow to structural ones
does not fix it. Train 29.0 to 37.0, holdout 23.0 to 36.5.

### Reverted

All five. `astro_engine/` carries the four original techniques and nothing
else; `astro_engine/core.py` is back to its prior surface with no leftover
ARMC or right-ascension helpers. The rejected evaluators exist only in
`benchmarks/harness/candidate_engine.py`, a frozen, self-contained copy that
the service never imports and that keeps `ablation.py` and `weight_sweep.py`
reproducible.

Also unchanged, and now asserted by a test rather than left to be
rediscovered: **`config.house_system` still has no effect on a rectification
score.** Every shipped technique reads only `asc` and `mc`.

---

## The directions key, and what it costs

**Naibod (0 deg 59' 08" per year, 0.985556 deg/yr) was the key used**, with
Ptolemy (1.000000 deg/yr) measured alongside. Ptolemy was better on train
(24.0 vs 29.0) and identical on holdout (23.0 both), so the choice does not
rescue the technique either way.

The two keys disagree about when a direction perfects, and that disagreement
converts directly into birth-time uncertainty at roughly 1 degree of ARMC per
3.99 minutes:

| Age at event | Ptolemy arc | Naibod arc | difference | equivalent birth-time uncertainty |
|---|---|---|---|---|
| 20 | 20.000 deg | 19.711 deg | 0.289 deg | **1.2 min** |
| 40 | 40.000 deg | 39.422 deg | 0.578 deg | **2.3 min** |
| 60 | 60.000 deg | 59.133 deg | 0.867 deg | **3.5 min** |

**This sets a floor.** For a subject with events in mid-life, simply choosing
between the two standard keys moves the implied birth time by 2 to 3.5
minutes. Any primary-direction-based claim tighter than about +/-3 minutes is
asserting a precision the technique does not have, before any question of
whether the technique works at all.

---

## The rounding caveat, stated where it bites

13 of 41 known times fall on a round quarter-hour (11 of 29 train, 2 of 12
holdout). Registered times are commonly rounded by the registrar, so those
references carry roughly +/-5 to 15 minutes of their own error. **Every figure
below +/-5 minutes is unverifiable on this instrument**, which is why the
+/-5 columns above are reported but should not be read as accuracy.

The non-round sub-corpus is reported alongside the full corpus in every
ablation row above. It does not rescue the result - on holdout the non-round
median is **31.0** against the full-corpus 23.0, i.e. slightly worse on the
subset where the reference is most trustworthy.

| Split | n | in-block median | mean | <=5 | <=15 | <=30 | non-round n | non-round median |
|---|---|---|---|---|---|---|---|---|
| train | 29 | 29.0 | 39.6 | 14% | 38% | 55% | 18 | 29.0 |
| **holdout** | 12 | **23.0** | 38.8 | 0% | 33% | 58% | 10 | 31.0 |

---

## Work item 4 - honest confidence, shipped regardless

This ships whether or not the gate passes, and it did not pass.

**1. `residual_window_minutes` is no longer the confidence figure.** It is
kept in `suggested_best` because clients read it, but the measured complaint
about it is confirmed at corpus scale: across all 41 cases it evaluates to
**0 in 38 cases and 4 (one step) in 3 cases**. It carries almost no
information.

**2. A permutation null runs per request.** Event dates are shuffled within
the subject's own span, the whole grid is rescored, and the real peak's rank
in that distribution is returned as `permutation_percentile`. The seed is
derived from the request, so the result is deterministic for a given request
while remaining a genuine shuffle. This is the only calibrated number in the
response.

**3. A refusal state.** When the peak does not stand out from the null, or the
top candidates are not separable, `suggested_best.time` is `null`,
`confidence.refused` is `true`, and `confidence.reasons` says why. **The API
can now answer "cannot determine" instead of a time.**

**4. The full density curve** is returned so clients do not re-derive a peak.

**5. `ascendant_sign`** marks out-of-sign candidates `excluded` rather than
dropping them, so the density curve stays a complete picture of the window.
This is the hook stage 1 will use.

### What the refusal state actually does on this corpus

At default thresholds (`refusal_percentile` 0.90, `refusal_min_separation`
0.05, 20 trials), the engine **refuses 39 of 41 cases**, and 11 of 12 on
holdout. Given the gate result, refusing almost everything is the *correct*
behaviour: the engine genuinely cannot determine these birth times, and it now
says so instead of returning a confident wrong answer.

The two cases it does not refuse are not better ones:

| Bucket | n | median in-block error | median full-day error |
|---|---|---|---|
| not refused | 2 | 71.0 | 649.0 |
| refused | 39 | 26.0 | 301.0 |

With n=2 this establishes nothing, but it is certainly not evidence that the
non-refused bucket is more accurate, and it should be read as a warning
against treating "not refused" as a quality signal at these thresholds. The
percentile itself spans 0.00 to 0.95 with a median of 0.45 - the real peak
lands near the middle of its own null distribution, which is the same story
the gate tells.

---

## Performance

360 candidates, 12 events, shipped engine:

| Configuration | wall clock |
|---|---|
| `permutation_trials: 0` | **0.19 s** |
| `permutation_trials: 12` (default) | **2.49 s** |

The null multiplies the work by trials + 1. The default stays well inside the
10-second budget; a caller who wants the old speed can set
`permutation_trials: 0` and will get no calibrated confidence in exchange.

---

## The corpus

41 Rodden AA cases, committed under `benchmarks/corpus/train/` (29) and
`benchmarks/corpus/holdout/` (12). The split is stratified on the night-birth
and high-latitude flags and ordered within each stratum by a stable hash of
the case id, so it is reproducible from the fixtures alone and does not depend
on any measurement.

| | full | train | holdout |
|---|---|---|---|
| cases | 41 | 29 | 12 |
| night births (00:00-06:00) | 7 | 5 | 2 |
| born above 45 deg latitude | 10 | 7 | 3 |
| within 10 deg of the equator | **0** | 0 | 0 |
| round known times | 13 | 11 | 2 |

**The equator shortfall carries over from the previous run and stands as a
known limitation.** AA-rated equatorial births are scarce in Astro-Databank;
the candidates checked and the rating each actually carries are listed in
`RESULTS.md`. The lowest-latitude case in the corpus is Jim Morrison at
28.08 N, so nothing here speaks to engine behaviour at equatorial latitudes.

Cases added in this task were admitted on their actual Rodden rating, not on
convenience. Rejected during expansion: Madonna (A, mother's hospital record),
Frank Sinatra (father's memory), Amy Winehouse (uncertain), Lady Gaga (B),
Brad Pitt (A, and 6:21 vs 6:31 conflict), Brigitte Bardot (12:15 / 13:15 /
13:20 conflict), Celine Dion (A), Nicole Kidman (A, upgraded from C by an
astrologer rather than a document).

---

## The self-fulfilling test, replaced

`tests/test_rectification.py:44` generated its event dates from the answer's
Ascendant, searched a two-hour window around the answer, and enabled a single
technique. It validated the scorer against data the scorer produced, so it
passed whether or not the scorer worked. It is **replaced, not deleted**, by
corpus-backed tests against a real AA case with real dated events over a full
24-hour search, plus tests for the density curve, the `ascendant_sign` hook,
the refusal state, permutation determinism, and the `house_system` no-op.

The in-block assertion in the replacement is deliberately set at the engine's
*measured* behaviour, not at an aspiration. Its job is to fail if that
regresses, not to imply an accuracy the engine does not have.

---

## What this means

The information budget in the task brief is confirmed by measurement rather
than refuted. Reaching +/-5 minutes from a 24-hour prior needs about 7.2 bits.
Stage 1 can supply at most log2(12) = 3.6 bits, because every question a
client can answer about their own chart under whole-sign houses is a function
of the Ascendant sign. The engine supplies roughly 2.6 more inside the block,
and **this task found none of the remaining bits.**

Three of the five things tried were flat inside the block before they were
built - the variance filter caught sect, saros and, unexpectedly, profections,
and that filter did its job by preventing three implementations. The five that
were built and measured all failed. The one with the strongest theoretical
claim, primary directions, carries a 2 to 3.5 minute floor from the key choice
alone, before accuracy is considered.

The pre-registered decision applies: **variant B is dead.** Ship the shortlist
product and rewrite the promise. What ships from this task is Work item 4: an
engine that returns a calibrated confidence, a full density curve, and - for
39 of 41 corpus cases - an honest refusal.

---

# Appendix: block ranking and the in-block null

Measurement only. No scoring change, no tuning, no new evaluator: the shipped
engine at its defaults, with the permutation null switched off because it
cannot move the argmax and only the argmax is read here. Produced by
`benchmarks/block_ranking.py`; raw per-case output in
`benchmarks/block_ranking.json`.

Shuffled dates use 5 shuffles per case, drawn uniformly across the subject's
own event span, with the event count, category mix and date precision held
fixed. The true block is always the block containing the *known* time, so the
null asks whether random dates find the right block just as often.

Rank ties are broken against the engine: a block tying with the true block
counts as ranking above it. A flat scorer cannot be credited by accident.

## 1. Block ranking

Blocks ranked by their peak score. Chance is 8.3% for first, 25.0% for top 3.

### All 41 cases

| Ranking | | 1st | top 3 | median rank |
|---|---|---|---|---|
| Twelve two-hour clock blocks | real events | 14.6% | 39.0% | 5 |
| | shuffled dates | **17.6%** | 35.1% | 6 |
| Twelve rising-sign blocks | real events | 14.6% | 51.2% | 3 |
| | shuffled dates | **19.0%** | 40.5% | 4 |

### Holdout only (12 cases)

| Ranking | | 1st | top 3 | median rank |
|---|---|---|---|---|
| Twelve two-hour clock blocks | real events | 8.3% | 16.7% | 5.5 |
| | shuffled dates | **11.7%** | **30.0%** | 6.0 |
| Twelve rising-sign blocks | real events | 8.3% | 50.0% | 3.5 |
| | shuffled dates | **16.7%** | 36.7% | 5.5 |

### Real against its own null, directly

| Scope | Ranking | AUC (real ranks better than null) | mean rank difference | permutation p |
|---|---|---|---|---|
| all 41 | clock blocks | 0.497 | +0.02 | 0.53 |
| all 41 | rising-sign blocks | 0.517 | -0.19 | 0.35 |
| holdout | clock blocks | 0.465 | +0.48 | 0.71 |
| holdout | rising-sign blocks | 0.525 | -0.37 | 0.37 |

AUC 0.50 is chance. All four sit on it.

### Stated plainly

**The true block does not rank better than chance.**

Read on its own, the real-events row looks encouraging: the true rising-sign
block lands in the top 3 half the time against a 25% chance rate. The null
destroys that reading. Shuffled dates put the true block first *more often
than real dates do* in all four comparisons (17.6% vs 14.6%, 19.0% vs 14.6%,
11.7% vs 8.3%, 16.7% vs 8.3%), and the direct real-versus-null AUC is 0.497 to
0.525 with p between 0.35 and 0.71.

The above-chance top-3 rate is therefore a property of the grid, not of the
events. Blocks differ in width and in Ascendant speed, so some blocks
systematically collect higher peaks whatever dates are fed in, and the true
block is disproportionately likely to be one of them. Random dates exploit
that structure exactly as well as real ones.

On holdout the real numbers do not even clear chance in absolute terms:
first-place 8.3% is precisely 1 in 12, and clock-block top-3 at 16.7% is
*below* the 25% chance rate.

**This supersedes the earlier recorded figure of 25% / 42% / 58% for top-1 /
top-2 / top-3.** That figure was measured on 12 cases and, more importantly,
without a null control. On 41 cases the top-1 rate is 14.6%, and the null
shows the whole effect is structural. The correct conclusion is not that block
ranking got worse; it is that it was never measured against anything.

**Consequence for the product:** stage 1 cannot be delegated to the scorer.
Block selection has to come from the client questionnaire, because the engine
ranks the correct block no better than it ranks a wrong one.

## 2. In-block null

Inside the correct rising-sign block only, same block and same 4-minute grid
for both arms. Median block width 144 minutes (all) and 148 minutes (holdout),
so a block holds 36 to 37 candidate times.

The blind floor is the median |err| of a uniform pick among the block's own
candidate times - what you get by guessing inside a correctly identified
block.

### All 41 cases

| | median &#124;err&#124; | mean &#124;err&#124; | <=15 min | <=30 min | n |
|---|---|---|---|---|---|
| real events | **26.0** | 39.4 | **36.6%** | 56.1% | 41 |
| shuffled dates | 36.0 | 43.9 | 19.0% | 42.4% | 205 |
| blind uniform pick | 38.0 | - | - | - | - |

### Holdout only (12 cases)

| | median &#124;err&#124; | mean &#124;err&#124; | <=15 min | <=30 min | n |
|---|---|---|---|---|---|
| real events | **23.0** | 38.8 | **33.3%** | 58.3% | 12 |
| shuffled dates | 38.0 | 48.5 | 11.7% | 38.3% | 60 |
| blind uniform pick | 46.5 | - | - | - | - |

### Real against its own null, directly

| Scope | AUC (real beats null) | mean difference | permutation p |
|---|---|---|---|
| all 41 | 0.565 | -4.5 min | 0.15 |
| holdout | 0.605 | -9.7 min | 0.12 |

### Stated plainly

**Inside the correct block, real events do beat shuffled dates - directionally
and consistently, but not to statistical significance on this corpus.**

Every summary points the same way. The median error is 10 minutes lower on all
41 cases (26.0 vs 36.0) and 15 minutes lower on holdout (23.0 vs 38.0). The
+/-15 minute hit rate roughly doubles in both scopes (36.6% vs 19.0%; 33.3% vs
11.7%). Shuffled dates land essentially on the blind floor - null median 36.0
against a blind 38.0 on all cases - which is what a scorer with no information
should do, while real events sit clearly inside it.

What the direction does not yet have is significance. AUC is 0.565 and 0.605,
and a paired permutation test on the means gives p = 0.15 and p = 0.12. With
41 cases and 12 respectively, an effect this size is what you would see
somewhere between one time in six and one time in eight by chance. It is
suggestive, not established.

## What the two halves say together

These two results are not in tension, and together they are the clearest
statement of where the engine actually stands:

- **Choosing the block: no signal at all.** Chance-level against its own null,
  in both blockings, in both scopes.
- **Placing the time inside a known-correct block: real but small signal.**
  Better than shuffled dates and better than a blind pick on every summary
  statistic, at roughly p = 0.12 to 0.15.

That is consistent with the information budget. Stage 1 supplies the block and
must come from the questionnaire. Stage 2 has genuine information but, at a
median of 23 minutes on holdout against a blind floor of 46.5, it converts
about half the available range into accuracy - and stops far short of the 6
minutes the gate required and further still from the +/-5 the product
promised.

Neither of these measurements changes the gate verdict. The gate was evaluated
on the shipped engine's holdout in-block median of 23.0 minutes and it failed;
this appendix explains what that number is made of.
