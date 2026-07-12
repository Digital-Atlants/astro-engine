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
