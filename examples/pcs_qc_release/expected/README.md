# LabTrust-local deterministic fixtures (`expected/`)

These files are **LabTrust-only** golden artifacts for CI and unit tests. They are generated with `PCS_DETERMINISTIC=1` and do **not** require CertifyEdge.

| File | Role |
|------|------|
| `valid_trace.json` | Hash-chained workflow trace |
| `valid_runtime_receipt.json` | `RuntimeReceipt.v0` |
| `valid_science_claim_bundle.pending.json` | Pending bundle (`runtime_receipts[]`, `certificates: []`) |
| `trace_certificate.mock.v0.json` | **Mock** certificate for `attach-certificate` tests only |
| `valid_science_claim_bundle.certified.json` | Certified bundle using the **mock** certificate above |
| `valid_trace_hash_alignment.json` | `trace_hash` handoff check |
| `invalid_*` | Invalid scenario traces, receipts, and result summaries |

**Not PCS v0.1 release evidence:** `trace_certificate.mock.v0.json` uses a fixed `DETERMINISTIC_CERT_DIGEST` stub. Cross-repo release candidates live under [`../release/`](../release/) and must be built with real CertifyEdge output.

Regenerate:

```bash
python examples/pcs_qc_release/scripts/generate_golden.py
```
