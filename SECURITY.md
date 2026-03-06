# Security

Report security vulnerabilities responsibly: do not open a public issue. Please report via one of the following:

- **Preferred:** Open a private security advisory at [https://github.com/fraware/LabTrust-Gym/security/advisories/new](https://github.com/fraware/LabTrust-Gym/security/advisories/new).
- Alternatively, contact the repository maintainers with a description, steps to reproduce, and impact.

We will acknowledge and work with you on a fix.

This project is a simulation and benchmark environment for R&D, not production medical or laboratory software. Trust skeleton issues (e.g. audit log, token verification) are in scope; deployment and operational security are the responsibility of integrators. Release artifacts are verified offline via `labtrust verify-release` (EvidenceBundles, risk register, RELEASE_MANIFEST hashes); use `--strict-fingerprints` for release validation. See [Trust verification](docs/risk-and-security/trust_verification.md).
