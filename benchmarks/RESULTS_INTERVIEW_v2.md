# Interview v2: in-session reliability, conservative trust, professional inputs

**G1 (safety) PASS. G2 (usefulness) FAIL. G3 (refusal) PASS. G4 (cost) PASS.**

The headline: **the Tier-1 wrong-window rate for the iid-noisy answerer falls
from 6.22% in v1 to 0.37% in v2** — a seventeen-fold reduction, and comfortably
inside the 5% bar that v1 failed. Both changes earned it, in roughly equal
measure, and they compound.

**The one v2 retune was not spent.** G1 passes, and G2's failure is not
something the v2 parameters can address honestly — see below.

---

## Gate results

41 cases, 20 seeded runs per answerer per case, 820 runs per answerer.

| Answerer | Tier 1 | Tier 2 | Tier 3/4 | **wrong-window** | T1 median &#124;err&#124; | T1 median window | questions | pairs |
|---|---|---|---|---|---|---|---|---|
| perfect | 82.9% | 17.1% | 0.0% | **0.00%** | 3 min | 14.5 min | 8 | +3.0/−0.0 |
| iid-noisy | 12.9% | 41.5% | 45.6% | **0.37%** | 3 min | 14.5 min | 8 | +1.94/−1.08 |
| adjacent-sign | 0.0% | 0.0% | 100.0% | **0.00%** | — | — | 8 | +3.0/−0.0 |
| random | 0.1% | 0.2% | 99.6% | **0.12%** | 714 min | 9 min | 8 | +0.17/−2.45 |
| dont-know-heavy | 8.9% | 48.7% | 42.4% | **0.00%** | 4 min | 15 min | 8 | +0.77/−0.0 |
| *correlated-noisy (not gated)* | *30.0%* | *15.2%* | *54.8%* | *1.59%* | *3 min* | *13 min* | *8* | *+2.80/−0.20* |
| *impostor (not gated)* | *87.8%* | *12.2%* | *0.0%* | *87.80%* | *358.5 min* | *13 min* | *8* | *+3.0/−0.0* |

| Gate | Required | Measured | Verdict |
|---|---|---|---|
| G1 safety | wrong-window ≤ 5% per model and pooled | worst 0.37%, pooled 0.10% | **PASS** |
| G2 usefulness | perfect Tier 1 ≥ 90% | **82.9%** | **FAIL** |
| G2 (other three) | window ≤30, containment ≥95%, median err ≤8 | 30 min, 100%, 3 min | pass |
| G3 refusal | random in Tier 3/4 ≥ 95% | 99.63% | **PASS** |
| G4 cost | perfect median questions ≤ 8 | 8 | **PASS** |

---

## Isolation: which change earned what

The same harness, four configurations, `iid_noisy` wrong-window rate as the
safety measure.

| Configuration | r | paraphrase | **iid-noisy wrong-window** | perfect Tier 1 | random Tier 3/4 | G1 | median questions |
|---|---|---|---|---|---|---|---|
| v1 baseline | 0.75 | no | **6.34%** | 82.9% | 99.4% | FAIL | 4 |
| conservative trust only | 0.60 | no | **2.07%** | 82.9% | 99.4% | PASS | 5 |
| paraphrase only | 0.75 | yes | **2.07%** | 82.9% | 99.2% | PASS | 7 |
| **v2 (both)** | 0.60 | yes | **0.37%** | 82.9% | 99.6% | PASS | 8 |

Three things this table settles.

**Either change alone would have passed G1.** Each cuts the wrong-window rate
by about a factor of three, from 6.34% to 2.07% — and they arrive at the same
number by different routes, which is a coincidence worth noting rather than a
sign they are the same mechanism.

**Together they compound rather than overlap**, to 0.37%. They act on
different failure modes: conservative trust stops any single answer from
concentrating the posterior too hard, while paraphrase detects *which
particular answerer* is unreliable and lowers their trust specifically.

**The v1 baseline reproduces.** 6.34% here against 6.22% reported in v1 — the
same configuration measured independently, differing only by seeding.

