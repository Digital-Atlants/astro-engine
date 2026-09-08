# Interview v3: stage 1 as short questions, free-text traits, times never as input

**G3 (refusal) PASS. G4 (cost) PASS. G1 (safety) FAIL. G2 (usefulness) FAIL.
G5 (sign recovery) FAIL on the perfect leg, PASS on the noisy leg.**

The owner's rule is implemented and enforced: **no question offers more than
four options, and no question payload contains a clock time.** Both are
asserted by tests that walk a whole interview.

The rule cost accuracy, and the honest headline is a regression:

> **The iid-noisy Tier-1 wrong-window rate rose from 0.37% in v2 to 3.17% in
> v3, and the adjacent-sign answerer went from 0.00% to 5.24% — which is what
> fails G1.**

The single permitted v3 retune has been spent. It bought G4 and did not rescue
G1, G2 or G5.

---

## What changed

| | v2 | v3 |
|---|---|---|
| Stage 1 | one 12-way sign choice | a sequence of ≤4-tag splits, multi-select |
| Options shown | up to 12 | **≤4** (movers ≤3, portraits ≤3) |
| Time spans in questions | twelve, rendered as the answer options | **none** — moved to `sign_blocks` in the result |
| Vocabulary | one description key per sign | 30 trait tags, each with a likelihood for every sign |
| Free text | not accepted | `trait_tags` at `source: free_text_confirmed`, trust 0.55 |

The live session that prompted this rendered stage 1 as twelve time spans
("промежуток с 07:08 до 08:46") and asked the person to choose the thing they
came to find out. That specific failure cannot recur: a test walks every
question in a full interview and fails if any payload matches a clock pattern
or carries a `spans`/`start`/`end` key.

---

## Gate results (retuned defaults, 41 cases × 20 runs × 7 models)

| Answerer | Tier 1 | Tier 2 | Tier 3/4 | **wrong-window** | **sign recovery** | T1 median &#124;err&#124; | questions |
|---|---|---|---|---|---|---|---|
| perfect | 78.0% | 14.6% | 7.3% | **0.00%** | **75.6%** | 5 min | 9 |
| iid-noisy | 13.5% | 23.3% | 63.2% | **3.17%** | **65.5%** | 6 min | 10 |
| adjacent-sign | 5.2% | 23.8% | 71.0% | **5.24%** | 0.0% | 18 min | 10 |
| random | 0.4% | 3.7% | 96.0% | **0.37%** | 10.6% | 394 min | 10 |
| dont-know-heavy | 1.0% | 25.2% | 73.8% | **0.00%** | 64.1% | 5 min | 10 |
| *correlated-noisy* | *25.5%* | *11.3%* | *63.2%* | *5.73%* | *60.9%* | *6 min* | *10* |
| *impostor* | *78.0%* | *17.1%* | *4.9%* | *78.05%* | *0.0%* | *357.5 min* | *9* |

| Gate | Required | Measured | Verdict |
|---|---|---|---|
| G1 safety | ≤5% per model and pooled | adjacent-sign **5.24%**, pooled 1.76% | **FAIL** |
| G2 usefulness | perfect Tier 1 ≥90% | **78.0%** | **FAIL** |
| G2 (other three) | window ≤30, containment ≥95%, err ≤8 | 30 min, 100%, 5 min | pass |
| G3 refusal | random Tier 3/4 ≥95% | 96.0% | **PASS** |
| G4 cost | perfect median ≤9 questions | 9 | **PASS** |
| G5 sign recovery | perfect ≥90% | **75.6%** | **FAIL** |
| G5 sign recovery | iid-noisy ≥60% | 65.5% | pass |

---

## Why G1 regressed: the redesign traded one failure mode for another

In v2 the adjacent-sign answerer had a **0.00%** wrong-window rate and landed
in Tier 3 in 100% of runs. In v3 it reaches Tier 1 in 5.2% of runs at a 5.24%
wrong-window rate, and it is the model that fails G1.

The mechanism is structural, not a bug. In v2 a neighbouring sign was a
*different enum value*: answering "Virgo" when the truth was Leo put the
answer in a disjoint class, the channels disagreed, and the engine correctly
refused. In v3 neighbouring signs share most of their trait likelihoods, so
someone answering for the adjacent sign ticks nearly the same tags, their two
phrasings agree with each other, and nothing in the machinery notices.

Smaller questions bought **better reliability against random noise** — the
random answerer still refuses 96% of the time — and **lost ground against
systematic neighbour confusion**. The correlated-noisy model moved the same
way, 1.59% → 5.73%.

No threshold fixes this. It is a property of how close neighbouring signs sit
in the vocabulary, and the vocabulary is frozen.

## Why G5 fails: the trait channel is a weaker stage 1 than a direct choice

