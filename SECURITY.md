# Security

Report security vulnerabilities responsibly: do not open a public issue. Contact the maintainers (or the security contact in the repository) with a description, steps to reproduce, and impact. We will acknowledge and work with you on a fix.

This project is a simulation and benchmark environment for R&D, not production medical or laboratory software. Trust skeleton issues (e.g. audit log, token verification) are in scope; deployment and operational security are the responsibility of integrators. Release artifacts are verified offline via `labtrust verify-release` (EvidenceBundles, risk register, RELEASE_MANIFEST hashes); use `--strict-fingerprints` for release validation. See [Trust verification](docs/risk-and-security/trust_verification.md).
