# Interview v3.3.1: detector on, decan trust at 0.40, and a retune that could not be spent

Three things were asked for. Two are done and measured. The third — spending
the last retune on `tier2_chance_p` — **could not be done**, and the reason is
measured rather than argued: **not one of the 593 Tier 2 sessions on the
training split lies in the band the grid sweeps**, so all five values produce
byte-identical results. The quantity the parameter tests is bimodal, and the
grid sits in the gap.

**Ranked verdicts on the full corpus: G1 PASS > G7 FAIL > G3 PASS > G2 FAIL >
G5 PASS > G4 PASS.** On the 12 holdout cases scored alone, **G1 also fails**.
Both statements are below, because reporting only the first would be
misleading.

---

## 1. The sun-attribution detector is on by default

`InterviewConfig.sun_sign_detector` now defaults to `True`.

The v3.3 measurement that defaulted it off was taken against the tier ladder
v3.3 then abandoned. Re-measured under the shipped ladder — no Tier 3,
portrait threshold restored — the cost is gone:

| perfect answerer | Tier 1 |
|---|---|
| detector off (v3.3 shipped) | **82.93%** |
| detector on (v3.3.1) | **82.93%** |

The 7.3-point cost that triggered the pre-registered rule was an artefact of
the unconditional portrait step. With the portrait threshold restored the
perfect answerer has non-stage-1 pairs to spare, so discounting the three
stage-1 pairs to one no longer drops it below Tier 1's bar. **G2, G3, G4 and
G5 are unchanged to the digit.**

What it buys is small but real and in the right direction:

| | detector off | detector on |
|---|---|---|
| sun-attributor G1 | 0.67% | **0.49%** |
| sun-attributor Tier 4 | 92.4% | 92.5% |
| random G1 | 0.18% | **0.12%** |

Flag rates under the shipped ladder: it fires on **7.3%** of perfect runs
(exactly the share of the corpus whose rising sign genuinely is its Sun sign —
the false positives, and they now cost nothing) and on **16.7%** of
sun-attributor runs. That second number is low, and honestly so: the flag
needs all three stage-1 channels answered, and with the portrait threshold
restored the portrait question is often never asked. **The detector is free
but weak.** It is not what is holding the sun-attributor's numbers down —
dropping Tier 3 did that.

## 2. Decan trust is 0.40

Applied as instructed, on the v3.3 sensitivity row. It is the only half of the
retune that moved anything:

| | decan 0.50 (v3.3) | decan 0.40 (v3.3.1) |
|---|---|---|
| *correlated-noisy G1* | *5.73%* | ***5.18%*** |
| iid-noisy G1 | 2.01% | 2.01% |
| iid-noisy G7 | 3.72% | **3.41%** |
| random G7 | 5.06% | 5.18% |
| perfect Tier 1 | 82.93% | 82.93% |
| iid-noisy sign recovery | 61.77% | 61.77% |

Correlated-noisy — the model closest to a real client — improves by 0.55
points at no cost to the useful answerer, which is what the v3.3 sweep
predicted. Random's Tier 2 rate moves the wrong way by 0.12 points, inside the
noise of a single seed set.

## 3. The retune: `tier2_chance_p` is inert

Discipline first: the sweep saw **only the 29 training cases**; the 12 holdout
cases were scored once afterwards, for the winner and for the 0.20 baseline;
the baseline was in the grid so the retune had to earn a change; ties broke
toward Tier 2 coverage, because the failing gate is trivially satisfied by
refusing everybody.

Grid frozen before running: {0.20, 0.15, 0.10, 0.05, 0.02}. Train, 20 seeds:

| tier2_chance_p | G1 worst | G7 worst | G3 random T4 | G2 perfect T1 | G5 iid | dont-know-heavy T2 |
|---|---|---|---|---|---|---|
| **0.20** (baseline) | 2.59% | 5.86% | 94.8% | 82.8% | 64.7% | 35.9% |
| 0.15 | 2.59% | 5.86% | 94.8% | 82.8% | 64.7% | 35.9% |
| 0.10 | 2.59% | 5.86% | 94.8% | 82.8% | 64.7% | 35.9% |
| 0.05 | 2.59% | 5.86% | 94.8% | 82.8% | 64.7% | 35.9% |
| 0.02 | 2.59% | 5.86% | 94.8% | 82.8% | 64.7% | 35.9% |

**Every row is identical.** Not close — identical. A ten-fold change in the
parameter changes nothing, so the retune is not a choice between options and
**it is recorded as not spent.**

### Why, measured rather than asserted

`chance_agreement` returns **1.0 by construction** when the channels'
supported regions do not intersect, and a product of small partition
probabilities when they do. There is nothing in between, so the quantity the
threshold reads is bimodal. Distribution at the point Tier 2 is decided
(41 cases × 6 seeds):

