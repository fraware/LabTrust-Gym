# Independent review protocol and checklist (LTG-PR8)

Step-by-step protocol for the three charter roles. Complete this before signing
a report. Unsigned slots under `benchmarks/reviews/slots/*.UNSIGNED.json` are
**not** approvals.

## Preconditions

1. Read [Reviewer charter](charter.md) (scope, non-goals, COI).
2. Read [Scientific credibility](../benchmarks/scientific_credibility.md) and
   [Verifier assurance non-claims](../verifier_assurance/non_claims.md).
3. Skim [Golden suite governance](../benchmarks/golden_suite_governance.md) and
   [Security attack suite](../risk-and-security/security_attack_suite.md)
   (evidence-contract section).
4. Optional technical smoke (does not substitute domain judgment):
   [Reviewer runbook](../operations/reviewer_runbook.md).

## Review axes

| Axis | Question |
|------|----------|
| Scenario framing | Are GS-* narratives and `governance.hazard` plausible as **simulation** hazards for the stated `coverage_class`? |
| Hazard coverage | Does the matrix list GS-*/SEC-* honestly? Are uncovered / partial classes called out with a non-empty `gap`? |
| Non-claims | Do linked docs avoid clinical validation, certification, and deployment-readiness claims? |

## Role focus

### Laboratory workflow expert

- Specimen identity, chain of custody, QC release, critical escalation, stability,
  multi-site handoff framing in golden scenarios.
- Flag any wording that implies a named hospital's SOPs or clinical ground truth.

### Safety or quality specialist

- Hazard matrix gaps vs marketing tone in docs.
- Attack-suite `evidence_contract` residual-risk and budget honesty
  (especially `requires_live_llm: false` on smoke paths).
- Confirm limitation language stays fail-closed.

### Multi-agent benchmark reviewer

- Whether leaderboard / pack narratives resist overclaim and leakage theater.
- Holdout / sealed-partition language (if present) is not sold as universal
  anti-leakage or real-world safety.
- Multi-agent evaluation norms: what is measured vs what is implied.

## Checklist (all roles)

Mark each item in the signed report's `findings_summary` or keep a private copy;
set `checklist_completed: true` only when all applicable items are done.

### A. Scenario framing

- [ ] Sampled at least one GS-* scenario per **covered** hazard class you are
      competent to judge (or documented sampling plan if reviewing a subset).
- [ ] `governance.coverage_class` matches the primary hazard described.
- [ ] No scenario text read as clinical validation of a real site.
- [ ] `governance.reviewer: pending-domain-review` is understood as **process
      pending**, not as an approval (see charter).

### B. Hazard coverage

- [ ] Inspected `policy/coverage/hazard_coverage_matrix.v0.1.yaml` for explicit
      gaps (e.g. uncovered classes).
- [ ] Agreed that clearing a gap requires honest fixtures, not invented coverage.
- [ ] SEC-* attack listing (where in scope for your role) does not overstate
      production security certification.

### C. Non-claims / limitations

- [ ] Confirmed [non_claims.md](../verifier_assurance/non_claims.md) and
      scientific credibility non-goals remain visible and consistent.
- [ ] Attestation will state that this review does **not** clinically validate
      the system.
- [ ] Will not authorize "scientifically reviewed" release language alone without
      the other two roles and the [signed approval gate](signed_approval_gate.md).

### D. COI and signature hygiene

- [ ] COI disclosed (or none stated) per charter.
- [ ] Will not ask maintainers to fabricate `signature_ref` or backdate
      `reviewed_at`.
- [ ] If blocking issues remain: set `approval.status` to `rejected` or
      `abstained`, not `approved`.

## Recording the outcome

1. Copy the unsigned slot for your `role_id` from `benchmarks/reviews/slots/`.
2. Fill scope fields (`reviewed_ok` / `reviewed_with_issues` / `blocked`).
3. Write `findings_summary`; keep `limitations_acknowledged` (extend if needed).
4. Only if approving: set `approval.status` to `approved`, `signed` to `true`,
   non-empty name/affiliation, ISO `reviewed_at`, real `signature_ref`,
   `conflicts_of_interest_disclosed: true`, and an attestation that cites this
   protocol.
5. Maintainers register the path per [signed approval gate](signed_approval_gate.md).

## Fail-closed reminders

- Empty or unsigned slots must never be described as completed reviews.
- Three unsigned slots ⇒ `scientifically_reviewed_claim_allowed` must stay
  `false`.
- Approval of framing and language ≠ clinical or deployment readiness.
