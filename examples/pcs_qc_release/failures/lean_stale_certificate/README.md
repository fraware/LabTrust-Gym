# lean_stale_certificate

Lean obligations must fail when trace_certificate status is Stale.

- Expected check: `lean_obligation.CertificateMatchesRuntime`
- Expected code: `LEAN_CERTIFICATE_STALE`
- Repair: see `repair_hint.json`
