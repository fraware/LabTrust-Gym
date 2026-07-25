# Independent review artifacts (LTG-PR8)

Release-facing slots and registry for independent domain review. Process docs live
under [`docs/reviews/`](../../docs/reviews/README.md).

## Status

**No reviews are completed.** All three role slots are `UNSIGNED`. The registry flag
`scientifically_reviewed_claim_allowed` is `false`.

Do **not** describe LabTrust-Gym, a benchmark pack, or a release as
"scientifically reviewed" until signed reports replace these slots per
[Signed approval gate](../../docs/reviews/signed_approval_gate.md).

Independent review does **not** clinically validate the simulator or authorize
deployment.

## Layout

| Path | Role |
|------|------|
| `review_registry.v1.json` | Required roles, report paths, claim-allowed flag |
| `slots/*.UNSIGNED.json` | Reserved unsigned report templates (no signatures) |

Schemas: `policy/schemas/independent_review_registry.v1.schema.json`,
`policy/schemas/independent_review_report.v1.schema.json`.

## How LTG-PR9 consumes this

1. Maintainers recruit reviewers out of band using
   [`docs/reviews/invitation_template.md`](../../docs/reviews/invitation_template.md).
2. Reviewers complete
   [`docs/reviews/protocol_and_checklist.md`](../../docs/reviews/protocol_and_checklist.md).
3. Signed reports replace `*.UNSIGNED.json` paths; registry paths and
   `scientifically_reviewed_claim_allowed` update only when the gate passes.
4. LTG-PR9 may label a release "scientifically reviewed" **only** when
   `labtrust validate-policy` / `validate_independent_review_gate` accepts
   `scientifically_reviewed_claim_allowed: true` with three approved, signed reports.

Related: [Scientific credibility](../../docs/benchmarks/scientific_credibility.md),
[Reviewer charter](../../docs/reviews/charter.md).
