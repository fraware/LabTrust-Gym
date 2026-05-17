# PCS QC-release PF handoff

Provability Fabric must sign **only** the certified bundle in this directory.

Before `pf sign science-claim`, confirm:

1. `../pf_handoff.json` `certified_bundle_hash` matches the SHA-256 of `science_claim_bundle.certified.json` in this directory.
2. `handoff_for_pf.json` `expected_certificate_id` equals `science_claim_bundle.certified.json` → `certificates[0].certificate_id`.
3. `RELEASE_HANDOFF_MANIFEST.json` artifact digests match the files in this directory.

Run `python examples/pcs_qc_release/scripts/verify_release_handoff.py` from the LabTrust-Gym root before copying into pcs-core.

Example (from a sibling `provability-fabric` checkout):

```bash
HANDOFF=/path/to/LabTrust-Gym/examples/pcs_qc_release/release/handoff
cat "$HANDOFF/handoff_for_pf.json"
pf verify science-claim "$HANDOFF/science_claim_bundle.certified.json" --out verification_result.json
pf sign science-claim "$HANDOFF/science_claim_bundle.certified.json" --out signed_science_claim_bundle.json
```

Do not sign a certified bundle from another run or an older `release/` copy. Regenerate via `generate_release_candidate.sh` (atomic `release-run` staging, then promotion to `release/handoff/`).