| Answerer | median chance_p | fraction at 1.0 | max chance_p among sessions that reached Tier 2 |
|---|---|---|---|
| perfect | 3.3 × 10⁻⁷ | 0% | 4.7 × 10⁻⁵ |
| iid-noisy | 1.0 | 51% | 1.7 × 10⁻³ |
| random | 1.0 | 76% | **8.3 × 10⁻²** |
| dont-know-heavy | 1.3 × 10⁻³ | 20% | 6.9 × 10⁻³ |

The decisive count is how many Tier 2 sessions actually sit inside the swept
band, per split (41 cases × 20 seeds × 9 models):

| Split | Tier 2 sessions | with chance_p in [0.02, 0.20) | which model |
|---|---|---|---|
| **train** | 593 | **0** | — |
| holdout | 278 | **1** (0.36%) | random |

**On train, not one session in 593 lies in the band the grid sweeps.** That is
why five values produce byte-identical output: there is nothing there for the
threshold to cut. The retune had no signal to act on, and that is as much a
fact about a 29-case training split as about the engine.

Note the one exception, because it is the reason the flat table above is not
the whole story: random's Tier 2 maximum on the **full** corpus is
8.3 × 10⁻², above two of the grid values. Exactly one holdout session sits
there. Had the grid been chosen with holdout in view, the best it could do is
remove that single session — moving random's holdout G7 from 5.21% to 5.00%,
which is *on* the bar rather than inside it. A one-session knife edge is not a
fix for a gate that fails on every split.

**I did not extend the grid after seeing any of this.** Picking a value
because I can now see where the one qualifying session sits would be choosing
a threshold from the data meant to test it — on the holdout split, which
exists precisely to prevent that. If this region is worth exploring it needs a
new pre-registered grid and a fresh holdout, not this retune.

**The honest conclusion is that `tier2_chance_p` is not the lever for G7.** It
is a guard against a specific failure — channels that agree only because they
could not disagree — and it does that job. It is not a dial for how willing
Tier 2 is to answer. That dial is `tier2_mass` and the window count and width
conditions, none of which were in scope here.

---

## 4. What ships (41 cases × 40 seeds × 9 models)

Detector on, decan trust 0.40, `tier2_chance_p` unchanged at 0.20, tiers 1/2/4.

| Answerer | T1 | T2 | T4 | **G1** T1 wrong | **G7** T2 wrong | sign recovery | detector flagged | q |
|---|---|---|---|---|---|---|---|---|
| perfect | 82.9% | 12.2% | 4.9% | **0.00%** | **0.00%** | 92.7% | 7.3% | 10 |
| iid-noisy | 10.7% | 25.0% | 64.3% | **2.01%** | **3.41%** | 61.8% | 2.2% | 10 |
| adjacent-sign | 1.6% | 4.5% | 93.9% | **1.59%** | **4.51%** | 0.0% | 0.0% | 9 |
| random | 0.1% | 5.3% | 94.6% | **0.12%** | **5.18%** | 12.3% | 0.3% | 10 |
| dont-know-heavy | 2.6% | 37.0% | 60.4% | **0.00%** | **0.00%** | 51.8% | 2.4% | 10 |
| sign-only | 0.0% | 0.0% | 100.0% | **0.00%** | **0.00%** | 92.7% | 0.0% | 9 |
| **sun-attributor** | **2.6%** | **4.9%** | **92.5%** | **0.49%** | **2.99%** | 14.6% | 16.7% | 9 |
| *correlated-noisy* | *24.3%* | *10.8%* | *64.9%* | *5.18%* | *1.71%* | *62.6%* | *3.7%* | *10* |
| *impostor* | *87.8%* | *9.8%* | *2.4%* | *87.80%* | *9.76%* | *0.0%* | *7.3%* | *10* |

| Rank | Gate | Required | Full corpus | Train | **Holdout** |
|---|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | **2.01%** PASS | 2.59% PASS | **5.42% FAIL** |
| 2 | G7 Tier-2 window | ≤5% per model | **5.18%** FAIL | 5.86% FAIL | **6.04% FAIL** |
| 3 | G3 refusal | random T4 ≥90% | 94.57% PASS | 94.8% PASS | 94.79% PASS |
| 4 | G2 usefulness | perfect T1 ≥90% | 82.93% FAIL | 82.8% FAIL | 83.33% FAIL |
| 5 | G5 sign recovery | perfect ≥90%, iid ≥60% | 92.68% / 61.77% PASS | — / 64.7% PASS | 91.67% / 62.08% PASS |
| 6 | G4 cost | perfect median ≤10 | 10 PASS | 10 PASS | 10 PASS |

### G1 passes on the full corpus and fails on holdout

This is the result I least want to round off. **G1 is 2.01% on all 41 cases,
2.59% on train, and 5.42% on the 12 holdout cases** — over the bar. The
offender is the adjacent-sign answerer, whose holdout Tier 1 rate is 5.4% with
**zero** correct windows among them.

