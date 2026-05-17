# PCS export commands

LabTrust-Gym exports Proof-Carrying Science (PCS) artifacts for the QC-release demo. All PCS artifacts use **`schema_version: "v0"`** and validate against [pcs-core](https://github.com/SentinelOps-CI/pcs-core) when installed.

## Commands

| Command | Output |
|---------|--------|
| `labtrust run-demo qc-release` | Run directory with `trace.json`, `run_meta.json` |
| `labtrust export-trace --run <dir> --out trace.json` | Hash-chained trace |
| `labtrust export-runtime-receipt --run <dir> --out runtime_receipt.json` | `RuntimeReceipt.v0` |
| `labtrust export-pcs --run <dir> --out science_claim_bundle.pending.json` | Pending `ScienceClaimBundle.v0` |
| `labtrust attach-certificate --bundle ... --certificate ... --out ...` | Certified bundle |
| `labtrust validate-pcs --run <dir>` | Validate trace + pcs-core artifacts in a run |
| `labtrust validate-pcs --artifact <file.json>` | Validate a single PCS JSON file |
| `labtrust export-pcs-handoff --out handoff/` | CertifyEdge + PF handoff bundle |

Exports validate against pcs-core by default; pass `--no-validate` only for debugging.

Provability Fabric produces **`SignedScienceClaimBundle.v0`** in `signed_science_claim_bundle.json` (see RUNBOOK).

Trace event model: [pcs_trace_model.md](pcs_trace_model.md).

## Trace model (CertifyEdge handoff)

Top-level `trace.json`:

- `schema_version`: `"v0"`
- `run_id`, `sample_id`, `events`, `trace_hash`

Each event includes: `event_id`, `run_id`, `sample_id`, `timestamp`, `actor_id`, `actor_role`, `action`, `pre_state`, `post_state`, `policy_decision`, `reason_code`, `event_hash`, `previous_event_hash`.

Actions: `accession_sample`, `perform_qc`, `record_analysis`, `release_sample`.

Reason codes: `ok`, `missing_qc`, `unauthorized_release`, `invalid_transition`, `policy_denied`.

Golden traces for CertifyEdge: `examples/pcs_qc_release/expected/valid_trace.json`, `invalid_missing_qc_trace.json`, `invalid_unauthorized_trace.json`.

## RuntimeReceipt.v0

| Field | Semantics |
|-------|-----------|
| `status` | Always `RuntimeObserved` (the run was recorded) |
| `run_outcome` | `passed` or `failed` (workflow result) |
| `final_reason_code` | `ok`, `missing_qc`, `unauthorized_release`, … |
| `released` | Whether `release_sample` succeeded |
| `local_dev` | `true` when `source_commit` is not from git (local runs only) |

Release goldens require a real git `source_commit`; use `examples/pcs_qc_release/scripts/generate_golden.py`.

## Hashing

- Event hash: SHA-256 of canonical JSON of the event body (excluding `event_hash`), chained via `previous_event_hash` (genesis `0`×64).
- Trace hash: pcs-core canonical digest over `{schema_version, version, run_id, sample_id, event_hashes}` as `sha256:…`.
- Artifact digests: pcs-core `canonical_hash` (signature field excluded).

Implementation: `src/labtrust_gym/pcs/`.
