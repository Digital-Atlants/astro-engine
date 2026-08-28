# The predisposition channel: does the natal-house channel carry a signal?

**Gate verdict: FAIL, on both conditions, under both codings of the answers.**

Matched biography-chart pairs do not narrow significantly better than
mismatched pairs (paired permutation p = 0.53 and p = 0.84 against a required
p < 0.05), and the true time survives the filtering in 66% and 37% of matched
cases against a required 80%. **The predisposition channel is dead.**

A second, separate finding sits underneath that one and matters more: **the
biographical answers this study depends on could not be produced reliably.**
Automated extraction from Wikipedia was 53% precise on `yes` answers when
hand-audited. That is reported in full below, because a reader should be able
to judge whether the gate failed because the channel is vacuous or because the
input was too noisy to test it. On this corpus both are true at once.

This study does **not** test whether a live person can answer these questions
about themselves. That is a separate study on volunteers with birth
certificates. Nothing here should be read as bearing on it.

---

## Work item 1 - which two questions, per chart

Inside the true rising-sign block, Placidus houses, all 41 cases. Pure chart
geometry: no events, no scoring.

| | all 41 | holdout 12 |
|---|---|---|
| block width (median) | 144 min | 148 min |
| planets that change house inside the block (median) | 10 | 10 |
| planets that change house (range) | 6 - 10 | 9 - 10 |
| window after **1** best question (median) | 40 min | 30 min |
| window after **2** best questions (median) | **16 min** | **20 min** |
| window after **3** best questions (median) | 16 min | 20 min |
| window from the full ten-planet vector (median) | 16 min | 20 min |
| cases where 2 questions already equal the full vector | **41 / 41** | 12 / 12 |
| cases where a 3rd question adds nothing over 2 | **41 / 41** | 12 / 12 |

**This reproduces the 12-case claim on all 41 cases.** Two house questions
reach the full ten-planet oracle in every case, and a third never adds
anything. The narrowing is 144 minutes to 16.

**The selection genuinely differs per chart - confirmed, not assumed.** Across
41 charts the best pair is **25 distinct pairs**. No single pair serves the
corpus. The most frequently selected planets are Venus (14 charts), Moon (12),
Sun (12), Jupiter (11), Mercury (9), Pluto (7); every planet is selected for
some chart and none for most. Any product built on this would have to compute
the two questions per chart, not ask a fixed pair.

**Work item 1.4, the wiring check: the shuffled-date arm is identical to the
real arm, exactly as it must be.** Stage (a) and the house vector never read
the events, and the run confirms it byte for byte across all 41 cases
(`shuffled_arm_identical: true` in `question_selection.json`). Nothing reads
events that should not.

---

## Work item 2 - the mapping, borrowed not invented

Committed frozen at `benchmarks/fixtures/predisposition_mapping.json`.

### The origin publishes no house mappings

The astro-app.net rectification page was fetched and read in full. **It
contains no astrological house numbers anywhere.** It describes the method and
names a handful of example items only. Verbatim, the whole of what it says
about this stage:

> it considers various options of the birth time taking into account
> predisposition to events. This refers to events or situations that do not
> occur to everybody, but which, as a rule, are well marked in the natal
> chart. For example, celibacy, childlessness, many children, imprisonment
> etc.

The full item list is generated inside the app after birth data is submitted
and is not published as a static list. The 24 items scored here are the
visible items supplied in the task brief, recorded verbatim in the fixture.

Under the Work item 2 rule as written - drop any item whose mapping the source
does not state - **every one of the 24 items would be dropped and this study
would end here.** The rule also permits a cited classical reference, so that
route was taken.

### Houses sourced from Lilly

House significations are taken verbatim from William Lilly, *Christian
Astrology* (1647), "Of the Twelve Houses, their Nature and Signification",
quoted in the fixture. An item is kept only where the matter it names is one
of the nouns Lilly enumerates. Items needing a qualifier Lilly does not state
are dropped rather than inferred.

**13 of 24 items survive. 11 are dropped.**

| Kept | House | Lilly's basis |
|---|---|---|
| many marriages | 7 | "It giveth judgement of marriage" |
| childlessness or a late child | 5 | "we judge of children" |
| adopted children | 5 | "we judge of children" |
| separation from a child | 5 | "we judge of children" |
| death of a child | 5, 8 | "we judge of children"; "death, its quality and nature" |
| emigration | 9 | "voyages or long journeys beyond seas" |
| success in science | 9 | 9th house matters include "Arts, Science" |
| success in religious work | 9 | "of religious men, or clergy of any kind" |
| unemployment | 10 | "the profession or trade" |
| high material wealth | 2 | "his wealth or poverty" |
| poverty | 2 | "his wealth or poverty" |
| homelessness | 4 | "of lands, houses, tenements" |
| prolonged hospital isolation | 12 | "imprisonments, all manner of affliction" |

