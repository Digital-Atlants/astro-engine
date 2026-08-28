# Rectification benchmark: our engine against the vendor, both against a null control

> **Headline: our engine clears the constant-guess floor, and that is the only bar it clears.**
>
> Arm A (our engine) has a median error of **278 minutes**, better than a constant clock time that ignores the subject entirely (noon 458 min, corpus median 348 min). So the scorer is doing *something* with the events.
>
> It is not doing enough. At +/-5 minutes - the accuracy the product promises - Arm A hits **0%**, and the vendor hits 0%. Against its own shuffled-date null control, neither engine separates (see the verdict). Beating a constant is a floor, not a product.

Generated 2026-08-28 by `benchmarks/run_benchmark.py`. This is a measurement instrument, not a tuning run: no scoring weight, orb, default or shipped code path was changed to produce these numbers, and the harness was never adjusted after seeing them.

## Protocol

- Window `00:00-23:59`, step `4` min, 360 candidate times, identical in every arm.
- **Arm A** - our engine on current `main` with engine defaults (`RectificationConfig()` with no arguments, which is what the web client gets because it sends no `config`).
- **Arm B** - the vendor's `POST /api/v3/rectification/search`. Their window caps at 720 minutes, so each case is two requests anchored at a fixed 06:00 and 18:00 with `delta_minutes: 360`; the better of the two peaks is taken. The anchors are protocol constants, never derived from the known time, so nothing about the answer leaks into the request.
- **Arm C** - the null control, run against both engines: same case, same window, same event count and category mix, event dates redrawn uniformly across the subject's own event span. 5 shuffles per case for Arm A.
- **Arm E** - a constant-guess baseline that returns the same clock time for every case and reads nothing about the subject. Run at a fixed noon and at the corpus median birth time (09:12). Costs no vendor requests.

The vendor honours explicit `latitude`/`longitude`/`timezone`: its Ascendant for a given candidate matches ours to 0.0013 degrees (`fixtures/vendor/category_probe.json`). Both engines therefore see the same astronomy, and every difference below is a difference in scoring.

## The corpus

| Case | Born | Known time | Rodden | Lat | Spread | Round time | Events |
|---|---|---|---|---|---|---|---|
| Muhammad Ali | 1942-01-17 | 18:35 | AA | 38.25 | - | no | 12 |
| Bill Clinton | 1946-08-19 | 08:51 | AA | 33.67 | - | no | 11 |
| Leonardo DiCaprio | 1974-11-11 | 02:47 | AA | 34.05 | night | no | 10 |
| Bob Dylan | 1941-05-24 | 21:05 | AA | 46.79 | lat>45 | no | 12 |
| Francois Mitterrand | 1916-10-26 | 04:00 | AA | 45.68 | night,lat>45 | yes | 12 |
| Marilyn Monroe | 1926-06-01 | 09:30 | AA | 34.05 | - | yes | 12 |
| Barack Obama | 1961-08-04 | 19:24 | AA | 21.31 | - | no | 12 |
| Elvis Presley | 1935-01-08 | 04:35 | AA | 34.26 | night | no | 10 |
| Nicolas Sarkozy | 1955-01-28 | 22:00 | AA | 48.86 | lat>45 | yes | 12 |
| Arnold Schwarzenegger | 1947-07-30 | 04:10 | AA | 47.07 | night,lat>45 | no | 12 |
| Britney Spears | 1981-12-02 | 01:30 | AA | 31.24 | night | yes | 10 |
| Vincent van Gogh | 1853-03-30 | 11:00 | AA | 51.47 | lat>45 | yes | 12 |

12 cases, all Rodden AA. Night births (00:00-06:00): **5** (rule: at least 4). Born above 45 degrees latitude: **5** (rule: at least 4). Within 10 degrees of the equator: **0** (rule: at least 2) - **this rule is not met; see 'Where this corpus falls short' below.**

