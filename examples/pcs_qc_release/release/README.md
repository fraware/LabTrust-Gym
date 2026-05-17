# PCS v0.1 release candidate fixtures

These files are synchronized from the canonical chain in **pcs-core**:

`pcs-core/examples/labtrust-release/`

Do not edit individual artifacts here. Regenerate the full cross-repo chain in pcs-core, then sync:

```bash
export PCS_CORE_PATH=/path/to/pcs-core/python
python examples/pcs_qc_release/scripts/sync_release_from_pcs_core.py
python examples/pcs_qc_release/scripts/verify_release_handoff.py
pytest tests/pcs/test_labtrust_release_fixtures_match_pcs_core_rc.py -q
```

PF signing input: `handoff/science_claim_bundle.certified.json` and `pf_handoff.json`.
