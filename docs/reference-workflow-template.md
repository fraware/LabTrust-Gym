# PCS reference workflow template (LabTrust)

This document describes how to implement a **domain workflow** on top of the shared PCS trust loop, using LabTrust’s QC release path as the reference. Copy this pattern for new workflows (for example agent tool-use); do not hardcode protocol steps in application code.

## 1. Define WorkflowProfile.v0

Author `examples/<your_workflow>/workflow_profile.v0.json` validated by pcs-core:

| Field | Purpose |
|-------|---------|
| `workflow_id` | Stable id (`labtrust.qc_release_v0.1`, `agent_tool_use.safety_v0`). |
| `domain` | Coarse domain label. |
| `runtime_artifacts` | Types produced before certification (`RuntimeReceipt.v0`, …). |
| `certificate_artifacts` | Certificate types (`TraceCertificate.v0`, …). |
| `handoff_sequence` | Ordered `handoff_kind` values for the trust graph. |
| `required_registry_entries` | Artifact types that must exist in `ArtifactRegistry.v0`. |
| `status_policy` | Allowed terminal statuses and **forbidden transitions** (e.g. never `RuntimeObserved` → `ProofChecked` from LabTrust). |
| `failure_modes` | Named negative cases for galleries and benchmarks. |
| `limitations_notice` | Non-goals and scope boundaries. |
| `required_admission_profile` | PF admission profile id (e.g. `labtrust_qc_release`). |
| `signature_or_digest` | Canonical pcs-core digest of the profile body. |

LabTrust binds `property_id` for handoff invariants separately (see `workflow_profile.py`).

Validate:

```bash
pcs validate examples/<workflow>/workflow_profile.v0.json
pcs registry check-artifact examples/<workflow>/workflow_profile.v0.json
```

## 2. Implement the workflow module

Under `src/labtrust_gym/pcs/workflows/`:

- Subclass `PcsWorkflow` (`base.py`)
- Load `WorkflowProfileView` in `__init__` (profile drives `workflow_id`, artifact types, handoff sequence, failure modes, status policy)
- Implement **workflow-specific** methods: `generate_trace()`, `runtime_receipt_generator()`, `claim_bundle_generator()`, `generate_failure_case()`
- Register in `registry.py`

**PCS protocol steps stay on the base class** (do not duplicate in each workflow): `emit_handoff_to_certifyedge()`, `attach_certificate()`, `emit_handoff_to_pf()`, `emit_release_fragment()`, `publish_workflow_profile()`, `regenerate_protocol_package()`.

QC release reference: `workflows/qc_release.py`.

## 3. Runtime observation (LabTrust-owned)

From a clean deterministic run:

1. **Emit runtime trace** — `export_trace` → `trace.json`
2. **Emit runtime receipt** — `export_runtime_receipt` → `RuntimeReceipt.v0` with `status: RuntimeObserved`
3. **Emit pending bundle** — `export_pcs` → `science_claim_bundle.pending.json` with `claim_artifact.status: RuntimeObserved`

## 4. Runtime → certificate handoff (CertifyEdge)

```bash
labtrust emit-handoff-to-certifyedge \
  --trace trace.json \
  --runtime-receipt runtime_receipt.json \
  --property-id <your.property_id> \
  --out handoff_to_certifyedge.json
```

Call CertifyEdge with `handoff_to_certifyedge.json` (or `--spec` + `--trace` on older CLIs) to produce `trace_certificate.json`.

## 5. Attach certificate (LabTrust-owned)

```bash
labtrust attach-certificate \
  --bundle science_claim_bundle.pending.json \
  --certificate trace_certificate.json \
  --out science_claim_bundle.certified.json
```

Certified bundle must have `claim_artifact.status: CertificateChecked`. LabTrust must **never** emit `ProofChecked`.

If the trace hash diverges after attach, mark the claim **Stale**.

## 6. Bundle → verifier handoff (Provability Fabric)

```bash
labtrust emit-handoff-to-pf \
  --bundle science_claim_bundle.certified.json \
  --out handoff_to_pf.json
```

Provability Fabric owns proof admission (`ProofChecked` on `VerificationResult.v0`). Send the certified bundle and `handoff_to_pf.json` to PF; consume `verification_result.json` from the PF release chain when integrating end-to-end.

## 7. Scientific Memory

After PF signs the bundle, import the **signed** claim into Scientific Memory (release chains include `signed_science_claim_bundle.json` and `scientific_memory_import_report.json` in full-stack examples). LabTrust’s QC reference stops at the LabTrust release fragment; downstream repos own SM import semantics.

## 8. Release fragment

```bash
labtrust emit-release-fragment \
  --release-dir <release-dir> \
  --out labtrust_release_fragment.json
```

Produces `ComponentReleaseFragment.v0` for pcs-core aggregation.

## 9. One-shot clean regeneration

```bash
labtrust regenerate-release-protocol \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --out examples/<workflow>/release \
  --workflow-profile examples/<workflow>/workflow_profile.v0.json
```

Regeneration copies `workflow_profile.v0.json` into the release directory so verifiers and PF can pin workflow semantics.

## 10. Verification and status policy

```bash
labtrust verify-release-protocol --release-dir <release-dir> --pcs-core ../pcs-core
labtrust check-status-policy --release-dir <release-dir>
```

## 11. Failure gallery (benchmark material)

```bash
labtrust generate-failure-gallery \
  --workflow <workflow_id_or_property_id> \
  --out examples/<workflow>/failures
```

Each case directory contains:

- `README.md`
- `artifacts/` — input and protocol JSON
- `expected_failure.json` — failing check and code
- `repair_hint.json` — how to fix

## Status boundaries (LabTrust)

| Stage | `claim_artifact.status` |
|-------|-------------------------|
| Pending bundle | `RuntimeObserved` |
| Certified bundle | `CertificateChecked` |
| After trace mutation | `Stale` |
| Failed runtime demo | `Rejected` or failed receipt only under `failures/` |
| Proof admission | **Forbidden** on LabTrust artifacts (`ProofChecked` is PF-only) |

## Reference files (QC release)

| Artifact | Path |
|----------|------|
| WorkflowProfile | `examples/pcs_qc_release/workflow_profile.v0.json` |
| Release package | `examples/pcs_qc_release/release/` |
| Failure gallery | `examples/pcs_qc_release/failures/` |
| Workflow code | `src/labtrust_gym/pcs/workflows/qc_release.py` |