Dropped: secret affairs, celibacy from excessive independence, marriage to a
foreigner, success in music or acting, success in invention or reform,
repeated extreme situations, attempted suicide, a fall from height, extreme
situations involving water, revenge or persecution, poisoning. Each carries a
recorded reason in the fixture.

### The bridge that could not be sourced

A sourced item-to-house mapping still does not say **which planet's** house to
read, and Work item 1 shows the narrowing information lives entirely in
per-planet house membership. The origin says nothing about this, and Lilly's
method of judging by the lord of a house is far richer than a house-membership
predicate and cannot be reduced to one without invention.

The rule adopted, frozen before any scoring run: **a `yes` for house H is
scored by the number of planets tenanting H at that candidate time; a `no` by
the negation of the same quantity; `unknown` contributes nothing.** It is one
chart-independent rule, it commits to no per-item or per-chart choice that
could be fitted afterwards, and it uses exactly the quantity Work item 1
identified as carrying the information.

**This is the weakest link in the chain and it is not sourced.** It is stated
here rather than buried.

**Any later change to the mapping invalidates every number in this report and
requires a rerun from scratch.** Ten planets across twelve houses with two
dozen predispositions is a space in which almost anything can be fitted after
the fact, which is the entire reason it is frozen and the entire reason the
mismatched-pair null exists.

---

## Work item 3 - blind extraction, and why it did not work

41 biographies were pulled from the public Wikipedia article for each case
(median 69,000 characters) and **every clock time was redacted before the text
was used**, with the removals logged per case in
`fixtures/biographies/index.json`. The corpus fixture, the Rodden rating and
every prior benchmark output were never read by the extraction.

Answers were derived by explicit committed rules over that text - not from
recall - so every answer carries the sentence that produced it and the whole
pass is reproducible. Two codings were produced:

- **strict**: `yes` or `no` only where a sentence states it; everything else
  `unknown`.
- **documented absence**: additionally, for rare-event items, a 40,000+
  character biography that never mentions the event is read as `no`.

### The extraction is 53% precise, hand-audited

All 36 machine-produced `yes` answers were read against their own quotations.
**19 were upheld and 17 rejected** - a precision of 53%. Every verdict with its
reason is committed at `fixtures/predisposition_audit.json`. Rejected answers
were demoted to `unknown`, never flipped to `no`.

Representative failures, all of which look plausible until read:

| Case | Item | What the sentence actually said |
|---|---|---|
| Bob Dylan | prolonged hospital isolation | he signed with **Asylum Records** |
| Sigmund Freud | prolonged hospital isolation | he **worked in** an asylum as a physician |
| Marilyn Monroe | high material wealth | the film title *How to Marry a Millionaire* |
| Whitney Houston | prolonged hospital isolation | the imprisoned person is **Nelson Mandela** |
| Bill Clinton | emigration | US trade **policy** on free emigration |
| Prince William | homelessness | **his work with** the homeless |
| Charles Manson | unemployment | the unemployed man is a **different person** |
| Angelina Jolie | prolonged hospital isolation | a **film role** as a psychiatric patient |

Three rounds of tightening - a subject gate requiring the surname or a leading
pronoun, third-party relative detection, possessive-name detection, exclusion
of film and policy contexts - reduced `yes` answers from 81 to 36 without
lifting precision above 53%. The remaining errors are semantic, not lexical:
distinguishing "was confined in an asylum" from "signed with Asylum Records"
requires reading, not matching.

**After the audit, 19 verified `yes` answers survive across 41 cases and 13
items - 3.6% of the 533 answer slots, about 0.5 verified facts per case.**

| Coding | yes | no | unknown |
|---|---|---|---|
| strict, after audit | 19 (4%) | 24 (5%) | 490 (92%) |
| documented absence, after audit | 19 (4%) | 172 (32%) | 342 (64%) |

### Contamination

The Work item 3.4 check as specified - can the extractor state the birth time
from the excerpt? - is not the binding contamination risk here, and reporting
only it would be misleading. **The extractor for this task is the same agent
that built the corpus earlier in this session and therefore already knew every
birth time.** The blind condition is not met in the strict sense and no check
on the excerpt can restore it.

What limits the damage is structural rather than procedural: the answers are
mechanical regex output over redacted text, and the audit rejected answers on
whether the sentence was about the subject, never on what any chart implied.
Recall cannot change whether Schwarzenegger was naturalised. But the honest
statement is that this pass was **not blind**, and a genuinely blind
replication would need an extractor with no prior exposure to the corpus.

On the specified check itself: the redaction removed 21 clock-time strings
across the 41 biographies, and no birth time appears in any excerpt. No case
could have its birth time stated from its excerpt.

