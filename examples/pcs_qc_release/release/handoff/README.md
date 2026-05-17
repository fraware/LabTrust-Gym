# PCS QC-release PF handoff

Provability Fabric must sign **only** the certified bundle in this directory.

Confirm `../pf_handoff.json` `certified_bundle_hash` matches `science_claim_bundle.certified.json` before signing.

```bash
python examples/pcs_qc_release/scripts/verify_release_handoff.py
```
