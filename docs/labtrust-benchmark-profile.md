# LabTrust PCS benchmark profile

Producer workflow and pcs-bench integration: [pcs-benchmark-producer.md](pcs-benchmark-producer.md).

LabTrust provides the reference **benchmark-grade** PCS workflow for hospital lab QC release.
The benchmark evaluates release-chain integrity, failure localization, repair hints, and
readiness for pcs-bench — not clinical correctness.

## What this benchmark evaluates

- Protocol artifact completeness (`RuntimeReceipt.v0`, bundles, handoffs, certificates)
- Hash and handoff digest alignment across LabTrust, CertifyEdge, and pcs-core validation
- Status-policy boundaries (LabTrust vs Provability Fabric admission)
- Negative cases with machine-readable failure codes and detection layers
- Lean trust-envelope obligation inputs (`trust_envelope_only`)
- Reproducibility of committed release hashes and `verify-release-protocol` outcomes

## What it does not evaluate

The LabTrust benchmark evaluates PCS release-chain integrity and failure localization for a
simulated lab workflow. It does **not** evaluate clinical correctness or real hospital
deployment safety.

## Artifact contracts

| Artifact | Role |
|----------|------|
| `benchmark_case.v0.json` | pcs-core `BenchmarkCase.v0` (status, failure code, provenance, digest) |
| `labtrust_benchmark_extension.v0.json` | LabTrust-only: detection layer, protocol failure code |
| `input_artifacts/` | Release-shaped inputs (`input_artifacts.release_directory`) |
| `expected_failure.json` | Protocol-level failing check and code |
| `expected_repair_hint.json` | `responsible_component`, `repair_hint.kind`, `repair_command` |
| `benchmark_index.json` | Suite index |
| `coverage_report.v0.json` | Taxonomy coverage (case kinds, detection layers) |
| `benchmark_run.v0.json` | Reproducibility summary (full_regeneration runs) |
| `hash_stability_report.v0.json` | Hash-stability slice (baseline copy runs) |
| `regeneration_reports/` | Per-run `regeneration_report.json` from full_regeneration |
| `benchmark_manifest.v0.json` | LabTrust producer manifest (pcs-bench case suite or reproducibility run) |
| `pcs_bench_ingest.v0.json` | pcs-core `PcsBenchIngest.v0` (embedded runs, coverage, commands, artifact_refs) |
| `benchmark_report.v0.json` | pcs-core `BenchmarkReport.v0` (reproducibility metric rollups) |

Schemas: `policy/schemas/pcs/BenchmarkCase.v0.schema.json`, `BenchmarkRun.v0.schema.json`,
`CoverageReport.v0.schema.json`, `ReproducibilityBenchmarkReport.v0.schema.json`.

Minimal smoke packet: `examples/pcs_qc_release/benchmark_packet/` (`valid_release`,
`invalid_trace_hash_tamper`, `reproduce.sh`, `expected_report.json`).

## Failure case taxonomy

| Directory | Case kind | Detection layer |
|-----------|-----------|-----------------|
| `valid_release/` | valid_release | LabTrust |
| `missing_qc_result/` | missing_qc_step | LabTrust |
| `unauthorized_release/` | unauthorized_actor | LabTrust |
| `trace_hash_tamper/` | invalid_hash_mismatch | LabTrust |
| `certificate_id_tamper/` | certificate_tamper | CertifyEdge |
| `stale_trace_after_certificate/` | status_transition | LabTrust |
| `legacy_handoff_file/` | handoff_tamper | LabTrust |
| `placeholder_commit/` | provenance_invalid | LabTrust |
| `lean_trace_hash_mismatch/` | formal_check_failure | Lean trust kernel |
| `lean_rejected_certificate/` | formal_check_failure | Lean trust kernel |
| `lean_stale_certificate/` | formal_check_failure | Lean trust kernel |
| `lean_signed_hash_mismatch/` | formal_check_failure | Provability Fabric |
| `scientific_memory_import_failure/` | scientific_memory_import_failure | Scientific Memory |

Release baseline must include `signed_science_claim_bundle.json` and `verification_result.json`
(materialize with `examples/pcs_qc_release/scripts/materialize_downstream_release_artifacts.py`).

## Expected metrics (pcs-bench)

- **Failure localization accuracy**: detected layer matches `expected_detection_layer`
- **Failure code precision**: benchmark + protocol codes match `expected_failure.json`
- **Repair hint coverage**: `expected_repair_hint_kind` and `repair_command` present
- **Reproducibility**: `artifact_hashes_stable`, `release_validation_stable`, `command_deterministic`
- **Certificate stability**: `certificate_id_stable` or `certificate_id_non_deterministic_declared`