---

## Work item 4 - matched against mismatched

Reweighting, never filtering: nothing is removed from the candidate set, so a
wrong answer degrades the result instead of deleting the truth. Run inside the
true rising-sign block only, so this measures the channel and not stage 1.
The null is subject A's answers against subject B's chart, 5 mismatches per
case (205 mismatched pairs against 41 matched).

### Strict coding

| | median window | true time survives | median midpoint err | <=5 | <=15 |
|---|---|---|---|---|---|
| matched | 104 min | 66% | 38 min | 5% | 27% |
| mismatched | **88 min** | 62% | 35 min | 6% | 23% |

AUC (matched narrower than mismatched) **0.516**, mean difference **+0.4 min**,
paired permutation **p = 0.53**.

### Documented-absence coding

| | median window | true time survives | median midpoint err | <=5 | <=15 |
|---|---|---|---|---|---|
| matched | 24 min | 37% | 41 min | 12% | 20% |
| mismatched | **28 min** | 31% | 40 min | 7% | 25% |

AUC **0.492**, mean difference **+6.0 min**, paired permutation **p = 0.84**.

### Gate

| Condition | Required | Strict | Documented absence |
|---|---|---|---|
| matched narrows better than mismatched | p < 0.05 | p = 0.53 **FAIL** | p = 0.84 **FAIL** |
| true time survives in matched cases | >= 80% | 66% **FAIL** | 37% **FAIL** |

**Both conditions fail under both codings.** Under the strict coding the
matched window is *wider* than the mismatched one, and AUC sits on chance in
both. A subject's own answers narrow their own chart no better than a
stranger's answers do.

---

## Work item 5 - the one code change

When the surviving candidate set is narrower than `midpoint_below_minutes`
(default 26), the engine returns the midpoint of the contiguous survivor
interval instead of the score argmax. `suggested_best.selection` reports which
was used. Above the threshold nothing changes, and the full-day search is
unaffected because the whole window is one wide interval.

Measured over the stage-(b) survivor sets from the ceiling appendix, which is
where narrow sets actually occur (the rule engages in 28 of 40 cases):

| | median err | mean err | <=5 | <=15 |
|---|---|---|---|---|
| **all 40** | | | | |
| before (argmax) | 6.0 | 8.7 | **48%** | 82% |
| after (midpoint) | 6.0 | **6.5** | 40% | **95%** |
| **holdout 12** | | | | |
| before (argmax) | 6.5 | 9.8 | **33%** | 75% |
| after (midpoint) | 8.0 | **7.5** | 25% | **92%** |

Head to head the midpoint is better in 19 cases, worse in 10, tied in 11.

**This is a trade, not a free win, and the losing side should be stated.** The
midpoint removes the large errors - mean 8.7 to 6.5, and the ±15 hit rate from
82% to 95% - by never landing far from a survivor interval that contains the
truth. It costs near-misses at ±5, where it drops from 48% to 40%, and on
holdout the median rises from 6.5 to 8.0. The rationale for this change cited a
blind pick taking ±5 in 52.1% against the argmax's 47.5%; the interval midpoint
is not the same estimator as a uniform blind pick and does not inherit that
number. It is the better estimator on mean error and on ±15, and the worse one
at ±5.

Given that the ±5 promise is not supported by anything in this engine anyway,
trading ±5 near-misses for a much better ±15 rate and a lower mean is the right
side of the trade. It is `midpoint_below_minutes` and can be set to 0.

Tests assert both branches: a survivor set narrower than the threshold returns
the interval midpoint, and above the threshold the argmax behaviour is
unchanged.

---

## What this means

**The channel is dead as specified.** Matched pairs do not beat mismatched
pairs; the mapping, as far as it can be sourced, is vacuous over these
answers.

Two caveats belong next to that verdict rather than after it:

1. **The input was poor.** 19 verified facts across 41 cases is not enough to
   detect a real effect if one existed. A negative result on an underpowered
   input is weaker evidence than a negative result on a good one. What the run
   establishes firmly is that *this* route to the answers - automated
   extraction from public biographies - does not produce usable input, at 53%
   precision after three rounds of tightening.
2. **The bridge from house to planet is unsourced.** If the channel is ever
   retried, that is the piece to settle first, because no amount of better
   biography will rescue a bridging rule that is invented.

What survives from this task and is worth keeping is Work item 1. Two house
questions collapse a 144-minute block to 16 minutes, in every one of 41 cases,
and a third adds nothing. That narrowing is real, it is chart geometry rather
than a scoring claim, and it is confirmed identical on shuffled dates. The
open question is not whether the narrowing exists but whether any obtainable
human answer can select the two planets - and this study says biographies
cannot.
