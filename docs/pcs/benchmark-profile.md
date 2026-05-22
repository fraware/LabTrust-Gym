# LabTrust PCS benchmark profile

Producer commands: [benchmark-producer.md](benchmark-producer.md). Producer contract: [producer-contract.md](producer-contract.md).

The benchmark evaluates **release-chain integrity**, failure localization, repair hints, and
pcs-bench readiness for a simulated lab workflow. Clinical correctness is out of scope for this benchmark profile.

## What it evaluates

- Protocol artifact completeness (receipts, bundles, handoffs, certificates)
- Hash and handoff digest alignment across LabTrust, CertifyEdge, and pcs-core
- Status-policy boundaries (LabTrust vs Provability Fabric admission)
- Negative cases with machine-readable failure codes and detection layers
- Lean trust-envelope obligation inputs (`trust_envelope_only` scope)
- Reproducibility of release hashes and `verify-release-protocol` outcomes

## Artifact contracts

| Artifact | Role |
|----------|------|
| `benchmark_case.v0.json` | pcs-core `BenchmarkCase.v0` |
| `labtrust_benchmark_extension.v0.json` | LabTrust detection layer metadata |
| `input_artifacts/` | Release-shaped inputs |
| `expected_failure.json` | Failing check and code |
| `expected_repair_hint.json` | Repair hint and responsible component |
| `pcs_bench_ingest.v0.json` | pcs-core ingest bundle |
| `benchmark_manifest.v0.json` | Producer manifest |

Schemas: `policy/schemas/pcs/BenchmarkCase.v0.schema.json` and related v0 schemas.

Smoke packet: `examples/pcs_qc_release/benchmark_packet/`.

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
| `scientific_memory_import_failure/` | import failure | Scientific Memory |

## Regenerate benchmark cases

Flat suite (in-repo examples):

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/benchmark \
  --seed 42
```

pcs-bench layout:

```bash
make pcs-bench-sync-suite
```

## Definition of done

1. `generate-benchmark-cases --pcs-bench-layout` emits suite layout and manifest.
2. `make pcs-bench-producer` passes release-grade ingest validation.
3. `make pcs-verify` passes offline fixture + producer contract checks.
4. pcs-bench producer gate consumes the reproducibility ingest without fixture fallback.

Suite id: `labtrust-qc-release-v0`. Registry expectations:
`examples/pcs_qc_release/policy/benchmark_registry.labtrust-qc-release.expected.json`.
