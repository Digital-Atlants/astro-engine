# astro-engine

Public, AGPL-3.0, astrology-only computation service (FastAPI + pyswisseph,
Moshier ephemeris). See README.md for the endpoint contract.

## COMMON MISTAKES TO AVOID

- Do NOT add any non-astrological chart systems (including the "H.D."
  system) or any brand references — this repo is public and astro-only by
  design. No such terminology anywhere: code, comments, tests, README,
  commit messages. `tests/test_no_hd_terms.py` enforces this structurally.
- Do NOT compute a full chart per rectification candidate — per-event
  transit/progressed positions and the solar arc are candidate-independent
  and precomputed once; only angles/houses (`swe.houses`) and the progressed
  Moon vary per candidate. See `astro_engine/rectification.py`.
- Keep responses deterministic: fixed float rounding (`core.ROUND_DEG`),
  stable ordering; `compute_ms` is the only non-deterministic field.
- No secrets in the repo: `.env` is gitignored; `.env.example` holds
  placeholders only.
- Do NOT derive a single reported time with `max(range(N_GRID), key=...)` - it
  returns the FIRST minute of a flat maximum and biases the time toward the
  early edge of the plateau - use `plateau_midpoint` / `working_time`.
  `peak_time` is kept only for backward compatibility.
- Do NOT put a clock time, an answer id, a tag id, the birth date or the place
  into the `/v1/interview/compare` response - the record exists so a labelled
  corpus can accumulate WITHOUT storing anything about the person -
  `tests/test_interview_v3_5.py` enforces it structurally.
- `/compare` must accept everything `/step` accepts that moves the posterior
  (answers, known_bounds, claimed_time, sphere_inventory, trait_tags) - a
  session that cannot be replayed is scored against a different posterior.
