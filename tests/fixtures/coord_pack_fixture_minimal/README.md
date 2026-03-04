Minimal synthetic fixture for CI coverage gate only: not a real coordination security pack run.

This directory contains **only** `pack_summary.csv` (no SECURITY/, no pack_results/, no summary/). The risk register bundle builder treats such a run dir as fixture-only and marks the coordination_pack evidence with `synthetic: true`, so downstream consumers can distinguish it from real pack output.

Headers must match `PACK_SUMMARY_COLUMNS` in `src/labtrust_gym/studies/coordination_security_pack.py`. Tests enforce this to prevent drift. The full pack fixture is `tests/fixtures/coord_pack_fixture` (used where a complete pack output is needed).