**The cost is four questions.** Paraphrase takes the perfect answerer from 4
questions to 8; conservative trust adds one on its own. G4 allows 8 and the
median is exactly 8, so this is at the boundary, not comfortably inside it.

---

## Why G2 still fails, and why the retune was not spent

The perfect answerer's Tier 1 rate is **82.9% in every single configuration
measured** — v1 baseline, conservative-only, paraphrase-only, both, and at
every value of r. It did not move by a tenth of a percent under any change made
in this task.

That is because it is not a trust problem. In 17.1% of runs the region the
answers genuinely agree on is **wider than the 30-minute Tier 1 cap**, so the
engine correctly reports a Tier 2 shortlist instead. Its other three G2
conditions pass and pass well: when it does issue Tier 1 the window contains
the truth **100%** of the time with a median error of **3 minutes**.

The v2 retune could reach 90% by widening `tier1_window_minutes`. That would be
choosing a number to pass a gate at the direct cost of the promise Tier 1
makes, in a task whose entire premise is that the confident-wrong rate is what
matters. The retune is left **unspent**, and G2 is reported as failed.

---

## The honest floors

**Impostor: 87.80%.** Someone answering consistently for a different birth time
is handed a confident wrong window in seven runs out of eight, with a median
error of about six hours. Paraphrase cannot touch this by construction: the
impostor agrees with themselves perfectly (+3.0/−0.0 pairs), because they are
being perfectly consistent — just about someone else.

**Correlated-noisy: 1.59%.** This is the model that matters for real people:
wrong one time in five, and when wrong, giving the *same* wrong answer to both
phrasings 70% of the time. It is the stress test paraphrase is designed to
fail, and the number is much better than feared — 1.59%, below the G1 bar it is
not held to. The reason is that paraphrase is not the only defence: a partial
self-misperception still produces answers that disagree *across channels*, and
the chance-agreement test catches what the pair test misses. Its Tier 1 rate
(30.0%) sits between the perfect answerer's and iid-noisy's, which is the right
ordering.

Neither number should be read as a solved problem. **A person who confidently
believes something false about themselves is the failure mode this design
cannot detect**, and the impostor rate is the ceiling on how bad that gets.

---

## Sensitivity over channel reliability r

`r` was **not tuned**; it is fixed at 0.60 on the argument in
`docs/trust_default.md`. This row is reported only.

| r | G1 | worst wrong-window | perfect Tier 1 | random Tier 3/4 | impostor |
|---|---|---|---|---|---|
| 0.50 | PASS | 0.24% | 82.9% | 99.9% | 90.2% |
| **0.60 (shipped)** | PASS | 0.73% | 82.9% | 100.0% | 87.8% |
| 0.75 | PASS | 1.46% | 82.9% | 99.4% | 75.6% |

With paraphrase in place, **every value of r now passes G1** — in v1, 0.75
failed at 6.2%. The safety margin still improves monotonically as r falls, and
the perfect answerer's Tier 1 rate is again completely flat, confirming that
caution costs nothing on the useful side.

The impostor rate moves the other way: lower trust means wider windows, and a
wider wrong window is still wrong. That is not an argument for higher trust —
it is a reminder that no setting of r addresses an answerer who is internally
consistent about the wrong person.

---

## Professional mode

Single-pass questioning with a filled sphere inventory. The inventory supplies
one observation of each mover question and the client supplies the other, so
the two form a **source pair** and the same agreement logic applies.

| Answerer | Tier 1 | Tier 2 | Tier 3/4 | **wrong-window** | T1 median &#124;err&#124; | questions | inventory covered movers |
|---|---|---|---|---|---|---|---|
| perfect | 41.5% | 58.5% | 0.0% | **0.00%** | 5 min | 4 | 76% |
| iid-noisy | 13.1% | 40.8% | 46.1% | **1.83%** | 6 min | 5 | — |
| adjacent-sign | 0.0% | 0.0% | 100.0% | **0.00%** | — | 5 | — |
| random | 0.0% | 1.1% | 98.9% | **0.00%** | — | 6 | — |
| dont-know-heavy | 6.0% | 37.6% | 56.5% | **1.59%** | 5 min | 5 | — |
| *correlated-noisy* | *13.8%* | *41.9%* | *44.3%* | *2.32%* | *5 min* | *5* | — |
| *impostor* | *9.8%* | *65.8%* | *24.4%* | ***9.76%*** | *357.5 min* | *4* | — |

