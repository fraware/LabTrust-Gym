# LabTrust as PCS reference implementation

LabTrust-Gym is the **reference workflow** for protocol-native PCS: it demonstrates how to
implement `WorkflowProfile.v0`, runtime artifacts, handoffs, certificate attach, verifier
handoff, component release fragment, failure gallery, and clean-run regeneration with a
machine-readable benchmark report.

## Start here

| Goal | Document / path |
|------|------------------|
| Implement a second workflow | [pcs-workflow-implementation-guide.md](pcs-workflow-implementation-guide.md) |
| Copy-paste starter | [templates/pcs_workflow_template/](../templates/pcs_workflow_template/) |
| QC release walkthrough | [reference-workflow-template.md](reference-workflow-template.md) |
| CLI contract | [contracts/cli_contract.md](contracts/cli_contract.md) |
| Failure manifest spec | [../schemas_or_docs/FailureCaseManifest.v0.md](../schemas_or_docs/FailureCaseManifest.v0.md) |
| Benchmark profile | [labtrust-benchmark-profile.md](labtrust-benchmark-profile.md) |
| BenchmarkCase spec | [../schemas_or_docs/BenchmarkCase.v0.md](../schemas_or_docs/BenchmarkCase.v0.md) |
| pcs-core upstream proposal | [../schemas_or_docs/proposals/FailureCaseManifest-v0-pcs-core.md](../schemas_or_docs/proposals/FailureCaseManifest-v0-pcs-core.md) |
| BenchmarkCase pcs-core proposal | [../schemas_or_docs/proposals/BenchmarkCase-v0-pcs-core.md](../schemas_or_docs/proposals/BenchmarkCase-v0-pcs-core.md) |

## Code map

| Layer | Module / example |
|-------|------------------|
| Workflow SDK | `src/labtrust_gym/pcs/workflows/base.py` (`PCSWorkflow`) |
| Reference workflow | `src/labtrust_gym/pcs/workflows/qc_release.py` |
| Registry | `src/labtrust_gym/pcs/workflows/registry.py` |
| Regeneration report | `src/labtrust_gym/pcs/regeneration_report.py` |
| Proof-obligation / Lean readiness | `src/labtrust_gym/pcs/formalization.py` |
| Failure manifests | `src/labtrust_gym/pcs/failure_case_manifest.py` |
| Benchmark cases | `src/labtrust_gym/pcs/benchmark_cases.py`, `benchmark_case.py` |
| Reproducibility bench | `src/labtrust_gym/pcs/benchmark_reproducibility.py` |
| JSON Schema | `policy/schemas/pcs/*.v0.schema.json` (RegenerationReport, FailureCaseManifest, BenchmarkCase, …) |
| Committed release | `examples/pcs_qc_release/release/` |
| Failure gallery | `examples/pcs_qc_release/failures/` |
| Benchmark suite | `examples/pcs_qc_release/benchmark/` |

## Canonical commands

```bash
labtrust regenerate-release-protocol \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --out examples/pcs_qc_release/release

python examples/pcs_qc_release/scripts/ci_validate_regeneration_report.py
python examples/pcs_qc_release/scripts/ci_validate_formalization.py
python examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py
labtrust generate-benchmark-cases --out examples/pcs_qc_release/benchmark --seed 42
labtrust verify-benchmark-cases --benchmark-dir examples/pcs_qc_release/benchmark
labtrust benchmark-reproducibility --pcs-core ../pcs-core --runs 5 \
  --out benchmark_runs/labtrust_reproducibility
pytest tests/pcs -q
```

Publish aligned fixtures to pcs-core:

```bash
python -m labtrust_gym.pcs.sync_pcs_core_rc --publish
```
