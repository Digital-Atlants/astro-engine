# Interview v3.2: Tier 3 must cohere; copy as Russian atoms

**Ranked verdicts — G1 PASS, G6 PASS, G7 PASS, G3 PASS, G2 FAIL, G5 PASS,
G4 PASS.** Six of seven gates pass, and the one failure is the second-lowest
ranked.

The change did what it was asked to do:

> **Random answering now lands in Tier 4 in 95.1% of runs (was 71.0%), reaches
> Tier 3 in 0.0% (was 24.4%), and delivers a wrong rising sign in 0.00% of
> runs (was 21.6%).**

**But read the next section before treating G6 as solved.** Tier 3 did not get
more accurate — it stopped being issued at all, to anybody. That is a real
result and it needs stating plainly rather than being banked as a passing gate.

The remaining retune was **not spent**; the reason is given below.

---

## Gate results (41 cases × 40 seeds × 7 models)

| Answerer | T1 | T2 | T3 | T4 | **G1** T1 wrong window | **G7** T2 wrong window | **G6** T3 wrong sign | sign recovery | questions |
|---|---|---|---|---|---|---|---|---|---|
| perfect | 82.9% | 12.2% | 0.0% | 4.9% | **0.00%** | **0.00%** | **0.00%** | 92.7% | 10 |
| iid-noisy | 12.9% | 26.4% | 0.0% | 60.7% | **2.62%** | **3.11%** | **0.00%** | 63.8% | 10 |
| adjacent-sign | 1.0% | 4.8% | 0.0% | 94.2% | **1.04%** | **4.76%** | **0.00%** | 0.0% | 9 |
| random | 0.1% | 4.8% | 0.0% | 95.1% | **0.06%** | **4.63%** | **0.00%** | 11.9% | 10 |
| dont-know-heavy | 3.2% | 38.7% | 0.1% | 58.1% | **0.00%** | **0.00%** | **0.00%** | 51.6% | 10 |
| *correlated-noisy* | *25.4%* | *11.3%* | *0.0%* | *63.3%* | *6.34%* | *1.77%* | *0.00%* | *62.3%* | *10* |
| *impostor* | *90.2%* | *7.3%* | *0.0%* | *2.4%* | *90.24%* | *7.32%* | *0.00%* | *0.0%* | *10* |

| Rank | Gate | Required | Worst measured | Verdict |
|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | 2.62% (iid-noisy) | **PASS** |
| 2 | G6 Tier-3 wrong sign, random included | ≤5% per model | 0.00% (all) | **PASS** |
| 3 | G7 Tier-2 wrong window | ≤5% per model | 4.76% (adjacent-sign) | **PASS** |
| 4 | G3 refusal, Tier 4 only | random Tier 4 ≥90% | 95.12% | **PASS** |
| 5 | G2 usefulness | perfect Tier 1 ≥90% | 82.93% | **FAIL** |
| 6 | G5 sign recovery | perfect ≥90%, iid ≥60% | 92.68% / 63.78% | **PASS** |
| 7 | G4 cost | perfect median ≤10 | 10 | **PASS** |

---

## G6 passes because Tier 3 was eliminated, not because it got accurate

This is the finding that matters most in this report.

| Answerer | Tier 3 v3.1 → v3.2 | Tier 4 v3.1 → v3.2 | wrong sign v3.1 → v3.2 |
|---|---|---|---|
| perfect | 0.0% → 0.0% | 4.9% → 4.9% | 0.00% → 0.00% |
| iid-noisy | **22.9% → 0.0%** | 40.4% → 60.7% | 1.10% → 0.00% |
| correlated-noisy | **27.2% → 0.0%** | 36.7% → 63.3% | 0.98% → 0.00% |
| adjacent-sign | 0.0% → 0.0% | 94.2% → 94.2% | 0.00% → 0.00% |
| random | **24.4% → 0.0%** | 71.0% → 95.1% | 21.59% → 0.00% |
| dont-know-heavy | **16.0% → 0.1%** | 42.8% → 58.1% | 0.00% → 0.00% |
| impostor | 0.0% → 0.0% | 2.4% → 2.4% | 0.00% → 0.00% |

**Tier 3 is now issued in 0.0% of runs for six of seven models and 0.1% for
the seventh.** G6's 0.00% across the board is arithmetic on an empty set, not
evidence that a delivered sign is reliable.

The cause is structural and worth fixing deliberately rather than leaving as a
happy accident. The two bars now sit in the wrong order:

| Tier | agreeing pairs | chance-agreement | checked |
|---|---|---|---|
| Tier 2 (windows) | ≥ 1 | < 0.20 | first |
| Tier 3 (a sign) | ≥ 2 | < 0.05 | second |

**Tier 3's coherence bar is strictly tighter than Tier 2's, and Tier 2 is
tested first.** Any session coherent enough to earn a sign has already earned
a shortlist of windows, so it never reaches the Tier 3 branch. The only
survivors are sessions that clear Tier 3's coherence bar but fail Tier 2's
*window* conditions — count, width or mass — which is the 0.1% seen for
dont-know-heavy.

That is backwards on its face: a rising sign is a **weaker** claim than a
30-minute window and ought to carry a **looser** bar, not a stricter one. What
the spec asked for — "Tier 3 must meet the same coherence standard as Tier 1"
— has been implemented as "a standard stricter than Tier 2", and the tier
collapsed.

