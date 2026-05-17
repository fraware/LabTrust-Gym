# PCS v0.1.0-rc1 release fixtures (LabTrust)

This directory mirrors the **canonical** PCS v0.1 release-candidate chain published in
[pcs-core](https://github.com/SentinelOps-CI/pcs-core) at `examples/labtrust-release/`.

It is **release evidence** for the trust loop:

LabTrust-Gym → RuntimeReceipt.v0 → CertifyEdge TraceCertificate.v0 → ScienceClaimBundle.v0 →
Provability Fabric VerificationResult.v0 → SignedScienceClaimBundle.v0 → Scientific Memory.

## Do not edit files here by hand

Individual artifacts must not be regenerated or patched in isolation. That breaks hash linkage,
certificate ID propagation, and cross-repo provenance.

Either:

1. **Sync from pcs-core** after the full atomic chain is regenerated there:

   ```bash
   export PCS_CORE_PATH=/path/to/pcs-core/python
   python -m labtrust_gym.pcs.sync_pcs_core_rc --pcs-core ../pcs-core/examples/labtrust-release
   ```

2. **Regenerate the entire chain** (LabTrust → CertifyEdge → PF → Scientific Memory) and promote
   atomically via `examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh` with
   `PCS_COPY_TO_RELEASE=1`, then sync to pcs-core and back.

## Verify against canonical RC (CI gate)

```bash
python -m labtrust_gym.pcs.sync_pcs_core_rc \
  --verify-only \
  --pcs-core ../pcs-core/examples/labtrust-release
```

This checks artifact hashes, commits, `pf_handoff.json` alignment, certificate/trace hash linkage,
and rejects mock certificates or placeholder `source_commit` values.

## PF signing

Use `handoff/science_claim_bundle.certified.json` and confirm `pf_handoff.json` before
`pf sign science-claim`.
