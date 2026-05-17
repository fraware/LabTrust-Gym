# PCS trace model (LabTrust-Gym QC-release v0.1)

LabTrust-Gym emits a **LabTrust-specific** `trace.json` for CertifyEdge and downstream certification. PCS bundles (`RuntimeReceipt.v0`, `ScienceClaimBundle.v0`, etc.) are validated by [pcs-core](https://github.com/SentinelOps-CI/pcs-core).

## Top-level trace document

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `"v0"` | PCS profile version |
| `version` | `"0"` | LabTrust trace format revision |
| `artifact_kind` | `"Trace"` | Discriminator for tooling |
| `run_id` | string | Stable run identifier |
| `sample_id` | string | Simulated sample identifier |
| `events` | array | Ordered workflow events |
| `trace_hash` | `sha256:…` | Canonical digest (see below) |

## Event record

Each element of `events` MUST include:

| Field | Description |
|-------|-------------|
| `event_id` | Unique id within the run |
| `run_id` | Same as trace `run_id` |
| `sample_id` | Same as trace `sample_id` |
| `timestamp` | ISO-8601 timestamp (fixed in workflow YAML for determinism) |
| `actor_id` | Simulated actor identifier |
| `actor_role` | Role id from `policy/pcs/roles.yaml` |
| `action` | One of the required actions (below) |
| `pre_state` | Sample lifecycle state before the action |
| `post_state` | State after policy evaluation |
| `policy_decision` | `allow` or `deny` |
| `reason_code` | From `policy/pcs/reason_codes.yaml` |
| `event_hash` | SHA-256 hex of canonical event body (no `event_hash` field) |
| `previous_event_hash` | Previous event’s `event_hash`, or `0`×64 for genesis |

### Required actions

1. `accession_sample`
2. `perform_qc`
3. `record_analysis`
4. `release_sample`

### Reason codes (v0.1)

- `ok` — permitted
- `missing_qc` — release without QC
- `unauthorized_release` — release by non-release-capable role
- `invalid_transition` — action invalid in current lifecycle state
- `policy_denied` — generic denial

## Event hash chain

1. Build event body (all fields except `event_hash`).
2. `event_hash = SHA256(canonical_json(body))` as lowercase hex (64 chars).
3. Chain: `events[0].previous_event_hash = "0" * 64`; each next event uses prior `event_hash`.

Canonical JSON: sorted keys, compact separators `,` and `:`.

## Trace hash {#trace-hash}

The trace-level digest bound into `RuntimeReceipt.v0.trace_hash`:

```json
{
  "schema_version": "v0",
  "version": "0",
  "run_id": "<run_id>",
  "sample_id": "<sample_id>",
  "event_hashes": ["<event_hash_0>", "<event_hash_1>", "..."]
}
```

Digest: pcs-core `canonical_hash` → `sha256:<64 lowercase hex>`.

`RuntimeReceipt.v0.output_hashes["trace.json"]` is the **file** digest (bytes of exported JSON). `trace_hash` is the **logical** digest above.

## Sample lifecycle `pre_state` / `post_state`

| Field | Meaning |
|-------|---------|
| `lifecycle` | `registered`, `accessioned`, `qc_complete`, `analyzed`, `released` |
| `qc_complete` | boolean |
| `analysis_complete` | boolean |
| `released` | boolean |

## Handoff files

Golden traces for CertifyEdge: `examples/pcs_qc_release/expected/*_trace.json`.

Generate handoff bundle:

```bash
labtrust export-pcs-handoff --out handoff/
```
