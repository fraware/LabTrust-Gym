# LabTrust PCS bench producer contract

LabTrust-Gym is the reference scientific workflow producer for the hospital lab QC
release benchmark. It emits a canonical `pcs_bench_ingest.v0.json` aligned with
[pcs-core](https://github.com/SentinelOps-CI/pcs-core) `PcsBenchIngest.v0` and
consumable by [pcs-bench](https://github.com/SentinelOps-CI/pcs-bench) without
fixture fallback.

## Canonical workflow identity

All PCS exports use:

```text
workflow_id = hospital_lab.qc_release
```

CLI aliases (`qc_release`, `qc-release`, `labtrust_qc_release`, `hospital_lab_qc_release`,
`labtrust.qc_release_v0.1`) resolve to this property id before any artifact is written.

## Release-grade producer target

```bash
make pcs-bench-producer
```

This runs:

1. `labtrust benchmark-reproducibility` with `full_regeneration`, five runs, live
   CertifyEdge, pcs-core validation, and release-grade gates.
2. `pcs-bench validate-ingest --release-grade` on the canonical ingest path.

Environment:

| Variable | Default |
|----------|---------|
| `PCS_CORE` | `../pcs-core` |
| `PCS_BENCH` | `../pcs-bench` |
| `BENCH_RUN_DIR` | `benchmark_runs/labtrust_reproducibility` |

Manual equivalent:

```bash
labtrust benchmark-reproducibility \
  --workflow hospital_lab.qc_release \
  --mode full_regeneration \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --runs 5 \
  --out benchmark_runs/labtrust_reproducibility \
  --validate-pcs-core-output ../pcs-core \
  --release-grade

pcs-bench validate-ingest \
  --input benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json \
  --pcs-core ../pcs-core \
  --release-grade
```

## Release-grade semantics

A producer output is **release-grade** only when:

| Gate | Requirement |
|------|-------------|
| Mode | `full_regeneration` |
| Runs | `>= 5` |
| CertifyEdge | `certifyedge_call_success_rate == 1.0` |
| Per run | `release_protocol_validation_passed`, `status_policy_validation_passed`, `pcs_core_validation_passed` |
| Stability | `canonical_hashes_stable` and `release_validation_stable` (from `hash_stability_report.v0.json` when `full_regeneration` runs hash-stability copies) |
| Commit | Real 40-character git `source_commit` (not all zeros) |
| Embedded objects | Non-empty `benchmark_runs`, non-empty `coverage_reports`, non-empty `commands` |
| Validation | pcs-core schema + `pcs-bench validate-ingest --release-grade` |

`benchmark_manifest.v0.json` records release evidence:

```json
{
  "evidence_grade": "release",
  "mode": "full_regeneration",
  "runs": 5,
  "certifyedge_live": true,
  "pcs_core_validation": true,
  "canonical_hashes_stable": true
}
```

## Emitted artifacts

Under `benchmark_runs/labtrust_reproducibility/`:

| File | Schema / role |
|------|----------------|
| `pcs_bench_ingest.v0.json` | pcs-core `PcsBenchIngest.v0` (embedded runs + coverage + `artifact_refs`) |
| `benchmark_run.v0.json` | LabTrust aggregate reproducibility summary |
| `coverage_report.v0.json` | LabTrust reproducibility coverage |
| `benchmark_report.v0.json` | pcs-core `BenchmarkReport.v0` |
| `benchmark_manifest.v0.json` | `ReproducibilityBenchmarkManifest.v0` |
| `hash_stability_report.v0.json` | `HashStabilityReport.v0` |
| `regeneration_reports/*.json` | `RegenerationReport.v0` per run |
| `artifact_refs/benchmark_runs/*.v0.json` | pcs-core run sidecars |
| `artifact_refs/coverage_reports/*.v0.json` | pcs-core coverage sidecar |
| `runs/run_*` | Regenerated release protocol trees |

### Ingest `artifact_refs`

Embedded pcs-core objects each have a matching sidecar under `artifact_refs/`.
LabTrust reproducibility sidecars are also listed in ingest `artifact_refs`:

| Path | `artifact_type` | `role` |
|------|-----------------|--------|
| `benchmark_run.v0.json` | `LabtrustBenchmarkRunSummary.v0` | `reproducibility_evidence` |
| `coverage_report.v0.json` | `LabtrustReproducibilityCoverage.v0` | `producer_export` |
| `benchmark_report.v0.json` | `BenchmarkReport.v0` | `native_report` |
| `benchmark_manifest.v0.json` | `ReproducibilityBenchmarkManifest.v0` | `producer_export` |
| `hash_stability_report.v0.json` | `HashStabilityReport.v0` | `reproducibility_evidence` |
| `regeneration_reports/*.json` | `RegenerationReport.v0` | `regeneration_report` |
| `pcs_bench_ingest.v0.json` | `PcsBenchIngest.v0` | `canonical_ingest` |

Extended refs are provenance only; pcs-core `BenchmarkRun.v0` and `CoverageReport.v0`
remain embedded in the ingest body.

## pcs-bench consumption

pcs-bench producer gate resolves:

```text
benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json
```

`pcs-bench validate-ingest` checks:

1. pcs-core `PcsBenchIngest.v0` schema (pcs-core-compatible `artifact_refs` only).
2. Semantic rules (commit, embedded arrays, digest alignment for embedded types).
3. Release-grade adequacy (non-empty runs, real commit, sidecar files on disk).
4. Nested `BenchmarkRun.v0` / `CoverageReport.v0` schemas.

Normalized output feeds the cross-producer gate without using the offline fixture
when the producer target succeeds.

## Refresh LabTrust pcs-bench fixture suite

```bash
make pcs-bench-sync-suite
```

Equivalent manual flow:

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

Produces `suite.yaml`, `valid/`, `invalid/`, `benchmark_manifest.v0.json`, and
`coverage_report.v0.json` under the pcs-bench benchmarks tree.

## Offline CI fixture

`tests/fixtures/pcs_bench_reproducibility/` is a full developer-grade producer tree
(ingest, sidecars under `artifact_refs/`, manifest, reports). Regenerate and publish:

```bash
make pcs-fixtures
make pcs-verify                   # regenerate + validate fixture + pcs-bench validate-ingest
make pcs-bench-publish-fixtures   # copies into ../pcs-bench/tests/fixtures and runs/
```

The committed tree is sidecar-only (no `runs/` scratch); ingest `commands` use repo-relative `--out` paths.

Legacy single-file mirror: `tests/fixtures/pcs_bench_ingest/labtrust/pcs_bench_ingest.v0.json`.

See also [pcs-benchmark-producer.md](pcs-benchmark-producer.md) for command tables
and CI script references.
