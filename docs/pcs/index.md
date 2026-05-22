# Proof-Carrying Science (PCS)

LabTrust-Gym ships a **reference workflow** for [Proof-Carrying Science](https://github.com/SentinelOps-CI/pcs-core). The workflow simulates a hospital lab QC-release path, produces versioned JSON artifacts, validates them with [pcs-core](https://github.com/SentinelOps-CI/pcs-core), and can run the full trust loop with CertifyEdge, Provability Fabric, and Scientific Memory when those tools are installed.

The PCS demonstration is a **research simulation** for laboratory automation benchmarks and carries no clinical deployment claims.

## Quick start

1. Install an isolated environment (recommended).

   ```powershell
   .\scripts\setup_pcs_dev.ps1
   .\.venv-pcs\Scripts\Activate.ps1
   ```

   ```bash
   bash scripts/setup_pcs_dev.sh
   source .venv-pcs/bin/activate
   ```

2. Run the demo and export artifacts.

   ```bash
   labtrust run-demo qc-release
   labtrust export-trace --run runs/qc-release --out trace.json
   labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
   labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
   ```

3. Run in-repo checks.

   ```bash
   pytest tests/pcs -q
   bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh
   ```

Hands-on layout is documented in the [PCS quickstart](../examples/pcs_qc_release-quickstart.md) and in the [repository example tree](https://github.com/fraware/LabTrust-Gym/tree/main/examples/pcs_qc_release).

## Documentation map

| Topic | Document |
|-------|----------|
| Quickstart | [examples/pcs_qc_release-quickstart.md](../examples/pcs_qc_release-quickstart.md) |
| End-to-end operator steps | [examples/pcs_qc_release-operator.md](../examples/pcs_qc_release-operator.md) |
| Cross-repo release gate | [pcs_v01_clean_chain.md](../pcs_v01_clean_chain.md) |
| Export commands | [pcs_export.md](../pcs_export.md) |
| Trace and reason codes | [pcs_trace_model.md](../pcs_trace_model.md) |
| Handoff bundle layout | [pcs_handoff.md](../pcs_handoff.md) |
| Add a second workflow | [extending-workflows.md](extending-workflows.md) |
| Benchmark producer (how-to) | [benchmark-producer.md](benchmark-producer.md) |
| Benchmark producer contract | [producer-contract.md](producer-contract.md) |
| Benchmark taxonomy | [benchmark-profile.md](benchmark-profile.md) |
| Scope and non-goals | [pcs_limitations.md](../pcs_limitations.md) |
| CLI reference | [contracts/cli_contract.md](../contracts/cli_contract.md) |
| Workflow starter template | [templates/pcs_workflow_template](https://github.com/fraware/LabTrust-Gym/tree/main/templates/pcs_workflow_template) |

## Release checklist

Before tagging a PCS release, confirm that every step below passes from a clean checkout.

| Step | Command |
|------|---------|
| In-repo CI (matches GitHub `pcs` workflow) | `bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh` |
| Offline producer fixtures | `make pcs-verify` (requires sibling `pcs-core`) |
| Full cross-repo chain (optional) | `bash examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh` |
| Release-grade benchmark ingest (optional) | `make pcs-bench-producer` (requires CertifyEdge on PATH) |

Set `PCS_DETERMINISTIC=1` for fixture-stable exports in CI and golden regeneration.

## Repository layout

| Path | Role |
|------|------|
| `src/labtrust_gym/pcs/` | Workflow SDK, benchmark and regeneration helpers |
| `examples/pcs_qc_release/` | Reference QC-release workflow, `release/`, benchmarks, scripts |
| `policy/pcs/` | Demo roles, reason codes, lifecycle policy |
| `policy/schemas/pcs/` | LabTrust JSON Schema copies (validate against pcs-core for releases) |
| `tests/pcs/` | Unit and integration tests |
| `tests/fixtures/pcs_bench_reproducibility/` | Offline pcs-bench ingest producer tree |

## Two fixture trees (keep separate)

| Directory | Use |
|-----------|-----|
| `examples/pcs_qc_release/expected/` | LabTrust-local deterministic goldens for unit tests (may include a mock certificate) |
| `examples/pcs_qc_release/release/` | Cross-repo release evidence; must match pcs-core `examples/labtrust-release/` |

Regenerate release evidence atomically with `run_pcs_v01_clean_chain.sh` and `PCS_COPY_TO_RELEASE=1`, or sync from pcs-core after LabTrust protocol enrichment.

```bash
python scripts/apply_pcs_core_labtrust_schema_profiles.py --pcs-core ../pcs-core
python -m labtrust_gym.pcs.sync_pcs_core_rc --pcs-core ../pcs-core/examples/labtrust-release
python -m labtrust_gym.pcs.sync_pcs_core_rc --verify-only --pcs-core ../pcs-core/examples/labtrust-release
```

## External repositories

| Repository | Role |
|------------|------|
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | Schemas, canonical hashing, `pcs validate` |
| [pcs-bench](https://github.com/SentinelOps-CI/pcs-bench) | Benchmark runner, `validate-ingest`, `validate-cases` |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | Trace certificates |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Verify and sign science claim bundles |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Import and render signed claims |

## Canonical workflow id

All PCS exports use the following workflow identifier.

```text
workflow_id = hospital_lab.qc_release
```

CLI aliases such as `qc-release` resolve to this id before any artifact is written.