**Why the retune was not spent on it.** The one remaining retune is scoped to
the Tier 3 coherence threshold. Loosening `tier3_chance_p` would make Tier 3
reachable again — and would put back exactly the wrong-sign risk that G6 and
G3 were introduced to catch, trading two high-priority passing gates for a
tier that nothing currently requires. Under the ranked priority that is a bad
trade, so it was not made. The retune stays available, and the right fix is a
design decision rather than a threshold nudge: either order the tiers by
strength of claim (loosest bar for the weakest claim) or drop Tier 3 and let
the shortlist carry it. **That is an owner's call and it is recorded here
rather than made quietly.**

### The honest price, as the spec asked

Uncertain answerers moved wholesale from Tier 3 to Tier 4. At 40 seeds × 41
cases = 1,640 runs per model:

- **iid-noisy: 376 runs** that used to end with a rising sign now end with
  "cannot determine".
- **correlated-noisy: 446 runs.**
- **dont-know-heavy: 261 runs.**
- **random: 400 runs** — this is the intended target and the reason for the
  change.

For iid-noisy and dont-know-heavy those signs were *mostly right* — their
v3.1 wrong-sign rates were 1.10% and 0.00%. So the change also refuses a
number of people it could have served correctly. That is the price of not
serving random answering, and with the tiers in their current order it is
being paid in full rather than in part.

---

## G3 redefined: Tier 3 is not a refusal

| | v3.1 (Tier 3 or 4 counted) | v3.2 (Tier 4 only) |
|---|---|---|
| random refusal rate | 95.4% | **95.1%** |

The number barely moved, but it now means what it says. In v3.1, 24.4 of those
95.4 points were Tier 3 landings — a delivered rising sign, wrong 88.5% of the
time. In v3.2 the entire 95.1% is Tier 4: the engine saying it cannot work
from these answers.

---

## Seed sets: G5 is no longer on a knife edge

v3.1 measured G5's iid-noisy leg at 59.02% on one seed set and 61.95% on
another, straddling the 60% bar. Doubling the seeds settles it.

| Seeds per model per case | G5 perfect | G5 iid-noisy | G5 verdict |
|---|---|---|---|
| 20 | 92.68% | 62.44% | PASS |
| **40** | **92.68%** | **63.78%** | **PASS** |

Both seed sets agree, and the 40-seed figure sits 3.8 points above the bar
rather than 1 point below it. Every other verdict is identical across the two
seed sets; the worst G1 model rate was 1.46% at 20 seeds and 2.62% at 40,
both comfortably inside 5%.

---

## G2, unchanged and still failing

Perfect Tier 1 rate is **82.93%**, against a 90% bar — the same value measured
in v2 and v3.1. Its other three conditions pass well: Tier 1 windows never
exceed 30 minutes, contain the truth **100%** of the time, and carry a median
error of **4 minutes**.

The cause has not changed: in roughly one run in six the region the answers
genuinely agree on is wider than the 30-minute Tier 1 cap, and a Tier 2
shortlist is the correct answer. Reaching 90% means widening the cap, which
buys the fifth-ranked gate with the promise the first-ranked one makes.

---

## The honest floors

**Impostor: 90.24%**, unchanged. Someone answering consistently for a
different birth time confirms the portrait for the sign they are answering
*as*, so nothing conflicts, no pair breaks, and they are handed a confident
wrong window nine times in ten. No tier rule touches this.

**Correlated-noisy: 6.34%**, up from 5.12% in v3.1 and over the 5% line it is
not held to. This is the model closest to a real client, and it is now the
worst non-impostor number in the report. The Tier 3 tightening pushed some of
its sessions into Tier 4, but the ones that still reach Tier 1 are no better
than before.

---

## Copy: 315 template sentences became 62 Russian atoms

`docs/copy_drafts.md` previously carried 315 template-generated English rows —
one per planet × house × facet — which is 315 sentences to correct when there
are only about twenty ideas underneath them. They are replaced by the atoms
themselves, in Russian:

| Block | Rows | Composes |
|---|---|---|
| Stage 1 and portraits (kept) | 38 | element, modality, sign_portrait keys directly |
| Life spheres (houses) | 12 | all 240 mover-house keys |
| Planet themes | 10 | the same 240 keys |
| Decan traits (sign × third) | 36 | all 72 decan keys |
| Sentence templates | 4 | how the atoms compose into a question |

Correcting one life-sphere line changes every mover-house question built on
that house. Every new row is marked `draft_ru`; Russian is the master, and
translation to EN / DE / UK happens in a later task from approved rows only.
The complete 353-key list stays machine-readable in
`astro_engine/data/copy_manifest.json`, and
`test_copy_manifest_covers_every_channel_the_engine_asks` still fails if the
engine can ask a channel the manifest does not cover.

---

## Constraints held

- `git diff main -- astro_engine/rectification.py core.py charts.py` is
  **empty**. Scoring untouched.
- ≤4 options and no clock time in any question — the v3 tests still run.
- Reweight, never zero; `cannot_choose` multiplies nothing.
- Thresholds frozen before measurement; the retune log is empty.
- No LLM in the path; deterministic and seeded.
- **Step latency 0.196 s** at the 1-minute grid, against a 1-second budget.

## The one thing to decide

Tier 3 currently cannot be reached. Either:

1. **Re-order the bars by strength of claim** — a sign is weaker than a
   window, so its coherence bar should be looser than Tier 2's, and it should
   be tested as a fallback *after* Tier 2 fails its window conditions rather
   than competing with it; or
2. **Drop Tier 3** and let Tier 2's shortlist plus Tier 4's refusal carry the
   whole range.

Doing nothing also works — the engine is safe and the gates pass — but it
ships a tier the code can emit and reality never produces, which is the kind
of thing that rots.