480 runs across only 12 distinct charts is a thin sample and 5.42% is 26 runs,
so this is not a confident failure. But it is not noise to be waved away
either: the whole point of holding 12 cases back is that the number computed
on them is the one that has not been looked at while decisions were made. The
correct statement is **G1's margin is thinner than the full-corpus figure
suggests, and on unseen charts it is at or over the line.**

### G7 fails on all three splits

5.18% full, 5.86% train, 6.04% holdout — and on holdout the worst model is
**sun-attributor at 6.04%**, which is exactly why item 3 asked for it to be
gated. Adding it to the gated set found a failure that was previously being
reported beside the gates rather than by them. That is the gate doing its job.

G7 has now failed in v3.3 (5.06%) and v3.3.1 (5.18%) on two independent seed
sets and on every split. It is no longer reasonable to call it marginal. What
is failing is Tier 2's willingness to hand a shortlist to an answerer whose
answers do not support one, and `tier2_chance_p` is not the parameter that
governs that.

### G2, unchanged since v2

82.93%, against 90%. Its other conditions pass well: Tier 1 windows never
exceed 30 minutes, contain the truth 100% of the time, median error 4 minutes.
In roughly one run in six the region the answers genuinely agree on is wider
than the 30-minute cap and a Tier 2 shortlist is the right answer.

---

## 5. The sun-attributor under the shipped ladder, as item 3 asked

| | Tier 1 | Tier 2 | Tier 4 | G1 | G7 | sign recovery |
|---|---|---|---|---|---|---|
| full corpus | 2.6% | 4.9% | **92.5%** | **0.49%** | **2.99%** | 14.6% |
| holdout | 2.9% | 8.1% | 89.0% | **0.42%** | **6.04%** | 8.3% |

It passes G1 comfortably on both splits and **fails G7 on holdout**. Its sign
recovery is 14.6% / 8.3% — at or below the one-in-twelve chance rate,
confirming the model does what it claims: this answerer has no information
about its rising sign at all, and the engine correctly refuses it in nine
cases out of ten.

For context, the exposure this model represented in v3.3 before Tier 3 was
dropped was a **wrong rising sign in 59.76% of all runs**. That is gone, and
the detector is not what removed it — removing Tier 3 did.

---

## 6. Copy: reconciled with the owner's file

The council file was re-supplied correctly encoded during this task and
`docs/copy_drafts.md` is now **byte-identical** to
`docs/interview_copy_drafts_ru_approved_v3_3.md`.

The v3.3 reconstruction, made from a mis-encoded attachment, is now checkable
against the original: **104 of 105 rows matched byte for byte. One did not** —
house 8 read «кризисы и страхи» where the council wrote «кризисы и утраты».
The caveat in the v3.3 report was warranted, and a test now asserts the two
files stay identical, since a byte comparison is the only check that would
have caught a single substituted word.

Coverage is unchanged: **350 of 353 engine keys** resolve to approved Russian;
the three that do not are `portrait.window.{0,1,2}`, uncovered by design.

---

## 7. Constraints held

- `git diff main -- astro_engine/rectification.py astro_engine/core.py
  astro_engine/charts.py` is **empty**. Scoring untouched.
- Train/holdout discipline: the sweep saw train only; holdout was scored once,
  after the choice; the grid was frozen before running and **was not extended
  after seeing the distribution**.
- **Retune ledger: not spent.** `tier2_chance_p` stays at 0.20 because no
  value in the grid changes any outcome. `decan_reliability = 0.40` is an
  owner decision taken on the v3.3 sensitivity row, not a retune choice.
- Reweight, never zero; the detector filters nothing (asserted by test).
- ≤4 options, no clock time in any question.
- No LLM; deterministic, SHA-256 seeded, reproducible.
- 98 tests pass.

## 8. What I would put in front of the owner next

1. **G7 is a real, repeated failure and needs a lever that exists.** Two seed
   sets, three splits, never inside the bar. The parameters that actually
   govern Tier 2's willingness to answer are `tier2_mass` and the window
   count and width limits. That needs a pre-registered experiment of its own.
2. **G1's holdout margin.** 2.01% full against 5.42% holdout on 12 charts. A
   larger corpus would settle whether the full-corpus figure is optimistic;
   the adjacent-sign answerer is the one to watch.
3. **The detector is free but weak** (16.7% of sun-attributor sessions
   flagged). It only fires when all three stage-1 channels are answered, which
   the restored portrait threshold makes uncommon. Making it fire on element +
   modality alone would raise its coverage and is measurable.
4. **The ceiling is unchanged and is not a threshold problem.** A person
   answering coherently for the wrong time or the wrong sign gets a confident
   wrong answer — impostor 87.80% — and every coherence test in the engine is
   blind to it by construction. `/v1/interview/compare` on live sessions is
   the only thing that moves this.
