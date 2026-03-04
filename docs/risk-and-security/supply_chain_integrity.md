# Optional integrity and supply-chain hardening

For high-assurance or regulated environments, this document describes optional integrity checks beyond the default threat model: artifact signing, policy checksums, and TEE or out-of-band verification.

The [Threat model](../architecture/threat_model.md) states that the benchmark runner, policy loaders, and process are **trusted** and that supply-chain attacks and compromised runner are **out of scope**. Integrators who need stronger guarantees can use the mechanisms below.

## Artifact signing

Evidence bundles (receipts and manifest) can be signed with **Ed25519**. When `sign_bundle=True` and the runner supplies a key registry and `get_private_key(key_id)` callback, the manifest and each receipt are signed. Signature format: `{"algorithm": "ed25519", "public_key_b64": ..., "signature_b64": ..., "key_id": ...}`. The `labtrust verify-bundle` command verifies signatures when the key registry is present under the policy root; tampering with signed content causes verification to fail. Key custody and storage are the integrator’s responsibility; the core export does not read keys from disk. See [Enforcement](../policy/enforcement.md) (Evidence bundle signing and verification).

## Policy checksums

- **policy_pack_manifest:** When exporting receipts with a policy root and partner ID, the export can write `policy_pack_manifest.v0.1.json` (list of effective policy files with SHA-256) and set `policy_root_hash` on the manifest. This ties the run to the exact policy set and supports reproducibility.
- **verify-release:** The release verification chain (`build-release-manifest`, `verify-release`) checks that manifest and receipts are consistent and that policy fingerprints match where required. Use for release artifacts and evidence bundles produced by `package-release`.

## TEE and out-of-band verification

The codebase has **no built-in TEE** (Trusted Execution Environment) support. For high-assurance deployments, integrators may:

- Run critical components (e.g. runner, policy loader, or signing step) inside a TEE and attest to the environment.
- Use out-of-band verification of artifacts and runner binary (e.g. verify hashes or signatures of the deployed package and policy bundle against a trusted source).

These are deployment and operations responsibilities, not part of the core simulation or CLI.

## See also

- [Threat model](../architecture/threat_model.md) — Trust boundary and out of scope.
- [Enforcement](../policy/enforcement.md) — Signing and verification of evidence bundles.
- [Production runbook](../operations/production_runbook.md) — Key management and threat model scope.
