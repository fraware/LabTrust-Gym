# Benchmark non-claims freeze (LTG-PR9)

**Authoritative limitation block** for LabTrust-Gym benchmark releases.
Release notes, candidate manifests, and credibility docs must reuse or cite
this block. Do not invent softer clinical or deployment-safety language.

## Freeze text (copy verbatim or link here)

LabTrust-Gym is a **simulation and research benchmark** for multi-agent
laboratory workflow, trust instrumentation, and verifier-assurance experiments.

It does **not**:

* Provide clinical validation of laboratory software or procedures
* Act as production laboratory control software
* Constitute medical-device certification, regulatory clearance, or deployment
  readiness evidence
* Convert passing golden / security / VA tests into real-world safety claims
* Authorize “scientifically reviewed” marketing language until independent
  domain approvals are signed and
  `scientifically_reviewed_claim_allowed` is true under
  [signed approval gate](../reviews/signed_approval_gate.md)
* Claim that unsigned review slots, hazard-matrix coverage, or sealed holdouts
  eliminate all benchmark leakage or clinical risk

Independent review (when completed) evaluates scenario framing, hazard coverage
honesty, and non-claims language only. It still does **not** clinically validate
LabTrust-Gym.

## Canonical related sources

| Source | Role |
|--------|------|
| This page | Single freeze block for **benchmark** release packaging (LTG-PR9) |
| [Scientific credibility non-goals](scientific_credibility.md#non-goals) | Program-level non-goals |
| [Verifier assurance non-claims](../verifier_assurance/non_claims.md) | LT-VA claim boundaries |
| [Paper claims](PAPER_CLAIMS.md) | Supported paper claims (no clinical claims) |
| [ADR-VA-002](../adr/ADR-VA-002-claim-boundaries.md) | VA claim-boundary ADR |

## Enforcement

* Candidate release notes under `benchmarks/releases/` must link this page and
  must **not** set or imply `scientifically_reviewed: true` while registry
  `scientifically_reviewed_claim_allowed` is false.
* `validate_independent_review_gate` / `assert_scientifically_reviewed_claim_allowed`
  remain fail-closed (see `labtrust_gym.policy.independent_review`).
* Do not mass-approve golden `governance.reviewer` fields as a substitute for
  signed domain reports.