G1 passes in professional mode too (worst 1.83%, pooled 0.68%).

**The result worth selling is the impostor row: 87.8% → 9.8%.** An independent
professional observation catches what paraphrase cannot. The impostor agrees
with *themselves* perfectly but disagrees with the astrologer's inventory,
those pairs break, session reliability drops, and the engine refuses or falls
back to a shortlist. This is the first mechanism in the whole project that
detects a consistently wrong answerer, and it works because the second
observation comes from a different *person*, not a different phrasing.

**Half the cost:** 4 questions against 8, because the inventory answers the
mover questions and only the sign and decan need asking.

**The trade is Tier 1 rate: 41.5% against 82.9%.** With one client observation
per question instead of two phrasings, fewer agreeing pairs accumulate, so more
sessions land in Tier 2. For a professional tool that is arguably the right
shape — a shortlist with portraits handed to someone qualified to choose
between them — but it should be stated plainly rather than presented as a win.

### Sensitivity over the `observed` source weight

Not tuned; reported.

| `observed` trust | G1 | worst wrong-window | perfect Tier 1 | impostor |
|---|---|---|---|---|
| 0.70 | PASS | 1.71% | 73.2% | 14.6% |
| **0.80 (shipped)** | PASS | 1.83% | 41.5% | 9.8% |
| 0.90 | PASS | 3.41% | 34.2% | 12.2% |

Non-monotone, and worth understanding before anyone reaches for the knob. At
0.70 the astrologer's inventory is weak enough that it rarely contradicts the
client, so more pairs agree and Tier 1 fires more often — at nearly double the
impostor rate. At 0.90 it is strong enough to overrule genuinely correct client
answers, so *more* pairs break and Tier 1 falls further. 0.80 is near the
minimum of the impostor curve. This is a real trade between how often the tool
speaks and how often it is wrong, and it should be set from calibration data,
not preference.

---

## Three bugs found by measurement

All three were in the professional path and all three would have shipped a
misleading number. None of them was a threshold choice, so none consumed the
retune.

1. **The inventory excluded the truth.** Reading it preferred `dominant`
   houses over `present` ones, but a planet often sits alone in a merely
   `present` house — so the correct answer was filtered out. A *perfect*
   answerer showed a 12.20% wrong-window rate. The inventory now rules out only
   what it positively marks `absent`.
2. **Single-pass mode waived the pair requirement entirely**, so professional
   sessions could reach Tier 1 with no cross-check at all. The requirement now
   applies whenever the session produced pairs, however they were formed, and
   is waived only when no second observation of any kind exists.
3. **Agreement was tested as equality.** That is correct for two paraphrases,
   which are both single-select — but an inventory answers with the *set* of
   houses it has not ruled out and the client picks one from it. Equality
   marked every source pair a disagreement, including for a perfect answerer,
   collapsing all seven models to Tier 3 with +0.0/−2.9 pairs. Agreement is now
   non-empty intersection, and the effective answer is that intersection.

---

## Performance

**0.073 s per interview step** at the 1-minute grid, against a 1-second budget.
The first call in a process is slower (~2 s) because the ephemeris initialises
on first use; that is startup cost, not per-step cost.

## Constraints held

- `git diff main -- astro_engine/rectification.py core.py charts.py` is
  **empty**. Scoring is untouched.
- Reweight, never zero: document bounds multiply by 0.02;
  `test_document_bounds_downweight_but_never_delete` asserts the ratio exactly.
- No LLM anywhere in the path; every run is seeded and reproducible.
- `extra: forbid` still in force; `hypothesis` never enters the posterior,
  asserted by comparing the full posterior summary and windows with and
  without it.
