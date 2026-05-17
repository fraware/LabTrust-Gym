# PCS v0.1 release candidate fixtures

Synced from **pcs-core** `examples/labtrust-release/` (canonical RC chain).

```bash
export PCS_CORE_PATH=/path/to/pcs-core/python
python examples/pcs_qc_release/scripts/sync_release_from_pcs_core.py
python examples/pcs_qc_release/scripts/verify_release_handoff.py \
  --release examples/pcs_qc_release/release \
  --pcs-core ../pcs-core/examples/labtrust-release
```
