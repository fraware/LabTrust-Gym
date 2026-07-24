# ADR-VA-002: Claim boundaries / non-clinical scope

- **Status:** Accepted (LT-VA-00)
- **Date:** 2026-07-24

## Context

LabTrust-Gym simulates blood-sciences laboratory workflows for research and benchmarking. Verifier-assurance campaigns can look like clinical validation artifacts if language is careless.

## Decision

Every VA document, CLI string, schema description, and release pack MUST state (or inherit via `docs/verifier_assurance/non_claims.md`) that:

1. Work is **simulation and research only**.
2. Results do **not** claim production clinical assurance, regulatory clearance, or clinical validation.
3. Partner calibration compares **approved de-identified aggregates only**; raw partner records never enter the public repo.
4. Causal / attribution graphs are a **declared experimental causal model**, not legal responsibility assignment.
5. Fail closed on unknown schema, missing artifact, unavailable checker, or leakage suspicion — never silent acceptance.

## Consequences

- Docs and release manifests carry explicit non-claims.
- Reviewers reject PRs that introduce production-assurance marketing language.
- VA schemas include a `claim_boundary` or reference field where portable evidence might be misread.

## Related

- `docs/verifier_assurance/non_claims.md`
- Threat model extension in `docs/architecture/threat_model.md`
