# FailureCaseManifest.v0

Machine-readable metadata for a PCS workflow **failure gallery** case. Each case directory
includes this manifest so benchmarks (`pcs-bench`) and CI can load negative fixtures without
parsing README prose.

## File location

```text
<gallery_root>/<failure_case_id>/failure_case_manifest.json
```

Companion files (LabTrust reference layout):

- `README.md` — human-readable description
- `expected_failure.json` — check label and code (legacy; mirrors manifest fields)
- `repair_hint.json` — `{"hint": "..."}` (legacy)
- `artifacts/` — release-shaped tree used as verifier input

## JSON shape

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `failure_case_id` | string | yes | Stable case id (matches directory name) |
| `workflow_id` | string | yes | WorkflowProfile `workflow_id` |
| `expected_failure_code` | string | yes | Stable code for benchmarks and repair routing |
| `responsible_component` | string | yes | Owning layer (`workflow.runtime`, `workflow.handoff`, `certifyedge.certificate`, …) |
| `artifacts` | string[] | yes | Basenames written under `artifacts/` for this case |
| `repair_hint` | string | yes | Operator-facing fix guidance |

### Example

```json
{
  "artifacts": [
    "runtime_receipt.json",
    "run_meta.json",
    "trace.json"
  ],
  "expected_failure_code": "missing_qc",
  "failure_case_id": "missing_qc_result",
  "repair_hint": "Complete the QC verification step before release_sample.",
  "responsible_component": "workflow.runtime",
  "workflow_id": "labtrust.qc_release_v0.1"
}
```

## JSON Schema (LabTrust)

`policy/schemas/pcs/FailureCaseManifest.v0.schema.json`

Validated in CI via `examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py` and
`labtrust_gym.pcs.bench_schemas.validate_failure_case_manifest`.

## Upstream proposal (pcs-core)

Formal proposal: `schemas_or_docs/proposals/FailureCaseManifest-v0-pcs-core.md`

Suggested pcs-core placement:

- Schema: `schemas/FailureCaseManifest.v0.schema.json`
- Gallery index: extend `gallery_index.json` to reference manifest paths per case