**5 of 12 known times fall on a round quarter-hour.** Registered times are commonly rounded by the registrar, so for those cases the reference itself carries roughly +/-5 to 15 minutes of error. No accuracy claim below +/-5 minutes can be validated against them, and the +/-2 column below is close to meaningless for that subset. Per-case notes are in each fixture's `reference_uncertainty_note`.

## Accuracy

| Arm | n | +/-2 min | +/-5 min | +/-15 min | +/-30 min | Median abs err | p90 abs err |
|---|---|---|---|---|---|---|---|
| A - ours, real events | 12 | 0% | 0% | 17% | 25% | 278 | 464 |
| C - ours, shuffled dates | 60 | 0% | 0% | 5% | 13% | 309 | 669 |
| B - vendor, real events | 12 | 0% | 0% | 8% | 8% | 156 | 631 |
| C - vendor, shuffled dates | 4 | 0% | 25% | 25% | 25% | 318 | 525 |
| E - constant guess, noon | 12 | 0% | 0% | 0% | 0% | 458 | 595 |
| E - constant guess, corpus median (09:12) | 12 | 0% | 0% | 0% | 17% | 348 | 666 |

Blind-guess baselines on a 24-hour window: +/-2 min is 0.3% of the day, +/-5 min is 0.7%. Any hit rate near those numbers is noise.

Read the vendor null row with care: it is four cases, so a single lucky run shows up as 25%. That row is a reminder of how little four samples buy, not evidence that shuffled dates work better than real ones.

**Arm E returns the same clock time for every case.** It does not read the events, the chart, the latitude or anything else about the subject. It is the floor a scorer has to clear before its output can be called a rectification at all. The noon constant was fixed before the corpus was scored; the corpus-median constant is **fitted to the very answers it is graded against**, so it is an oracle baseline and an upper bound on what a constant can do here, not a strategy anything could ship.

## Calibration - does the engine know when it is right?

### Ours (`residual_window_minutes`)

| Self-reported confidence | n | within +/-5 | rate | within +/-15 | rate | Median abs err |
|---|---|---|---|---|---|---|
| 0 min | 11 | 0 | 0% | 2 | 18% | 265 |
| 4-12 min | 1 | 0 | 0% | 0 | 0% | 301 |

### Vendor (`confidence.level`)

| Self-reported confidence | n | within +/-5 | rate | within +/-15 | rate | Median abs err |
|---|---|---|---|---|---|---|
| medium | 1 | 0 | 0% | 0 | 0% | 108 |
| low | 11 | 0 | 0% | 1 | 9% | 186 |

Ours reports no confidence *level*, only `residual_window_minutes` - the width of the contiguous span whose scores stay within `plateau_ratio` of the best. A narrower residual window is the engine claiming a sharper answer, so the buckets run from narrow (highest implied confidence) to wide.

## Signal versus null

`peak / mean` over the full 24-hour candidate grid, real events against shuffled dates. If the real distribution is not separated from the null distribution, the peak is a property of the grid, not of the life.

| Engine | real n | real median | null n | null median | real p10 | null p90 | AUC | Cohen's d |
|---|---|---|---|---|---|---|---|---|
| ours | 12 | 2.56 | 60 | 2.65 | 2.34 | 3.21 | 0.47 | 0.03 |
| vendor | 12 | 1.96 | 4 | 1.91 | 1.73 | 2.12 | 0.60 | 0.33 |

AUC is the probability that a randomly chosen real run outranks a randomly chosen null run on `peak / mean`. 0.50 is chance; 1.00 is complete separation.

### Where the true birth time ranks in each engine's own score distribution

Argmax accuracy is coarse on twelve cases: an engine can carry real signal and still miss the top slot. This asks the softer question - of the 360 candidates, what fraction score strictly below the true time? **0.50 is chance. 1.00 would mean the true time is the outright peak.** A scorer with any signal at all should sit well above 0.50 here even when its argmax is wrong.