## Regenerate benchmark cases

LabTrust flat suite (examples):

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/benchmark \
  --seed 42
```

pcs-bench canonical layout (refresh fixtures in the pcs-bench repo):

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out ../pcs-bench/benchmarks/labtrust_qc_release \
  --pcs-bench-layout \
  --seed 42

cd ../pcs-bench
pcs-bench validate-cases --suite labtrust-qc-release --pcs-core ../pcs-core
```

To publish into pcs-core instead of pcs-bench:

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out ../pcs-core/benchmarks/labtrust-qc-release \
  --pcs-bench-layout \
  --seed 42

# or
python examples/pcs_qc_release/scripts/generate_pcs_bench_suite.py
```

Each case uses `input_artifacts.release_directory` = `input_artifacts/`. Valid cases omit
`expected_failure.json`. `benchmark_manifest.v0.json` records the LabTrust generator version
and git commit.

```bash
python examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py
python examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_core.py
```

Legacy failure gallery (demos): `labtrust generate-failure-gallery --out examples/pcs_qc_release/failures`.

## Reproducibility benchmark

```bash
labtrust benchmark-reproducibility \
  --workflow hospital_lab.qc_release \
  --mode full_regeneration \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --runs 5 \
  --out benchmark_runs/labtrust_reproducibility \
  --seed 42 \
  --validate-pcs-core-output ../pcs-core
```

Writes `benchmark_run.v0.json`, `coverage_report.v0.json`, `hash_stability_report.v0.json`,
`regeneration_reports/`, `pcs_bench_ingest.v0.json`, and `benchmark_manifest.v0.json`.
`pcs_bench_ingest.v0.json` embeds pcs-core `BenchmarkRun.v0` and `CoverageReport.v0` objects
(not path-only references) plus optional `artifact_refs` for on-disk companions.

Default mode `full_regeneration` re-runs `regenerate-release-protocol` each iteration and
records artifact/canonical hash stability, CertifyEdge success, release protocol validation,
status policy, and pcs-core validation. CI falls back to `hash_stability` when CertifyEdge is
unavailable (`examples/pcs_qc_release/scripts/ci_benchmark_reproducibility.py`).

## Definition of done (LabTrust producer)

1. `labtrust generate-benchmark-cases --pcs-bench-layout` emits `suite.yaml`, `benchmark_manifest.v0.json`, `valid/`, `invalid/`, and `coverage_report.v0.json`.
2. Each case uses `input_artifacts.release_directory` = `input_artifacts/` (flat) or pcs-core fixture paths after layout patch.
3. Valid cases use pcs-core null failure fields; invalid cases ship `expected_failure.json` and repair hints.
4. `labtrust benchmark-reproducibility --mode full_regeneration` (default) writes `benchmark_run.v0.json`, `coverage_report.v0.json`, `hash_stability_report.v0.json`, `regeneration_reports/`, `pcs_bench_ingest.v0.json`, and `benchmark_manifest.v0.json`.
5. `--validate-pcs-core-output ../pcs-core` validates `BenchmarkRun.v0`, `CoverageReport.v0`, and `PcsBenchIngest.v0` (and `BenchmarkReport.v0` when present).
6. Generated cases validate against pcs-core when a checkout is provided.
7. pcs-bench ingests `pcs_bench_ingest.v0.json` from reproducibility runs directly.

## pcs-bench integration

Suite id `labtrust-qc-release-v0`. Layout: `valid/<case_id>/`, `invalid/<case_id>/`,
`suite.yaml`, `benchmark_manifest.v0.json`. Each case's `release_directory` is
`benchmarks/labtrust-qc-release/<polarity>/<case_id>/input_artifacts` (pcs-core repo root).

Registry expectations: `examples/pcs_qc_release/policy/benchmark_registry.labtrust-qc-release.expected.json`.
Export to pcs-core: `examples/pcs_qc_release/scripts/export_pcs_bench_to_pcs_core.ps1`.

Legacy pcs-core case ids (`valid-release-chain`, `invalid-trace-hash`, …) are replaced by
LabTrust-generated ids (`labtrust-valid-release-v0`, `labtrust-trace-hash-tamper-v0`, …); see
`legacy_case_id_map` in the expected registry file.

For flat LabTrust examples, load `benchmark_index.json`, iterate `cases`, and read
`benchmark_case.v0.json` plus `input_artifacts/`. Use `labtrust_benchmark_extension.v0.json`
for detection-layer assertions in simulate mode.
