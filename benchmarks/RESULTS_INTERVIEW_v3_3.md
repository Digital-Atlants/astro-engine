# Interview v3.3: Tier 3 was made reachable, measured, and dropped

**The spec's design decision failed its own gates, and the spec's own
pre-registered fallback was applied in the same task. There is no Tier 3. A
rising sign is never delivered on its own.**

Ranked verdicts for what ships: **G1 PASS > G6 n/a > G6-sun n/a > G7 FAIL >
G3 PASS > G8 n/a > G2 FAIL > G5 PASS > G4 PASS.**

One sentence, as the definition of done asks: **Tier 3 issuance is 0.0% for
sign-only and 0.0% for random because Tier 3 no longer exists — G8 passed at
85.4% but G6 failed at 30.85%, so the two could not pass together and the
pre-registered fallback was taken.**

The one remaining retune was **not spent**. It was scoped to the Tier 3
threshold, and the failure is not a threshold problem; the reason is below.

---

## 1. What was built, and what it measured

Work item 1 was implemented exactly as specified: tiers tested in order
1 → 2 → 3 → 4, with Tier 3's bar reduced to *all stage-1 pairs agree, zero
disagreements anywhere, sign mass ≥ 0.50*, no window condition and no
chance-agreement test.

Implementing it turned up a **second reason Tier 3 was unreachable in v3.2**,
which the previous spec had not identified. The bar being stricter than Tier
2's was real but not sufficient. The two-portrait confirmation only fired once
the leading signs already carried 70% of the sign mass — and two structural
answers never reach that. Measured: after a perfect element and modality
answer the top sign carries **0.23** of the mass. So the sign-only session was
never *offered* a portrait, could not establish a sign, and landed in Tier 4
no matter what Tier 3's bar said. Making the portrait step unconditional was
therefore part of making the tier reachable, and it is also what makes the
spec's own arithmetic for random correct: ¼ element × ⅓ modality × ½ portrait
= one in twenty-four.

With both changes in, **Tier 3 became reachable**: the sign-only answerer
reached it in **85.4%** of runs, comfortably passing G8's 80% bar, at a top
sign mass of 0.82–0.85.

Then the rest of the gate set was measured.

### Pre-fallback: the design as specified (41 cases × 40 seeds × 9 models)

| Answerer | T1 | T2 | T3 | T4 | **G1** T1 wrong | **G7** T2 wrong | **G6** T3 wrong sign | T3 wrong *of issued* | sign recovery | q |
|---|---|---|---|---|---|---|---|---|---|---|
| perfect | 73.2% | 19.5% | 0.0% | 7.3% | **0.00%** | **0.00%** | **0.00%** | — | 97.6% | 10 |
| iid-noisy | 10.9% | 24.8% | 10.6% | 53.7% | **3.05%** | **3.72%** | **0.18%** | 1.7% | 58.4% | 10 |
| adjacent-sign | 32.5% | 12.3% | 38.5% | 16.7% | **32.50%** | **10.91%** | **30.85%** | **80.2%** | 0.0% | 10 |
| random | 0.4% | 4.1% | 0.2% | 95.3% | **0.43%** | **3.90%** | **0.18%** | 100% | 10.8% | 10 |
| dont-know-heavy | 4.3% | 31.3% | 0.1% | 64.3% | **0.00%** | **0.00%** | **0.00%** | — | 61.2% | 10 |
| sign-only | 0.0% | 0.0% | **85.4%** | 14.6% | **0.00%** | **0.00%** | **0.00%** | 0.0% | 97.6% | 10 |
| *correlated-noisy* | *22.5%* | *12.0%* | *20.1%* | *45.4%* | *5.18%* | *2.26%* | *0.73%* | *3.7%* | *58.6%* | *10* |
| *impostor* | *65.8%* | *26.8%* | *0.0%* | *7.3%* | *65.85%* | *26.83%* | *0.00%* | — | *0.0%* | *10* |
| *sun-attributor* | *0.0%* | *7.6%* | *0.0%* | *92.4%* | *0.00%* | *4.09%* | *0.00%* | — | *14.6%* | *9* |