A perfect answerer picking their own sign from a list gets it right
essentially always. A perfect answerer answering trait questions gets it right
**75.6%** of the time. That 25-point gap is the price of the owner's rule, and
it is the number to weigh against the user-experience gain.

The bits-per-question table shows where the information actually is:

| Stage | mean information per question (bits) |
|---|---|
| trait (stage 1) | **0.02** |
| decan | 4.95 |
| mover_house | 1.55 |
| portrait | 1.44 |

Stage 1 contributes almost nothing in *expected* bits. Two things make that
number look worse than the channel really is, and both should be stated:

1. **The update is positive-only by design.** Unticked tags do not penalise,
   so the large "ticked nothing" branch contributes zero and drags the
   expectation down even though a tick, when it happens, moves the posterior
   decisively.
2. **The decan figure is inflated by stage 1's weakness.** 4.95 bits means
   roughly 31 live sign-decan classes were still in play when the decan
   question was asked — i.e. stage 1 had barely narrowed the sign at all.

Both readings point the same way: the trait vocabulary as constructed does not
carry the sign the way a direct choice does.

---

## The retune log — one entry, none remaining

*Trigger:* frozen defaults failed G1 (adjacent-sign 5.37%), G2 (78.05%),
G4 (median 10 questions) and G5 (75.6%).

*Scope:* only parameters v3 introduced — `max_trait_questions`,
`sign_mass_stop`, `repeat_pairs`. Tier thresholds and the trust default were
deliberately out of scope: they belong to v1/v2, whose retunes are spent or
deliberately unspent.

*Search:* 12 configurations on the 29-case **train** split, ranked by gates
passed, then by G1 margin.

| max_trait_questions | sign_mass_stop | repeat_pairs | gates passed | G1 worst | G4 questions | G5 perfect |
|---|---|---|---|---|---|---|
| 2 | 0.55 | 2 | 1 | 0.053 | 8 | 0.724 |
| 2 | 0.55 | 3 | 2 | 0.026 | 9 | 0.724 |
| 3 | 0.45 | 2 | 2 | 0.038 | 9 | 0.759 |
| 3 | 0.45 | 3 | 1 | **0.017** | 10 | 0.759 |
| 3 | 0.55 | 2 | 2 | 0.038 | 9 | 0.759 |
| 3 | 0.55 | 3 | 1 | 0.026 | 10 | 0.759 |
| **4** | **0.45** | **2** | **3** | 0.033 | 9 | 0.759 |
| 4 | 0.45 | 3 | 1 | 0.024 | 10 | 0.759 |
| 4 | 0.55 | 2 | 3 | 0.043 | 9 | 0.759 |
| 4 | 0.55 | 3 | 1 | **0.015** | 10 | 0.759 |

*Chosen:* `max_trait_questions=4, sign_mass_stop=0.45, repeat_pairs=2`.

*Holdout re-evaluation (12 cases):* G1 FAIL (adjacent-sign 13.33%), G2 FAIL
(83.3%), G3 PASS (97.9%), G4 PASS (9), G5 FAIL (75.0%).

**The most useful thing in that table is a conflict the score function had to
resolve: G1 and G4 pull against each other.** Every `repeat_pairs=3`
configuration has a markedly better worst-model wrong-window rate — as low as
**1.5%**, which would pass G1 — and every one of them costs a tenth question,
which fails G4. The third repeat pair is precisely what catches the
adjacent-sign answerer, and the cost gate forbids it.

The pre-declared score function ranked by *gates passed* first, so it chose
the configuration that passes three gates (G1 still failed) over one that
would likely pass G1 but fail G4. That was the rule agreed before the search
ran and it was followed. **If the owner would rather have safety than the
ninth question, `repeat_pairs=3` is the setting** — but changing it now would
be a second retune, and the spec allows one.

---

## Trait vocabulary

30 tags across three channels — temperament, social, appearance — committed
frozen at `astro_engine/data/trait_vocabulary.json`, generated from a
declarative rule rather than hand-typed per sign:

```
likelihood(tag, sign) = element_profile[element(sign)]
                      * modality_profile[modality(sign)]
```

clipped to [0.08, 0.94]. Not fitted to any corpus — there is no corpus in that
step. Any change to a tag or a likelihood invalidates every number here.

Every tag has a `label_key` for rendering and a distinct `paraphrase_key` for
the v2 repeat phrasing, so a repeat asks the same partition in different words.

**Separation report** (`benchmarks/fixtures/trait_vocabulary_separation.json`),
counting tags where the likelihood difference is ≥0.20:

| Sign | vs previous | vs next | worst against any sign |
|---|---|---|---|
| aries | 21 | 25 | 5 |
| taurus | 25 | 28 | 6 |
| gemini | 28 | 22 | 7 |
| cancer | 22 | 20 | 6 |
| leo | 20 | 24 | 5 |
| virgo | 24 | 21 | 8 |
| libra | 21 | 25 | 7 |
| scorpio | 25 | 24 | 6 |
| sagittarius | 24 | 26 | 8 |
| capricorn | 26 | 17 | 6 |
| aquarius | 17 | 14 | 7 |
| pisces | 14 | 21 | 10 |

**No sign is without separating tags against any other sign** — the worst case
is five. The weakest neighbour pair is Aquarius/Pisces at 14 tags. So the
vocabulary is not degenerate; the 75.6% sign recovery is not caused by signs
being indistinguishable in principle, but by how much a *positive-only* update
at 0.60 trust can move a posterior in four rounds.

---

## Free-text traits

Confirmed tags arrive as one more observation of the same vocabulary, at
trust 0.55 — below a direct chip choice, because agreeing with a reading of
what you said is a weaker act than picking the thing yourself. Unknown tag ids
are rejected by the schema. **The engine never receives free text**: the
mapping from words to tags is the client's and exists only because the person
confirmed it.

| Answerer | Tier 1 | wrong-window | sign recovery | questions |
|---|---|---|---|---|
| perfect | 61.0% | 0.00% | 63.4% | **7** |
| iid-noisy | 16.3% | 1.46% | 63.2% | 8 |
| adjacent-sign | 3.9% | 3.90% | 0.0% | 8 |
| random | 0.1% | 0.12% | 45.1% | 9 |

Free text **saves two questions** (7 against 9) and **costs 12 points of sign
recovery** (63.4% against 75.6%). Two tags at 0.55 trust concentrate the
posterior enough to stop stage 1 early, without concentrating it as accurately
as four rounds of direct choices would. That is a real trade and it should be
the client's decision which to offer, not a silent default.

---

## Sensitivity over r

`r` was not tuned; it is fixed at 0.60 on the argument in
`docs/trust_default.md`.

| r | G1 worst | perfect Tier 1 | sign recovery | random Tier 3/4 | impostor |
|---|---|---|---|---|---|
| 0.50 | **2.20%** | 75.6% | 73.2% | 95.5% | 82.9% |
| **0.60 (shipped)** | 5.24% | 78.0% | 75.6% | 95.4% | 82.9% |
| 0.75 | 8.90% | 80.5% | 75.6% | 91.6% | 85.4% |

In v2 every value of r passed G1. In v3 only **r = 0.50** does. The trait
channel is more sensitive to trust than the partition channels were, because a
positive-only likelihood update compounds across ticks rather than being
bounded by a single class choice. Lowering r to 0.50 would pass G1 at a cost
of 2.4 points of Tier 1 rate and 2.4 points of sign recovery — but r is not a
knob to be turned to pass a gate, and setting it from a gate result is exactly
what `docs/trust_default.md` argues against. It is reported, not taken.

---

## Honest floors

**Impostor: 78.05%.** Unchanged in character from v2's 87.8% — someone
answering consistently for a different birth time is still handed a confident
wrong window most of the time, now with a median error of about six hours. The
slight improvement is not a detection mechanism, only a wider posterior.

**Correlated-noisy: 5.73%**, up from 1.59% in v2. A person who holds a
partially wrong belief about themselves ticks the same wrong tags in both
phrasings, and neighbouring signs share tags, so the pair test sees agreement.
This is the same mechanism that fails G1 and it is the failure mode closest to
a real client.

---

## Constraints held

- `git diff main -- astro_engine/rectification.py core.py charts.py` is
  **empty**. Scoring untouched.
- Reweight, never zero: `test_trait_answer_never_zeroes_a_candidate` applies
  eight tags in series and asserts every candidate stays positive.
- Multi-select non-penalty: asserted directly — ticking one of four moves the
  posterior exactly as ticking that one alone.
- `extra: forbid` still in force; unknown trait tags rejected with 422.
- No LLM in the path; deterministic and seeded.
- **Step latency 0.074 s** at the 1-minute grid, against a 1-second budget.

## What I would do next, if asked

1. **Decide the G1/G4 conflict deliberately.** `repeat_pairs=3` measured a
   1.5% worst-model wrong-window rate on train against the 5.24% shipped. One
   extra question buys the safety gate. That is an owner's call about which
   gate matters, not a tuning question.
2. **Fix neighbour separation in the vocabulary, not the thresholds.** The
   adjacent-sign failure is a vocabulary property. Tags that separate *adjacent*
   signs specifically — rather than tags that separate elements and modalities,
   which adjacent signs never share — would target it directly.
3. **Measure `r` from live calibration sessions.** The v3 sensitivity row
   shows the trait channel is more trust-sensitive than v2's channels were,
   which raises the value of the measurement rather than the guess.
