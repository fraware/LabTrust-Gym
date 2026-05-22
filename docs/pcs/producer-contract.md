# PCS bench producer contract

LabTrust-Gym is the reference workflow producer for the hospital lab QC release benchmark.
It emits `pcs_bench_ingest.v0.json` aligned with [pcs-core](https://github.com/SentinelOps-CI/pcs-core)
`PcsBenchIngest.v0` and consumable by [pcs-bench](https://github.com/SentinelOps-CI/pcs-bench).

## Canonical workflow identity

```text
workflow_id = hospital_lab.qc_release
```

CLI aliases resolve to this property id before any artifact is written.

## Release-grade producer

```bash
make pcs-bench-producer
```

Runs `labtrust benchmark-reproducibility` with `full_regeneration` (five runs, live CertifyEdge)
then `pcs-bench validate-ingest --release-grade`.

| Variable | Default |
|----------|---------|
| `PCS_CORE` | `../pcs-core` |
| `PCS_BENCH` | `../pcs-bench` |
| `BENCH_RUN_DIR` | `benchmark_runs/labtrust_reproducibility` |

## Release-grade gates

| Gate | Requirement |
|------|-------------|
| Mode | `full_regeneration` |
| Runs | >= 5 |
| CertifyEdge | `certifyedge_call_success_rate == 1.0` |
| Per run | release protocol, status policy, and pcs-core validation passed |
| Stability | `canonical_hashes_stable` and `release_validation_stable` |
| Commit | Real 40-character git `source_commit` |
| Embedded objects | Non-empty `benchmark_runs`, `coverage_reports`, and `commands` |
| Validation | pcs-core schema + `pcs-bench validate-ingest --release-grade` |

## Emitted artifacts

Under `benchmark_runs/labtrust_reproducibility/`:

| File | Role |
|------|------|
| `pcs_bench_ingest.v0.json` | pcs-core ingest (embedded runs + coverage + `artifact_refs`) |
| `benchmark_run.v0.json` | LabTrust aggregate summary |
| `coverage_report.v0.json` | Reproducibility coverage |
| `benchmark_report.v0.json` | pcs-core report |
| `benchmark_manifest.v0.json` | Producer manifest |
| `hash_stability_report.v0.json` | Hash stability slice |
| `regeneration_reports/*.json` | Per-run regeneration reports |
| `artifact_refs/` | Sidecars for embedded pcs-core objects |

## pcs-bench consumption

Producer gate path:

```text
benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json
```

`pcs-bench validate-ingest` checks schema, semantic rules, release-grade adequacy, and nested
`BenchmarkRun.v0` / `CoverageReport.v0` objects.

## Offline CI fixture

```bash
make pcs-fixtures
make pcs-verify
make pcs-bench-publish-fixtures   # optional: copy into ../pcs-bench
```

Committed tree: `tests/fixtures/pcs_bench_reproducibility/`.

See [benchmark-producer.md](benchmark-producer.md) for command tables.