| Rank | Gate | Required | Measured | Verdict |
|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | **32.50%** (adjacent-sign) | **FAIL** |
| 2 | G6 Tier-3 wrong sign | ≤5% per model | **30.85%** (adjacent-sign) | **FAIL** |
| 3 | G6-sun | ≤5% | 0.00% | PASS |
| 4 | G7 Tier-2 wrong window | ≤5% per model | **10.91%** (adjacent-sign) | **FAIL** |
| 5 | G3 refusal | random Tier 4 ≥90% | 95.30% | PASS |
| 6 | G8 Tier 3 reachable | sign-only Tier 3 ≥80% | **85.37%** | PASS |
| 7 | G2 usefulness | perfect Tier 1 ≥90% | 73.17% | **FAIL** |
| 8 | G5 sign recovery | perfect ≥90%, iid ≥60% | 97.56% / **58.35%** | **FAIL** |
| 9 | G4 cost | perfect median ≤10 | 10 | PASS |

**Five of nine gates failed, including the two highest-ranked.**

---

## 2. Why G6 failed, and why no threshold could have saved it

Tier 3 was reachable and it was **wrong**: the adjacent-sign answerer was
handed a Tier 3 rising sign in **38.5%** of runs, and **80.2% of those signs
were wrong** — 30.85% of all its runs, against a 5% bar.

This is not a tuning failure and the retune would have been wasted on it. The
adjacent-sign answerer describes itself consistently one sign over. In a
sign-only session that produces:

- all three stage-1 pairs agreeing with themselves — the answers are
  *consistent*, they are just consistently displaced;
- no channel conflict, because the portrait it confirms is the one the element
  and modality answers already pointed at;
- sign mass concentrated hard (0.82–0.85) on the neighbouring sign.

That session is **numerically identical to an honest one**. There is no value
of `tier3_sign_mass` that separates them, because the quantity the threshold
reads is the same in both. It is the impostor problem restated at sign
resolution: an internally coherent wrong answer cannot be caught by a
coherence test.

Note what makes this specific to a *sign-only* claim. On windows, the
adjacent-sign answerer does get caught, because its decan and mover-house
answers come from the true minute and contradict the displaced sign — which is
why its G1 rate was 1.04% in v3.2. Tier 3 asks for no such corroboration by
construction: the spec froze its bar as stage-1 agreement with **no window
condition**, and stage 1 is exactly the part the answerer is coherently wrong
about.

### The pre-registered fallback, applied

> *"if the remaining retune cannot make G6 (random included) and G8 pass
> together, **Tier 3 is dropped** — Tier 2 and Tier 4 carry the range, and no
> sign is ever delivered on its own."*

G8 passed at 85.4%. G6 failed at 30.85%. They cannot pass together, and no
retune closes the gap. **Tier 3 is dropped.** `assign_tier` has tiers 1, 2 and
4; `rising_sign` is always `null`; a test walks a full interview and asserts
the tier is never 3.

The information is not thrown away, only the claim. `sign_blocks` still
returns a mass per sign — a description of what the answers support rather
than an assertion about which sign it is.

---

## 3. The larger finding: the portrait threshold is load-bearing for safety

**G1 failed at 32.50% for the adjacent-sign answerer, with 100% of those Tier
1 windows wrong.** That is not Tier 3's doing, and dropping Tier 3 does not
fix it. It was caused by making the portrait step unconditional.

| | portrait gated at 70% mass (v3.2) | portrait unconditional (v3.3 as specified) |
|---|---|---|
| adjacent-sign G1 | **1.04%** | **32.50%** |
| adjacent-sign G7 | 4.76% | 10.91% |
| perfect Tier 1 | 82.93% | 73.17% |
| iid-noisy sign recovery | 63.78% | 58.35% |

The mechanism: asking the portrait while the top sign still carries 0.23 of
the mass lets an answerer confirm a sign that **nothing has corroborated**,
and the confirmation then concentrates the posterior hard on it before any
independent channel has spoken. Waiting for the mass means the portrait can
only ever confirm what something else already suggested. That ordering was
doing real safety work in v3.2 and nobody knew, because v3.2's Tier 3 was
unreachable for two independent reasons and this run is the first to separate
them.

Since the unconditional portrait existed **only** to serve Tier 3, and Tier 3
is gone, the threshold is restored. G1 is the top-ranked gate; keeping a
32.5% failure to serve a tier that no longer exists would be indefensible.

---

## 4. What ships (41 cases × 40 seeds × 9 models)

Tiers 1, 2, 4. Portrait threshold restored. Sun detector off. Decan trust
capped at 0.50.

