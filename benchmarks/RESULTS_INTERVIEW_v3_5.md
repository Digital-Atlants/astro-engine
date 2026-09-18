# Interview v3.5: measurement outputs only

**v3.5 does not change accuracy; it changes what can be measured.**

No number that reaches `tier`, `windows`, `coherence`, `next_question`,
`sign_blocks`, `per_channel`, `telemetry` or `peak_time` moved. The holdout
gate table is re-run below and reproduces to the digit.

---

## What changed

Three things were making a live blind calibration session close to worthless:

1. **Tier 4 produced no measurement at all.** `abs_error_minutes` is null when
   no window was named, and Tier 4 is where most real sessions land — 94.8% of
   random, 64.8% of dont-know-heavy. The sessions the engine is least sure
   about were the ones it learned nothing from.
2. **Nothing said *which* answers agreed with the documented time.** A channel
   that is systematically misleading was undiscoverable without reading
   people's answers, which the PII rule forbids.
3. **`/compare` rejected `trait_tags`,** so a consumer session could not be
   replayed at all. It would have been scored against a different posterior
   than the person actually saw.

Plus one latent bias: `posterior_summary.peak_time` uses
`max(range(N_GRID), key=...)`, which returns the **first** minute of a flat
maximum. On a near-flat posterior that pins the reported time to the early
edge — largest exactly when the engine knows least. `peak_time` is kept
unchanged for backward compatibility; `best_time` and `working_time` are the
unbiased additions.

### New outputs

`/v1/interview/step` → `posterior_summary` gains `best_time`, `working_time`,
`working_time_source`. `/v1/interview/compare` gains
`abs_error_minutes_working`, `working_time_source`, `truth_rank_pct`,
`truth_sign_correct`, `truth_sign_mass`, `documented_minute_is_round`,
`per_answer`, and accepts `trait_tags`.

`truth_rank_pct` is the mid-rank percentile of the documented minute in the
posterior — 0 means it was the single best candidate, ~50 is chance. It
separates "wrong" from "nearly right" far better than a midpoint error does,
and it is defined in every tier.

`documented_minute_is_round` exists because registrars round. Without it a
corpus reads that rounding as engine error.

---

## Proof that decisions are untouched

| Check | Test | Result |
|---|---|---|
| `/step` byte-identical to `dc35fc4` with the three new keys removed | `test_step_decisions_are_byte_identical_to_dc35fc4` | pass |
| `peak_time` still the first minute of the maximum | `test_peak_time_still_reports_the_first_minute_of_the_maximum` | pass |
| the bias the new key fixes is real | `test_plateau_midpoint_and_peak_time_disagree_on_a_flat_posterior` | pass |
| `posterior_summary` has exactly six keys | `test_posterior_summary_has_exactly_the_expected_keys` | pass |
| `/compare` has exactly twelve keys | `test_compare_response_has_exactly_the_agreed_key_set` | pass |
| no clock time, answer id, tag id, birth date or place in `/compare` | `test_compare_response_carries_nothing_about_the_person` | pass |
| the public `run_interview` result is not widened | `test_run_interview_public_result_is_not_widened` | pass |
| `/step` still has nowhere to put a documented time | `test_interview_step_has_no_field_for_a_documented_time` (unchanged) | pass |

The fixture `tests/fixtures/step_dc35fc4.json` was recorded from the clean
`dc35fc4` tree **before** any edit in this task, and is committed. `compute_ms`
is stripped from it — the one non-deterministic field in the contract.

```
git diff dc35fc4 -- astro_engine/data/ astro_engine/rectification.py \
                    astro_engine/charts.py astro_engine/core.py \
                    astro_engine/build_info.py
```
→ empty. `GET /health` → `interview_contract.answer_fields` identical to
`dc35fc4`.

---

## Gate re-run (Pre-answered 10)

```
python benchmarks/interview_holdout_v3_4.py --config chosen --width 50
```

Run on the v3.5 branch, 12 holdout cases × 40 seeds × 9 models, 23m27s.

| Rank | Gate | Required | v3.4 documented | **v3.5 re-run** |
|---|---|---|---|---|
| 1 | G1 safety | ≤5% per model | 5.42% **FAIL** | **5.42% FAIL** |
| 2 | G7 Tier-2 window | ≤5% per model | 4.37% **PASS** | **4.37% PASS** |
| 3 | G3 refusal | random T4 ≥90% | PASS | **PASS** |
| 4 | G9 shortlist width | perfect median ≤90 min | 36.0 min PASS | **36.0 min PASS** |
| 5 | G2 usefulness | perfect T1 ≥90% | FAIL | **FAIL** |
| 6 | G5 sign recovery | perfect ≥90%, iid ≥60% | PASS | **PASS** |
| 7 | G4 cost | perfect median ≤10 | PASS | **PASS** |

Per model, holdout:

| Answerer | G1 | G7 |
|---|---|---|
| perfect | 0.00% | 0.00% |
| iid-noisy | 2.08% | 2.29% |
| **adjacent-sign** | **5.42%** | 0.00% |
| **random** | 0.00% | **4.37%** |
| dont-know-heavy | 0.00% | 0.00% |
| sign-only | 0.00% | 0.00% |
| sun-attributor | 0.42% | 0.83% |

Worst model and worst figure match `RESULTS_INTERVIEW_v3_4.md` exactly on both
gates.

---

## What this makes possible, and what it does not

It makes a live blind session worth running: every session now yields an error,
a rank, a sign verdict and a per-channel agreement record, in every tier, with
nothing stored about the person.

It does **not** improve anything. The ceilings in
`RESULTS_INTERVIEW_v3_4.md` are unchanged and unaddressed — impostor 87.8%,
adjacent-sign's 88-minute displacement with no near misses, G2 stuck at 82.9%
since v2. Those need evidence about whether self-description identifies a
rising sign at all, which is what the accumulated `/compare` records are for.
This task built the instrument, not the result.