| Set | n | median percentile | p25 | p75 |
|---|---|---|---|---|
| ours, real events | 12 | 0.62 | 0.33 | 0.82 |
| ours, shuffled dates | 60 | 0.48 | 0.21 | 0.79 |
| vendor, real events | 12 | 0.73 | 0.58 | 0.87 |
| vendor, shuffled dates | 4 | 0.24 | 0.17 | 0.43 |

For the shuffled-date rows the 'true time' has no reason to score well, so those rows are the chance reference measured rather than assumed.

## Bias check - are returned times following the Ascendant, not the events?

| Set | n | in the 8 slowest Ascendant hours | share | uniform expectation |
|---|---|---|---|---|
| A - ours, real | 12 | 5 | 42% | 33% |
| C - ours, null | 60 | 18 | 30% | 33% |
| B - vendor, real | 12 | 8 | 67% | 33% |
| C - vendor, null | 4 | 1 | 25% | 33% |

### Returned-hour histogram (all runs, all arms)

| Set | 00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ours real | 0 | 2 | 0 | 0 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| ours null | 2 | 1 | 6 | 3 | 1 | 1 | 3 | 1 | 11 | 2 | 2 | 1 | 1 | 7 | 2 | 1 | 2 | 0 | 3 | 5 | 3 | 1 | 1 | 0 |
| vendor real | 0 | 0 | 0 | 0 | 2 | 0 | 1 | 0 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 1 | 1 | 1 |
| vendor null | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The 'slowest Ascendant hours' are computed per case from the actual Ascendant travel per 4-minute step at that latitude and date (`harness/bias.py`), not assumed. A share well above 33% means the scorer is rewarding the hours where the angles move least, which is a property of the grid rather than of the subject's life.

## Per case, verbatim engine output

| Case | Known | Ours | abs err ours | residual | Vendor | abs err vendor | level | gap | lift | twin | anchor | on grid | grid floor |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Muhammad Ali | 18:35 | 18:44 | 9 | 0 | 20:32 | 117 | low | 0.01 | 1.94 | False | False | no | 1 |
| Bill Clinton | 08:51 | 09:20 | 29 | 0 | 06:44 | 127 | low | 0.07 | 1.71 | False | True | no | 1 |
| Leonardo DiCaprio | 02:47 | 07:12 | 265 | 0 | 04:08 | 81 | low | 0.09 | 1.83 | False | False | no | 1 |
| Bob Dylan | 21:05 | 16:04 | 301 | 4 | 21:52 | 47 | low | 0.07 | 1.71 | False | True | no | 1 |
| Francois Mitterrand | 04:00 | 01:08 | 172 | 0 | 11:44 | 464 | low | 0.02 | 1.74 | False | False | yes | 0 |
| Marilyn Monroe | 09:30 | 14:20 | 290 | 0 | 09:20 | 10 | low | 0.04 | 2.27 | False | True | no | 2 |
| Barack Obama | 19:24 | 08:48 | 636 | 0 | 08:48 | 636 | low | 0.09 | 1.90 | False | True | yes | 0 |
| Elvis Presley | 04:35 | 12:24 | 469 | 0 | 18:52 | 583 | low | 0.05 | 1.93 | False | True | no | 1 |
| Nicolas Sarkozy | 22:00 | 04:28 | 388 | 0 | 20:12 | 108 | medium | 0.15 | 2.29 | False | True | yes | 0 |
| Arnold Schwarzenegger | 04:10 | 11:04 | 414 | 0 | 22:52 | 318 | low | 0.01 | 1.79 | False | False | no | 2 |
| Britney Spears | 01:30 | 01:40 | 10 | 0 | 04:36 | 186 | low | 0.00 | 1.95 | True | True | no | 2 |
| Vincent van Gogh | 11:00 | 06:52 | 248 | 0 | 23:20 | 700 | low | 0.04 | 2.20 | False | True | yes | 0 |