| Answerer | T1 | T2 | T4 | **G1** T1 wrong | **G7** T2 wrong | T1 contains truth | T1 median err | sign recovery | q |
|---|---|---|---|---|---|---|---|---|---|
| perfect | 82.9% | 12.2% | 4.9% | **0.00%** | **0.00%** | 100% | 4 min | 92.7% | 10 |
| iid-noisy | 10.8% | 25.6% | 63.6% | **2.01%** | **3.72%** | 81.5% | 5 min | 61.8% | 10 |
| adjacent-sign | 1.6% | 4.5% | 93.9% | **1.59%** | **4.51%** | 0.0% | 88 min | 0.0% | 9 |
| random | 0.2% | 5.1% | 94.7% | **0.18%** | **5.06%** | 0.0% | 373 min | 12.3% | 10 |
| dont-know-heavy | 2.6% | 37.7% | 59.6% | **0.00%** | **0.00%** | 100% | 5 min | 51.8% | 10 |
| sign-only | 0.0% | 0.0% | **100.0%** | **0.00%** | **0.00%** | — | — | 92.7% | 9 |
| *correlated-noisy* | *25.1%* | *11.1%* | *63.8%* | *5.73%* | *1.83%* | *77.2%* | *5 min* | *62.6%* | *10* |
| *impostor* | *87.8%* | *9.8%* | *2.4%* | *87.80%* | *9.76%* | *0.0%* | *358 min* | *0.0%* | *10* |
| *sun-attributor* | *2.7%* | *4.8%* | *92.4%* | *0.67%* | *2.87%* | *75.6%* | *8 min* | *14.6%* | *9* |

| Rank | Gate | Required | Measured | Verdict |
|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | 2.01% (iid-noisy) | **PASS** |
| 2 | G6 Tier-3 wrong sign | ≤5% per model | — | **n/a, Tier 3 removed** |
| 3 | G6-sun | ≤5% | — | **n/a, Tier 3 removed** |
| 4 | G7 Tier-2 wrong window | ≤5% per model | **5.06%** (random) | **FAIL** |
| 5 | G3 refusal | random Tier 4 ≥90% | 94.70% | **PASS** |
| 6 | G8 Tier 3 reachable | sign-only Tier 3 ≥80% | — | **n/a, Tier 3 removed** |
| 7 | G2 usefulness | perfect Tier 1 ≥90% | 82.93% | **FAIL** |
| 8 | G5 sign recovery | perfect ≥90%, iid ≥60% | 92.68% / 61.77% | **PASS** |
| 9 | G4 cost | perfect median ≤10 | 10 | **PASS** |

**G7 fails by one run.** 5.06% of 1,640 random runs is 83 wrong Tier 2
shortlists; the bar allows 82. v3.2 measured 4.63% on a seed set that cannot
be reproduced (it used `hash()`, which is salted per process — v3.3 seeds with
SHA-256 instead, which is why this is the first v3.x figure that can be
re-derived). The honest statement is that random's Tier 2 rate sits **on** the
5% line rather than clearly inside or outside it, and one seed set will not
settle it. It is not called a pass.

**G2 fails as it always has**, at the same 82.93% measured in v2, v3.1 and
v3.2. Its other three conditions pass well: Tier 1 windows never exceed 30
minutes, contain the truth **100%** of the time, and carry a median error of
**4 minutes**. In roughly one run in six the region the answers genuinely
agree on is wider than the 30-minute cap and a Tier 2 shortlist is the correct
answer. Reaching 90% means widening the cap, which buys the seventh-ranked
gate with the promise the first-ranked one makes.

---

## 5. Work item 3c: sun-sign self-attribution

### The exposure, before any detector

This is the largest single finding in the report that the spec did not already
predict the size of. Measured with Tier 3 present and the detector off:

| sun-attributor, detector off | rate |
|---|---|
| Tier 3 issued | **72.6%** |
| **Tier 3 wrong sign, of all runs** | **59.76%** |
| Tier 1 issued | 4.2% |
| Tier 1 wrong window | 1.46% |
| sign recovery | 14.6% |

An answerer who describes itself by its Sun sign — the documented effect (van
Rooij 1994) — walked away with a **wrong rising sign in three runs out of
five**. Its sign recovery is 14.6%, about the one-in-twelve chance agreement
you would expect plus noise, confirming the model is doing what it says.

