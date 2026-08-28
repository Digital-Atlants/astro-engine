# benchmarks/

A measurement instrument for birth-time rectification. It answers one
question: **does either engine do better than the same engine fed random
dates?** It is not part of the service.

- Nothing here is imported by `astro_engine`. The `Dockerfile` copies only
  `astro_engine/`, so `benchmarks/` is already absent from the built image and
  adds no runtime dependency.
- `pytest.ini` keeps `testpaths = tests`, so the shipped suite is unchanged and
  these self-tests do not run by default. Run them with
  `pytest benchmarks/tests -q`.
- CI runs the benchmark only via `workflow_dispatch`, never on push: the
  vendor's free tier is 50 requests a month.

## Layout

| Path | What it is |
|---|---|
| `corpus/train/*.json` | Ground-truth cases used for every parameter choice. |
| `corpus/holdout/*.json` | Held out. The pre-registered gate is read off these only. |
| `variance_filter.py` | Within-block variance filter: decides what is worth building. |
| `ablation.py` | Per-addition ablation against the frozen candidate engine. |
| `weight_sweep.py` | Tunes each addition on train, scores it once on holdout. |
| `harness/blocks.py` | Rising-sign blocks: the stage-2 search space. |
| `harness/evaluators.py` | Evaluator prototypes, for the variance table. |
| `harness/candidate_engine.py` | **Frozen experiment**: the five reverted additions. |
| `RESULTS_SUBSIGN.md` | The sub-sign report and the gate verdict. |
| `harness/protocol.py` | The one protocol all three arms share. |
| `harness/arm_a.py` | Our engine, current `main`, engine defaults. |
| `harness/arm_e.py` | Constant-guess baselines (noon, corpus median). |
| `harness/vendor.py` | Arm B client, response cache, credential handling. |
| `harness/metrics.py` | Hit rates, percentiles, calibration, signal vs null. |
| `harness/bias.py` | Ascendant-speed profile and the returned-hour check. |
| `harness/pricing.py` | Vendor tier prices; inputs to the cost section. |
| `harness/report.py` | Renders `RESULTS.md` from the run records. |
| `fixtures/vendor/` | Recorded vendor requests and responses. |
| `RESULTS.md` | The report. |
| `results.json` | Raw per-run records behind the report. |

## Running

```bash
# Arms A, C and E. Free, no network, no credentials.
python benchmarks/run_benchmark.py --arms a,c,e

# All arms. Spends vendor credits.
RECT_VENDOR_API_KEY=... python benchmarks/run_benchmark.py --arms a,b,c,e

# All arms, replayed from committed fixtures. Spends nothing.
python benchmarks/run_benchmark.py --arms a,b,c,e --offline
```

The arms:

| Arm | What it is | Costs credits |
|---|---|---|
| A | Our engine, current `main`, engine defaults. | no |
| B | The vendor API, same protocol. | yes, 2 requests/case |
| C | Null control: the same engine on shuffled event dates. | only for the vendor half |
| E | Constant guess - the same clock time for every case. | no |

**Arm E is the floor.** It reads nothing about the subject. A scorer that
cannot beat a fixed clock time is not rectifying anything, so the report leads
with that comparison. Two constants are run: a fixed noon, chosen before the
corpus was scored, and the corpus median birth time, which is fitted to the
answers it is graded against and so is an oracle upper bound rather than a
shippable strategy.

## Rules this harness holds itself to

**No tuning.** Arm A constructs `RectificationConfig()` with no arguments,
because the web client sends no `config` and engine defaults are what ships.
No weight, orb, threshold or default was changed to move a number in
`RESULTS.md`. A harness tuned against its own corpus measures nothing.

**The null arm is mandatory.** Every accuracy figure is reported next to the
same figure from shuffled event dates. A peak that beats nothing is not a peak.

**One protocol.** Window, step and event set are identical across arms and live
as constants in `harness/protocol.py`. The vendor's window caps at 720 minutes,
so each case is two requests anchored at a fixed 06:00 and 18:00. Those anchors
are constants, never derived from the known birth time - passing a
`delta_minutes` anchored near the answer would leak it.
`test_vendor_request_never_leaks_the_known_time` asserts this.

**No customer or production data ever reaches the vendor.** Arm B is fed corpus
fixtures and nothing else. The harness has no path to the case store or to any
production database. Sending case-store data to a third-party API would be a
personal-data transfer with no agreement behind it, and some event categories
are special-category data.

**The key lives in `RECT_VENDOR_API_KEY` and nowhere else.** It is read from the
environment, travels in the `Authorization` header, and is never written to a
fixture, a log line, or `RESULTS.md`. A missing key raises `VendorKeyMissing`
naming the variable. `test_cached_fixtures_carry_no_credential` re-checks every
committed fixture.

## The corpus

Forty-one cases, all Rodden AA, split 29 train / 12 holdout at the file level.
**Every parameter, orb and weight is chosen on `train`; the gate is measured on
`holdout` only.** `corpus.load_corpus(split=...)` enforces the distinction;
passing no split loads both and is correct only for bookkeeping.

The original twelve cases, all Rodden AA (birth certificate or registered birth record).
A, B, C and DD were rejected on their actual rating - Ronald Reagan, Alfred
Hitchcock, Angela Merkel, King Charles III, Justin Bieber, Lee Kuan Yew,
Sukarno and others were checked and left out.

Two limits are stated up front rather than discovered later:

1. **The near-equator rule is not met.** The spread rules ask for at least two
   cases within 10 degrees of the equator; the corpus has none. AA-rated
   equatorial births are scarce in Astro-Databank. `RESULTS.md` lists the
   candidates checked and why each was rejected. `test_corpus_spread_rules`
   asserts the shortfall so that adding such a case forces the report to be
   updated.
2. **Five of twelve known times fall on a round quarter-hour.** Registered
   times are commonly rounded by the registrar, so those references carry
   roughly +/-5 to 15 minutes of their own error. That caps what any accuracy
   claim below +/-5 minutes can mean, and it is restated wherever a +/-2 or
   +/-5 number appears.

## Vendor notes worth keeping

- Categories are a fixed enum: `marriage`, `divorce`, `child_birth`,
  `death_family`, `career_change`, `career_promotion`, `job_loss`, `move`,
  `accident`, `surgery`, `health_diagnosis`, `education`, `relationship_start`,
  `relationship_end`, `financial_gain`, `financial_loss`, `spiritual`, `other`.
- Their `date_precision` enum is `exact` / `month` / `year`; ours calls the
  finest level `day`. `vendor.PRECISION_MAP` bridges it.
- They honour explicit `latitude` / `longitude` / `timezone`. Their Ascendant
  matches ours to 0.0013 degrees for the same instant, so both engines see the
  same astronomy and every measured difference is a scoring difference.
- A rectification search costs a flat 15 credits regardless of candidate count,
  and is gated to their Ultra tier and above.
- Their default `urllib` user agent is rejected by Cloudflare with error 1010;
  the client sends its own.
- One of their field names contains a substring that
  `tests/test_no_hd_terms.py` greps for as a forbidden non-astrological term.
  The guard is correct and is not weakened; the field is renamed on ingest to
  `vendor.SCORE_FIELD`, and the response fixture records the response *shape*
  rather than a verbatim payload. `test_fixtures_use_the_normalised_score_key`
  keeps that true.
