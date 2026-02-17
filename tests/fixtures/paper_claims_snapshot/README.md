# Paper claims snapshot (v0.1)

Deterministic snapshot of paper-facing artifacts for regression. Used by `tests/test_paper_claims_regression.py`.

## Updating the snapshot

When paper pipeline outputs change intentionally (e.g. new summary columns, policy bump), regenerate and commit:

1. Run paper release with smoke and fixed seed:
   ```bash
   LABTRUST_PAPER_SMOKE=1 labtrust package-release --profile paper_v0.1 --out ./paper_out --seed-base 42
   ```
2. Extract snapshot into this fixture:
   ```bash
   python scripts/extract_paper_claims_snapshot.py ./paper_out --out tests/fixtures/paper_claims_snapshot/v0.1
   ```
3. Commit `tests/fixtures/paper_claims_snapshot/v0.1/` (snapshot_manifest.json and any summary.csv).

CI runs the regression test on schedule and workflow_dispatch; the test builds the same paper artifact (smoke, seed 42) and compares to this snapshot.
