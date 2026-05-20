# LabTrust PCS benchmark profile

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
| `benchmark_run.v0.json` | Reproducibility summary (pcs-bench compatible) |
| `regeneration_report.json` | Full reproducibility report (`ReproducibilityBenchmarkReport.v0`) |

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

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/benchmark \
  --seed 42

python examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py
```

Legacy failure gallery (demos): `labtrust generate-failure-gallery --out examples/pcs_qc_release/failures`.

## Reproducibility benchmark

```bash
labtrust benchmark-reproducibility \
  --pcs-core ../pcs-core \
  --runs 5 \
  --out benchmark_runs/labtrust_reproducibility \
  --seed 42
```

Default mode `full_regeneration` re-runs `regenerate-release-protocol` each iteration and
records artifact/canonical hash stability, CertifyEdge success, release protocol validation,
status policy, and pcs-core validation. CI falls back to `hash_stability` when CertifyEdge is
unavailable (`examples/pcs_qc_release/scripts/ci_benchmark_reproducibility.py`).

## pcs-bench integration

Suite id `labtrust-qc-release-v0`. Load `benchmark_index.json`, iterate `cases`, and for each
case read `benchmark_case.v0.json` plus `input_artifacts/`. Use `labtrust_benchmark_extension.v0.json`
for detection-layer assertions in simulate mode.
