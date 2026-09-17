# Why the default channel reliability is 0.60

`InterviewConfig.channel_reliability` defaults to **0.60**. This document
records why, because the number looks arbitrary and is not.

## What the parameter means

It is the assumed probability that a person picks the correct option when
answering an interview question about their own chart. It sets how hard a
non-matching candidate is downweighted: at reliability `r` with `k`
alternatives, a non-matching class is multiplied by `(1 - r) / (r * (k - 1))`.
A high `r` says "believe the answer"; a low `r` says "hedge".

## The measurement it comes from

The v1 gate run swept `r` over {0.60, 0.75, 0.90} and reported this
(`benchmarks/RESULTS_INTERVIEW.md`, sensitivity section):

| r | worst-model Tier-1 wrong-window rate | G1 | perfect answerer's Tier 1 rate | G3 refusal |
|---|---|---|---|---|
| 0.60 | **2.2%** | pass | **82.9%** | 99.5% |
| 0.75 | 6.2% | fail | 82.9% | 98.4% |
| 0.90 | 14.9% | fail | 78.0% | 94.6% |

Two things in that table decide the question.

**The safety cost of over-trusting is steep.** Going from 0.60 to 0.90 nearly
sevenfold increases the rate at which the engine hands someone a confident
window that does not contain their birth time, and at 0.90 even the refusal
path starts to fail.

**The usefulness cost of under-trusting is zero.** The perfect answerer's
Tier 1 rate is **identical at 0.60 and 0.75** (82.9%), and only falls at 0.90.
Caution buys safety here without spending anything on the useful side. That is
an unusually clean trade and it is the whole argument.

## Why this is minimax, not a fit to the gate

The true reliability of live answerers is **unknown**. Nobody has measured how
often a real person picks the right rising-sign description about themselves;
that is exactly what `/v1/interview/compare` exists to find out, and until it
has run there is no empirical value to use.

Faced with an unknown parameter and an asymmetric loss - a confident wrong
birth time is far more damaging to the product than a wider window or an
honest refusal - the design assumes the worst plausible value rather than a
hopeful one. That is a minimax choice about which error to prefer, made before
seeing which value passes a gate.

It is worth being precise about the distinction, because the two look alike
from outside. `r = 0.60` does make G1 pass in the v1 sweep. But the v2 spec
fixed the value on the argument above, and the same sweep is re-reported in
`RESULTS_INTERVIEW_v2.md` so the reader can check that the choice is not being
justified after the fact by the number it produces. The honest summary: the
sensitivity row identified 0.60 as both the safe choice and a free one, and
the design took it for the first reason.

## What would change it

A calibration corpus. Once `/v1/interview/compare` has collected enough live
sessions with documented birth times, `r` becomes a measured quantity - per
channel, and possibly per question - rather than an assumption. At that point
this default should be replaced by the measurement, and this document should
be replaced by a pointer to it.

Until then: **do not raise `r` to make a number look better.** The v1 retune
already demonstrated that tier thresholds are not the lever that controls
safety; `r` is, and it is the one parameter in the system that should be set
by evidence about people rather than by tuning against a corpus.

---

# Why the decan channel is trusted less than the sign channels (v3.3)

`InterviewConfig.decan_reliability` defaults to **0.50**, against a session
default of 0.60. It caps the trust applied to any decan answer, so a decan
answer moves the posterior less than an element, modality or portrait answer
does.

This is a **design constant, not a fitted one**, and the argument is geometric
rather than empirical.

## The argument

A decan is a ten-degree third of a rising sign. How long it takes to rise
depends on latitude and on which sign it is: at 51 degrees a decan rises in
roughly **18 to 57 minutes**. So a decan answer, taken at face value, is a
claim about the birth time to within about half an hour.

The answer itself is a self-report of appearance and bearing — "which of these
two descriptions is closer to how people describe you". Nothing about that
question carries half-hour precision. Two people born forty minutes apart do
not reliably sort themselves into different thirds of a sign, and the copy
that distinguishes the thirds (`docs/copy_drafts.md`, section 4) differs by a
single leading trait inside each sign by construction.

Trusting the answer at the session default would let a low-information answer
make a high-precision claim. The cap is the smaller of the two: a
document-sourced answer is not *promoted* by it, only a high-trust one pulled
down.

## Sensitivity, reported and not tuned

`benchmarks/RESULTS_INTERVIEW_v3_3.md` carries the sweep over {0.40, 0.50,
0.60}. It is reported so the reader can see what the constant costs, not so a
value can be picked from it. If a decan value is ever chosen by measurement it
should come from `/v1/interview/compare` on live sessions — how often a person
actually places themselves in the correct third — and not from which setting
makes a gate pass.

## What would change it

The same thing that would change `channel_reliability`: a calibration corpus
with documented birth times, measuring per-channel accuracy directly. Until
then the decan channel is the one whose self-report is least plausible at the
precision its geometry implies, and it is weighted accordingly.