This is second only to the impostor as a way to get a confident wrong answer
out of the engine, and unlike the impostor it does not require the person to
be answering for somebody else. They are answering honestly about the wrong
thing.

### The detector, and why it is off

Frozen before measurement: when the element answer, the modality answer and
the confirmed portrait all name the Sun sign, the three stage-1 pairs count as
**one** pair for Tier 1, and Tier 3 additionally required decan-channel
agreement. Nothing is filtered — a test asserts the posterior stays strictly
positive everywhere.

Under the pre-fallback ladder it worked, and G6-sun passed at **0.00%**
(sun-attributor Tier 3 0.0%, Tier 1 0.0%, flagged on 82.9% of its runs). But:

| perfect answerer, pre-fallback ladder | Tier 1 |
|---|---|
| detector off | **80.5%** |
| detector on | **73.2%** |
| cost | **−7.3 points** |

The spec allowed at most 3 points. The 7.3 is not noise and it is not
fixable: it is exactly the **7.32%** of corpus cases whose rising sign
genuinely *is* their Sun sign, whose honest stage-1 answers the detector
cannot distinguish from a recalled stereotype. So, per work item 3c step 4,
**the detector is left off** and the finding stands on its own.

Two further measurements, because the fallback changed the ladder underneath
the decision:

- **Under the shipped ladder the detector is free but nearly inert.** Perfect
  Tier 1 is **82.93% with it on and 82.93% with it off** — the discount no
  longer costs anything, because with the portrait threshold restored the
  perfect answerer has non-stage-1 pairs to spare. But it only flags **16.7%**
  of sun-attributor runs (against 82.9% before), because the flag needs all
  three stage-1 channels answered and the portrait question is now often never
  asked. Its effect on sun-attributor safety is correspondingly small:
  G1 0.67% → 0.55%.
- **Dropping Tier 3 removes most of the exposure by itself.** The
  sun-attributor now lands in Tier 4 in 92.4% of runs and its Tier 1
  wrong-window rate is 0.67%. The 59.76% wrong-sign rate was a Tier 3
  phenomenon, and Tier 3 is gone.

**This is an owner decision I did not take.** Switching the detector on is now
free and would be a small safety gain, but the pre-registered rule said to
leave it off on a 3-point test taken against a ladder that no longer exists.
Turning it on would be a post-hoc choice against a retired gate, so it is
reported rather than made.

---

## 6. Work item 3b: decan trust sensitivity (reported, not tuned)

`decan_reliability` is **0.50** against a session default of 0.60. Reason
recorded in `docs/trust_default.md`: at 51° latitude a decan rises in 18–57
minutes and a self-report of appearance does not carry that precision.

Sweep at 20 seeds, shipped ladder:

| decan r | perfect T1 | iid-noisy G1 | *correlated-noisy G1* | *impostor G1* | random G7 | iid sign recovery |
|---|---|---|---|---|---|---|
| 0.40 | 82.93% | **2.44%** | *5.61%* | *87.80%* | 5.24% | 63.7% |
| **0.50** | 82.93% | **2.44%** | *6.22%* | *87.80%* | 5.12% | 63.7% |
| 0.60 | 82.93% | **2.68%** | *6.83%* | *90.24%* | 5.12% | 63.7% |

The trade has the same clean shape as the `channel_reliability` argument:
**lowering decan trust costs the useful answerer nothing** — perfect Tier 1
and sign recovery are identical at all three values — and buys a monotone
safety gain on the answerers that get things wrong, with correlated-noisy
falling 6.83% → 5.61% and the impostor 90.24% → 87.80%.

Stated plainly: **the sweep says 0.40 is better than the shipped 0.50 on every
number that moves, at no measured cost.** The spec said to report this row and
not tune it, so 0.50 ships. Lowering it to 0.40 is an owner call with the
evidence already in hand.

---

## 7. Honest floors, unchanged

**Impostor: 87.80%.** Someone answering consistently for a different birth
time confirms the portrait for the sign they are answering *as*, so nothing
conflicts, no pair breaks, and they are handed a confident wrong window nearly
nine times in ten. No tier rule touches this, and dropping Tier 3 does not
help: the impostor was never reaching Tier 3 anyway. It is down from 90.24% in
v3.2 only because of the decan cap.

**Correlated-noisy: 5.73%**, over the 5% line it is not held to, and the worst
non-impostor number in the report. This is the model closest to a real client.
It is *better* than v3.2's 6.34%, and the decan sweep above shows it is the
model most responsive to decan trust.

