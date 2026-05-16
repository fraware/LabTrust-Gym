# PCS QC-release demonstration

The flagship PCS v0.1 demo proves that a simulated lab workflow can produce proof-carrying artifacts consumable by CertifyEdge, Provability Fabric, and Scientific Memory.

## Workflow

Valid path:

```
sample accession → QC → analysis → release
```

Invalid paths (included in CI):

- Release without QC (`missing_qc`)
- Release by unauthorized role (`unauthorized_release`)

## Policy

- `policy/pcs/roles.yaml` — roles; only `release_manager` is release-capable
- `policy/pcs/reason_codes.yaml` — documented reason codes
- `policy/pcs/qc_release_policy.yaml` — lifecycle transitions

## Example layout

```
examples/pcs_qc_release/
  valid_workflow.yaml
  invalid_missing_qc.yaml
  invalid_unauthorized_release.yaml
  expected/          # golden snapshots
  RUNBOOK.md         # full multi-repo flow
```

## Tests

```bash
pytest tests/pcs
```

See [pcs_export.md](pcs_export.md) for CLI details and [examples/pcs_qc_release/RUNBOOK.md](../examples/pcs_qc_release/RUNBOOK.md) for the canonical end-to-end procedure.
