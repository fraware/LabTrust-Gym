# Evidence bundle verification

`labtrust verify-bundle` checks an **EvidenceBundle.v0.1** directory for integrity, schema validity, hashchain proof, and invariant trace. Optional policy fingerprints (tool registry, RBAC, coordination identity, memory) are validated when present in the manifest.

## What to pass to `--bundle`

The `--bundle` argument must be the path to a **single EvidenceBundle.v0.1** directory (a folder that contains `manifest.json`), not the release root.

- **Correct:** A path under `receipts/`, e.g. `release/receipts/taska_cond_0/EvidenceBundle.v0.1`.
- **Incorrect:** The release directory that contains `MANIFEST.v0.1.json` and `receipts/`. Passing the release root will fail with a missing-manifest or invalid-structure error.

To verify **every** EvidenceBundle in a release in one go, use:

```bash
labtrust verify-release --release-dir <path>
```

That command discovers all `receipts/*/EvidenceBundle.v0.1` under the release directory and runs the same checks as verify-bundle on each. See [Release checklist](release_checklist.md) and [Troubleshooting](troubleshooting.md).

## What is checked

- **Manifest integrity** — File list and SHA-256 hashes match the bundle contents.
- **Schema** — Manifest and receipt files validate against `policy/schemas/evidence_bundle_manifest.v0.1.schema.json` and `receipt.v0.1.schema.json`.
- **Hashchain proof** — Append-only chain is consistent; no break.
- **Invariant trace** — Present and valid when required.
- **Optional policy fingerprints** (when present in manifest): `tool_registry_fingerprint`, `rbac_policy_fingerprint`, `coordination_policy_fingerprint`, `memory_policy_fingerprint` are recomputed from the corresponding policy files and must match.

Bundles that do not include these optional keys are unchanged; when receipts or manifests add them, verify-bundle validates them.

## See also

- [FHIR R4 export](fhir_export.md) — Export from receipts/EvidenceBundle.
- [Security attack suite](security_attack_suite.md) — Verification and fingerprints in context of the security suite.
