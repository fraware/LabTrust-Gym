# PCS export commands

LabTrust-Gym exports Proof-Carrying Science (PCS) artifacts for the QC-release demo. All bundle shapes validate against [pcs-core](https://github.com/SentinelOps-CI/pcs-core) when that package is installed.

## Commands

| Command | Output |
|---------|--------|
| `labtrust run-demo qc-release` | Run directory with `trace.json`, `run_meta.json` |
| `labtrust export-trace --run <dir> --out trace.json` | Hash-chained trace |
| `labtrust export-runtime-receipt --run <dir> --out runtime_receipt.json` | `RuntimeReceipt.v0` |
| `labtrust export-pcs --run <dir> --out science_claim_bundle.pending.json` | Pending `ScienceClaimBundle.v0` |
| `labtrust attach-certificate --bundle ... --certificate ... --out ...` | Certified bundle |

## Trace model

Each event includes: `event_id`, `run_id`, `sample_id`, `timestamp`, `actor_id`, `actor_role`, `action`, `pre_state`, `post_state`, `policy_decision`, `reason_code`, `event_hash`, `previous_event_hash`.

Actions: `accession_sample`, `perform_qc`, `record_analysis`, `release_sample`.

Reason codes: `ok`, `missing_qc`, `unauthorized_release`, `invalid_transition`, `policy_denied`.

## Hashing

- Event hash: SHA-256 of canonical JSON of the event body (excluding `event_hash`), chained via `previous_event_hash` (genesis `0`×64).
- Trace hash: pcs-core canonical digest over `{version, run_id, sample_id, event_hashes}` prefixed with `sha256:`.
- Artifact digests: pcs-core `canonical_hash` (signature field excluded).

Implementation: `src/labtrust_gym/pcs/`.
