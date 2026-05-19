# lean_rejected_certificate

Lean obligations must fail when trace_certificate status is Rejected.

- Expected check: `lean_obligation.CertificateMatchesRuntime`
- Expected code: `LEAN_CERTIFICATE_REJECTED`
- Repair: see `repair_hint.json`
