# Evidence bundle verification

**`labtrust verify-bundle --bundle <EvidenceBundle.v0.1 dir>`** checks integrity, schema, hashchain, and invariant consistency of an exported evidence bundle (as produced by `labtrust export-receipts`).

**Checks:** (1) **Manifest integrity** — recompute SHA-256 for every file in `manifest.json`; fail on hash mismatch, missing file, or extra file (unless `--allow-extra-files`). (2) **Schema validation** — manifest against `policy/schemas/evidence_bundle_manifest.v0.1.schema.json`, each receipt against `policy/schemas/receipt.v0.1.schema.json`; if `fhir_bundle.json` exists, validate JSON and minimal Bundle structure (resourceType, type, entry). (3) **Hashchain proof** — `hashchain_proof.json` must match the last entry of `episode_log_subset.jsonl` (head_hash, length, last_event_hash). (4) **Invariant trace** — violations in `episode_log_subset` must be a superset of `invariant_eval_trace.jsonl` per step; mismatch fails with a diff by invariant_id.

**Output:** Short report (PASS/FAIL, file counts, first error). Exit code 0 on success, non-zero on failure.