**Adjacent-sign, in the shipped configuration: G1 1.59%**, but note what that
means — its 1.6% Tier 1 rate contains **zero** correct windows and a median
error of 88 minutes. The engine is safe here by refusing, not by being right.

---

## 8. Copy: the council file imported, 350 of 353 keys covered

`docs/copy_drafts.md` is the council-approved file (100 Russian rows, all
`approved`). The direction of `benchmarks/build_copy_manifest.py` is reversed:
through v3.2 it *generated* the drafts file from templates, and it now **reads**
it and resolves each engine key to the Russian behind it, exiting non-zero on
any gap.

| Channel | keys | with approved Russian |
|---|---|---|
| element | 8 | 8 |
| modality | 6 | 6 |
| sign_portrait | 24 | 24 |
| decan | 72 | 72 |
| mover_house | 240 | 240 |
| portrait | 3 | **0** |
| **total** | **353** | **350** |

**The three engine keys that still lack a Russian row are
`portrait.window.0`, `portrait.window.1` and `portrait.window.2`.** The copy
file does not claim to cover them and should not: that question distinguishes
one surviving time window from another, and the client renders it from the
placements the engine returns in `distinguishing_placements`, not from a fixed
sentence. They are listed in an exact `UNCOVERED` set, so the build fails both
if a new key loses its Russian row **and** if one of these three ever gains
one and the exemption stops being true.

**One caveat on the import, which the owner needs to act on.** The supplied
file reached this session with its Cyrillic mis-encoded — UTF-8 bytes rendered
as Latin-1 with the continuation bytes stripped. A byte-level round-trip was
attempted and fails to decode, so the Russian was recovered by reading the
damaged text rather than by copying it. The structure matches the council's
coverage table exactly (38 / 12 / 10 / 36 / 4 = 100 rows), and no row is
missing, but the wording is a faithful reconstruction rather than a byte-exact
copy. **Diff `docs/copy_drafts.md` against the original before the web imports
it**, or re-send the file and it will be replaced verbatim.

---

## 9. Work item 2: the SHA in `/health`

```json
{"status": "ok", "version": "1.0.0", "git_sha": "<commit>",
 "interview_contract": {"answer_fields": ["answer_ids", "channel",
   "offered_tag_ids", "question_id", "source", "subject", "variant",
   "windows"]}}
```

`git_sha` resolves from `GIT_SHA`, else `RAILWAY_GIT_COMMIT_SHA`, else the
checkout's `.git`, else the literal string `unknown` — which is a real state
for a slim container image and is reported as such rather than papered over
with the package version. A test asserts the field and the contract list.

---

## 10. Constraints held

- `git diff main -- astro_engine/rectification.py astro_engine/core.py
  astro_engine/charts.py` is **empty**. Scoring untouched.
- ≤4 options and no clock time in any question — the v3 tests still run.
- Reweight, never zero; `cannot_choose` multiplies nothing; the detector
  filters nothing (asserted).
- Thresholds frozen before measurement. **Retune log: empty. The one
  remaining retune was not spent**, because the Tier 3 threshold was not the
  binding constraint — an internally coherent wrong answer reads identically
  to a correct one at the threshold, so no value of it separates them.
- No LLM in the path; deterministic and seeded, and for the first time in v3.x
  the seeds are reproducible (SHA-256 rather than salted `hash()`).
- 97 tests pass.

## 11. What is left for the owner

1. **Correct nothing in the copy — but diff it.** See the encoding caveat in
   section 8. The three uncovered keys are `portrait.window.{0,1,2}` and they
   are uncovered by design.
2. **Two free improvements the measurements support and the rules forbade me
   from taking**: lower `decan_reliability` to 0.40 (section 6), and switch
   `sun_sign_detector` on (section 5). Both cost the perfect answerer nothing
   in the shipped configuration.
3. **G7 sits on its bar at 5.06%.** One more seed set would settle which side
   it is on; it is reported as a failure rather than rounded down.
4. **The real ceiling is unchanged and is not a tier problem.** A person who
   answers coherently for the wrong time or the wrong sign gets a confident
   wrong answer, and every coherence test in the engine is blind to it by
   construction. Catching that needs a channel the person cannot self-describe
   — which is what `/v1/interview/compare` exists to find out.
