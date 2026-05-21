# PCS benchmark producer (LabTrust-Gym)

LabTrust is the reference producer for the hospital lab QC release PCS benchmark. All
machine-readable outputs align with pcs-core v0 schemas and normalize into
`PcsBenchIngest.v0` for pcs-bench.

## Producer surfaces

| Command | Output |
|---------|--------|
| `labtrust generate-benchmark-cases --pcs-bench-layout` | Case suite: `valid/`, `invalid/`, `suite.yaml`, `benchmark_manifest.v0.json`, `benchmark_task.v0.json` |
| `labtrust benchmark-reproducibility` | Run ingest: `pcs_bench_ingest.v0.json`, `benchmark_report.v0.json`, `benchmark_manifest.v0.json` |
| `labtrust verify-benchmark-cases --validate-pcs-core-output` | Schema gate (LabTrust + pcs-core) |

## Canonical refresh (pcs-bench)

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out ../pcs-bench/benchmarks/labtrust_qc_release \
  --pcs-bench-layout \
  --seed 42 \
  --validate-pcs-core-output ../pcs-core

cd ../pcs-bench
pcs-bench validate-cases --suite labtrust-qc-release --pcs-core ../pcs-core
```

Publish into pcs-core registry (optional):

```bash
python examples/pcs_qc_release/scripts/generate_pcs_bench_suite.py \
  --out ../pcs-core/benchmarks/labtrust-qc-release \
  --registry ../pcs-core/examples/benchmark_registry.valid.json \
  --validate-pcs-core-output ../pcs-core
```

## Reproducibility ingest (pcs-bench runs)

```bash
labtrust benchmark-reproducibility \
  --workflow hospital_lab.qc_release \
  --mode full_regeneration \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --runs 5 \
  --out benchmark_runs/labtrust_reproducibility \
  --validate-pcs-core-output ../pcs-core

python examples/pcs_qc_release/scripts/publish_reproducibility_ingest.py \
  --out benchmark_runs/labtrust_reproducibility \
  --pcs-core ../pcs-core
```

`pcs_bench_ingest.v0.json` embeds pcs-core `BenchmarkRun.v0` (one per iteration) and
`CoverageReport.v0` (`release_reproducibility_score`). Companion files:

- `benchmark_run.v0.json` — LabTrust aggregate multi-run summary
- `benchmark_report.v0.json` — pcs-core suite report with `metric_summaries`
- `benchmark_manifest.v0.json` — reproducibility producer manifest

## Validation layers

1. LabTrust vendored schemas under `policy/schemas/pcs/`
2. pcs-core cross-schema validation when `--validate-pcs-core-output` is set
3. CI scripts under `examples/pcs_qc_release/scripts/ci_validate_*`

## Smoke fixtures

| Path | Purpose |
|------|---------|
| `examples/pcs_qc_release/benchmark_packet/` | Two-case smoke packet |
| `examples/pcs_qc_release/benchmark_ingest/golden/` | Optional committed ingest golden (regenerate via `materialize_benchmark_ingest_golden.py`) |

See also [labtrust-benchmark-profile.md](labtrust-benchmark-profile.md).
