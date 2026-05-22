# PCS export commands

LabTrust-Gym exports Proof-Carrying Science (PCS) artifacts for the QC-release demo. Every PCS artifact uses **`schema_version: "v0"`** and validates against [pcs-core](https://github.com/SentinelOps-CI/pcs-core) when that package is installed.

## Commands

| Command | Output |
|---------|--------|
| `labtrust run-demo qc-release` | Run directory with `trace.json`, `run_meta.json` |
| `labtrust export-trace --run <dir> --out trace.json` | Hash-chained trace |
| `labtrust export-runtime-receipt --run <dir> --out runtime_receipt.json` | `RuntimeReceipt.v0` |
| `labtrust export-pcs --run <dir> --out science_claim_bundle.pending.json` | Pending `ScienceClaimBundle.v0` |
| `labtrust attach-certificate --bundle ... --certificate ... --out ...` | Certified bundle |
| `labtrust validate-pcs --run <dir>` | Validate trace and pcs-core artifacts in a run |
| `labtrust validate-pcs --artifact <file.json>` | Validate a single PCS JSON file |
| `labtrust export-pcs-handoff --out handoff/` | CertifyEdge and Provability Fabric handoff bundle |

Exports validate against pcs-core by default. Pass `--no-validate` only when you are debugging schema or hashing interactively.

Provability Fabric writes **`SignedScienceClaimBundle.v0`** to `signed_science_claim_bundle.json`; see the [PCS operator runbook](examples/pcs_qc_release-operator.md) for the signing segment.

The trace event model is described in [pcs_trace_model.md](pcs_trace_model.md).

## Trace model (CertifyEdge handoff)

Top-level `trace.json` contains `schema_version` (`"v0"`), `run_id`, `sample_id`, `events`, and `trace_hash`.

Each event carries `event_id`, `run_id`, `sample_id`, `timestamp`, `actor_id`, `actor_role`, `action`, `pre_state`, `post_state`, `policy_decision`, `reason_code`, `event_hash`, and `previous_event_hash`.

Supported actions include `accession_sample`, `perform_qc`, `record_analysis`, and `release_sample`.

Reason codes include `ok`, `missing_qc`, `unauthorized_release`, `invalid_transition`, and `policy_denied`.

Golden traces for CertifyEdge live under `examples/pcs_qc_release/expected/` as `valid_trace.json`, `invalid_missing_qc_trace.json`, and `invalid_unauthorized_trace.json`.

## RuntimeReceipt.v0

| Field | Semantics |
|-------|-----------|
| `status` | Always `RuntimeObserved` because the run was recorded |
| `run_outcome` | `passed` or `failed` for the workflow result |
| `final_reason_code` | `ok`, `missing_qc`, `unauthorized_release`, and related codes |
| `released` | Whether `release_sample` succeeded |
| `local_dev` | `true` when `source_commit` comes from a local run without git metadata |

**Fixture trees.** `examples/pcs_qc_release/expected/` holds LabTrust-local deterministic goldens, including `trace_certificate.mock.v0.json` for unit tests. `examples/pcs_qc_release/release/` holds cross-repo release candidates built with CertifyEdge through `generate_release_candidate.sh`. Regenerate local goldens with `generate_golden.py` and `PCS_DETERMINISTIC=1`.

## CI validation

GitHub Actions (`.github/workflows/pcs.yml`) runs the full PCS gate, including tests, export validation, benchmark cases, reproducibility ingest, producer contract, release protocol, and failure gallery.

Local parity uses the same script as CI.

```bash
bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh
```

See [pcs/index.md](pcs/index.md) for the documentation map and release checklist.

## Hashing

Event hashes use SHA-256 over the canonical JSON event body (excluding `event_hash`), chained through `previous_event_hash` with genesis `0` repeated 64 times. The trace hash is the pcs-core canonical digest over `{schema_version, version, run_id, sample_id, event_hashes}` formatted as `sha256:…`. Artifact digests use pcs-core `canonical_hash` with signature fields excluded.

Implementation code lives in `src/labtrust_gym/pcs/`.
