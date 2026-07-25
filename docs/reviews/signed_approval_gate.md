# Signed approval gate (LTG-PR8 → LTG-PR9)

How independent-review approvals gate calling a LabTrust-Gym benchmark release
**scientifically reviewed**. Fail-closed: missing or unsigned reports never
count as approval. Independent review still does **not** clinically validate
the simulator.

## Artifacts

| Artifact | Path |
|----------|------|
| Registry | `benchmarks/reviews/review_registry.v1.json` |
| Role slots (current: unsigned) | `benchmarks/reviews/slots/*.UNSIGNED.json` |
| Report schema | `policy/schemas/independent_review_report.v1.schema.json` |
| Registry schema | `policy/schemas/independent_review_registry.v1.schema.json` |
| Process docs | `docs/reviews/` (this tree) |

## CI / validate-policy behavior

`labtrust validate-policy` runs `validate_independent_review_gate`:

1. Required process docs exist under `docs/reviews/`.
2. Registry and each `report_path` exist and validate against schemas.
3. Each required `role_id` appears exactly once.
4. **Unsigned consistency:** if `approval.status` is `unsigned`, then
   `approval.signed` must be `false`, identity/`signature_ref` empty or null,
   and scope axes remain `not_reviewed`.
5. **Approved consistency:** if `approval.status` is `approved`, then
   `signed` must be `true`, name/affiliation/`reviewed_at`/`signature_ref`
   present, `conflicts_of_interest_disclosed` true, checklist completed, and
   limitations must acknowledge non-clinical-validation.
6. **Claim flag:** `scientifically_reviewed_claim_allowed` may be `true` only
   when all three roles are `approved` under the rules above. Otherwise it must
   be `false`. Inventing `true` fails the gate.

Default CI therefore **passes** with three UNSIGNED slots and
`scientifically_reviewed_claim_allowed: false`. It **fails** if someone claims
scientific review without signed reports.

## How LTG-PR9 consumes approvals

LTG-PR9 (benchmark release) may use the phrase **scientifically reviewed** in
release notes or pack metadata **only if**:

1. All three role reports are `approved` and signed (real `signature_ref`; no
   fabricated signatures).
2. Registry `scientifically_reviewed_claim_allowed` is `true` and
   `validate_independent_review_gate` returns no errors.
3. Technical release gates for PR9 (packs, verify-release, etc.) also pass.
4. Release text still links non-claims: review ≠ clinical validation ≠
   deployment readiness.

Recommended release checklist items (for PR9 authors):

```text
[ ] Engineering candidate packaging green (DoD smoke / release runbook)
[ ] Release notes cite docs/benchmarks/non_claims_freeze.md; no clinical claims
[ ] scientifically_reviewed_claim_allowed remains false until all three roles approved
[ ] Only after signed approvals: scientifically_reviewed_claim_allowed == true
    (labtrust validate-policy clean; three approved reports under benchmarks/reviews/)
```

Until approvals land, ship as an **engineering benchmark** only
([release runbook](../benchmarks/release_runbook.md)).

Helper for strict consumption (e.g. release scripts):

```python
from labtrust_gym.policy.independent_review import (
    assert_scientifically_reviewed_claim_allowed,
)

assert_scientifically_reviewed_claim_allowed(repo_root)  # raises if not allowed
```

## Replacing an unsigned slot

1. Do **not** edit an UNSIGNED file in place to pretend a signature exists.
2. Add a new report path, e.g.
   `benchmarks/reviews/slots/laboratory_workflow_expert.approved.json`
   (name is conventional; path must be registered).
3. Point that role's `report_path` in the registry at the new file.
4. Keep other roles unsigned until their reviewers finish.
5. Set `scientifically_reviewed_claim_allowed` to `true` only when all three are
   approved and the gate is green.
6. Optionally update individual golden `governance.reviewer` from
   `pending-domain-review` to a real reviewer id **only** after that role's
   signed report exists — do not mass-flip scenarios in PR8.

## Forbidden

- Fabricating `signature_ref`, reviewer names, or backdated `reviewed_at`
- Setting `scientifically_reviewed_claim_allowed: true` with any unsigned role
- Implying clinical validation in attestation or release notes
- Treating risk-register reviewer smoke
  ([reviewer_runbook](../operations/reviewer_runbook.md)) as domain approval