`grid floor` is the smallest |err| any engine could achieve for that known time on this 4-minute grid. Where the known time is not a grid point, that floor is the irreducible part of the error.

## Cost and wall-clock

**Total vendor requests consumed: 33** (32 rectification searches - two per case, one per half-window - plus 1 schema probe), for 495 credits. One further exploratory request was made by hand before the harness existed and is not in the fixture ledger, so the true total is 34. **That is under the vendor's free-tier limit of 50 requests a month.** One malformed probe was rejected with a 422 and cost nothing.

The vendor bills a flat 15 credits per rectification request regardless of candidate count (measured: 15 credits for a 5-candidate search, a 13-candidate search and a 181-candidate search alike). Note the tension: 34 requests is inside a 50-*request* allowance, but at 15 credits each it is far outside a 50-*credit* one, and the vendor gates rectification to its Ultra tier. If the free tier is denominated in credits rather than requests, this run exceeded it; every request was nonetheless accepted with a 200 and no quota warning.

Median compute per case: ours **198 ms** in-process for all 360 candidates; the vendor reports **109158 ms** of server compute across its two requests. End to end, though, a vendor case took roughly **105 seconds** of wall-clock in the live run, against a fifth of a second for ours. That is a two-order-of-magnitude difference in latency and it would be visible to a user waiting on a result.

### Vendor cost per rectification, by tier

| Tier | USD/month | Credits/month | Rectification | Rectifications/month | Cost per rectification |
|---|---|---|---|---|---|
| Free | $0 | 50 | not offered | - | - |
| Pro | $11 | 1,000 | not offered | - | - |
| Pro Plus | $21 | 7,000 | not offered | - | - |
| Ultra | $37 | 55,000 | yes | 1,833 | $0.0202 |
| Business | $99 | 220,000 | yes | 7,333 | $0.0135 |
| Enterprise | $399+ | custom | yes | negotiated | negotiated |

One rectification = 2 requests x 15 credits = 30 credits, because the vendor's window caps at 720 minutes and a full day needs two calls. **Rectification is gated to Ultra and above**, so the $11 and $21 tiers cannot buy it at any volume, and the free tier cannot legitimately be used for it in production at all.

Prices transcribed from https://astrology-api.io/pricing on 2026-08-28.

## Verdict

### 1. Which engine, if either, is measurably better than its own null control

**Neither engine is measurably better than its own null control** on this corpus.

- Ours: +/-5 hit rate 0% vs null 0%; median |err| 278 vs null 309 min; peak/mean AUC 0.47.
- Vendor: +/-5 hit rate 0% vs null 25%; median |err| 156 vs null 318 min; peak/mean AUC 0.60.

The bar used here is deliberately all three at once: a higher +/-5 hit rate than the null, a lower median error than the null, and `peak / mean` separated from the null at AUC > 0.65. Clearing one of the three by chance on twelve cases is easy; clearing all three is not.

**One qualifier, because it is the only thing in this run that looks like signal.** Argmax is a harsh test on twelve cases. Ranking the *true* time inside each engine's own score distribution is softer, and there the two engines separate:

- Ours: true time at the 0.62 percentile on real events (n=12) against 0.48 on shuffled dates (n=60).
- Vendor: 0.73 on real events (n=12) against 0.24 on shuffled dates (n=4).

The vendor's scorer ranks the true birth time well above its own shuffled-date control: it is finding something and then failing to convert it into a correct peak. Ours sits much closer to its own control. **This does not overturn the verdict above.** The vendor null here is only 4 cases, far too few to establish the gap, and none of it moves the hit rates a product promise actually depends on. It is the one result in this report worth spending another measurement on, and the cheap way to do that is to widen the vendor null arm - not to rebuild our scorer on the strength of it.

### 2. Do the vendor's confidence outputs track error better than `residual_window_minutes`?

