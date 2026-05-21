# LabTrust reproducibility ingest (golden)

Reference output for pcs-bench run ingestion: pcs-core `PcsBenchIngest.v0` with embedded
`BenchmarkRun.v0` and `CoverageReport.v0`, plus companion `benchmark_report.v0.json`.

## Regenerate golden fixtures

From the repository root (requires `../pcs-core` schemas):

```bash
python examples/pcs_qc_release/scripts/materialize_benchmark_ingest_golden.py \
  --pcs-core ../pcs-core \
  --runs 2
```

Writes `golden/` with:

- `pcs_bench_ingest.v0.json`
- `benchmark_manifest.v0.json`
- `benchmark_report.v0.json`
- `benchmark_run.v0.json`
- `coverage_report.v0.json`

## Publish to pcs-bench

```bash
python examples/pcs_qc_release/scripts/publish_reproducibility_ingest.py \
  --out examples/pcs_qc_release/benchmark_ingest/golden \
  --pcs-core ../pcs-core \
  --pcs-bench-runs ../pcs-bench/runs/labtrust_reproducibility
```

## Validate

```bash
labtrust verify-benchmark-cases \
  --benchmark-dir examples/pcs_qc_release/benchmark_ingest/golden \
  --validate-pcs-core-output ../pcs-core
```
