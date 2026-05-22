# Offline PcsBenchIngest.v0 fixture

Committed ingest for pcs-bench producer gate tests without running certifyedge.

- Regenerate: `python scripts/generate_pcs_bench_ingest_fixture.py`
- CI: `python examples/pcs_qc_release/scripts/ci_validate_pcs_bench_ingest_fixture.py`
- Pytest: `tests/pcs/test_pcs_bench_ingest_fixture.py`

`evidence_grade` is `developer` (fixture pins use `0000…0001`). Release-grade semantics are enforced by `make pcs-bench-producer` / `full_regeneration` runs.

Full producer tree with on-disk sidecars: `tests/fixtures/pcs_bench_reproducibility/` (regenerate via `make pcs-fixtures`).