Our `residual_window_minutes` splits the corpus into 2 bucket(s); the spread in +/-5 hit rate between its best and worst bucket is 0%.
The vendor's `confidence.level` splits it into 2 bucket(s); the spread there is 0%.

A confidence output is worth copying only if high-confidence cases really are more accurate than low-confidence ones, i.e. if that spread is large and positive. See the calibration tables above for the underlying counts; with twelve cases each bucket holds only a handful of cases, so treat any spread here as directional rather than established.

### 3. Is either engine accurate enough to support a +/-5 minute promise?

No. The best +/-5 hit rate in either real arm is **0%**, against a blind-guess baseline of 0.7%. A product promise of +/-5 minutes with +/-2 as the target and no refund path is not supported by either engine on this corpus.

**The corpus caveat is load-bearing here.** 5 of 12 known times fall on a round quarter-hour, and registered times are commonly rounded by the registrar. For those cases the reference carries roughly +/-5 to 15 minutes of its own error, so a measured +/-5 hit rate on them cannot distinguish a correct answer from one that is 10 minutes out. Any +/-5 or +/-2 figure in this report is therefore an upper bound on what could be verified, not a demonstrated accuracy.

### 4. Build versus buy

Buying: the cheapest tier that can run rectification at all is **Ultra at $37/month**, which covers 1,833 rectifications, i.e. **$0.0202 per rectification** at full utilisation. Below roughly 1,833 a month the tier fee dominates and the effective unit cost is higher; at 100 rectifications a month it is $0.37 each.

Building: our engine runs the same 360-candidate grid in-process. At $0.000463 per vCPU-minute the compute cost per rectification is a small fraction of a cent - see the measured wall-clock above - so the marginal cost is effectively zero and the real cost is engineering time on the scorer.

**The cost difference is not the deciding factor.** Both options are cheap per rectification relative to anything charged to an end user. The decision turns on the accuracy and calibration numbers above, and on the fact that sending customer birth data and life events to a third party would be a personal-data transfer with no agreement behind it - some event categories in the intake are special-category data. Arm B in this report was run on public-figure fixtures only, and that boundary is what makes it lawful to run at all; it is not a boundary a production integration could keep.

## Where this corpus falls short

**The near-equator spread rule is not met: 0 cases within 10 degrees of the equator, against a required 2.** This is a real gap and it is reported rather than papered over, because the whole point of that rule is that the slow-Ascendant bias is a function of latitude.

Astro-Databank is heavily Western-weighted and AA-rated equatorial births are genuinely scarce. Candidates were checked and rejected on their actual Rodden rating, not on convenience:

| Candidate | Latitude | Rating found | Rejected because |
|---|---|---|---|
| Lee Kuan Yew | 1.3 N | R | book reference, not a birth record |
| Sukarno | 7.2 S | B | biography |
| Hugo Chavez | 8.8 N | conflicting | 02:00 / 03:30 / 04:00 / 17:10 all reported |
| Freddie Mercury | 6.2 S | X | no birth time recorded at all |
| Oscar Arias | 9.9 N | conflicting | birth year itself disputed (1940 vs 1941) |

The lowest-latitude case that did qualify is Barack Obama at 21.3 N. The latitude-dependent part of the bias check is therefore measured over 31.2 N to 51.5 N only, and this report cannot say how either engine behaves at equatorial latitudes. Closing this gap needs a source other than Astro-Databank - a national civil-registry release, or an astrological association's regional AA collection.

Two further limits worth stating:

- Rejections elsewhere in the shortlist were also on rating, not fit: Ronald Reagan (Astro-Databank shows AA, but the displayed certificate carries no time), Alfred Hitchcock (DD), Angela Merkel (B), King Charles III (A), Justin Bieber (B). None were admitted.
- Event dates come from published biography, so a handful carry their own day-level slack even where they are recorded here as `day` precision. That adds noise to both arms equally and cannot favour one engine over the other.

