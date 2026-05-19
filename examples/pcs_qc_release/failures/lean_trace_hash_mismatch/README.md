# lean_trace_hash_mismatch

Lean CertificateMatchesRuntime fails when certificate trace_hash diverges from runtime receipt.

- Expected check: `lean_obligation.CertificateMatchesRuntime`
- Expected code: `LEAN_CERTIFICATE_TRACE_HASH_MISMATCH`
- Repair: see `repair_hint.json`
