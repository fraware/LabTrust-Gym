# Independent reviewer charter (LTG-PR8)

Charter for external independent review of LabTrust-Gym scenario framing, hazard
coverage honesty, and non-claims / limitation language. This charter authorizes
**process materials and review criteria only**. It does not authorize clinical
use, regulatory claims, or deployment.

## Purpose

Obtain independent judgment that:

1. Golden scenarios (GS-*) are **plausible as laboratory-workflow *simulations***
   for the stated hazard class (not that they mirror any named clinical site).
2. Hazard coverage in
   [`policy/coverage/hazard_coverage_matrix.v0.1.yaml`](../../policy/coverage/hazard_coverage_matrix.v0.1.yaml)
   and scenario `governance` metadata is **honest** (covered / partial / gap).
3. Public docs keep **fail-closed non-claims** about clinical validation and
   deployment readiness.

## Roles (recruit one of each)

| `role_id` | Title | Primary lens |
|-----------|-------|--------------|
| `laboratory_workflow_expert` | Laboratory workflow expert | Specimen flow, handoffs, QC/critical-path plausibility of GS-* framing |
| `safety_or_quality_specialist` | Safety or quality specialist | Hazard classes, residual risk wording, attack-suite evidence contracts vs overclaim |
| `multi_agent_benchmark_reviewer` | Multi-agent benchmark reviewer | Benchmark leakage resistance, leaderboard non-claims, multi-agent evaluation norms |

Recruitment is **out of band** (email, institutional contact). This repository
only holds invitation text, protocol, and unsigned report slots.

## In scope

- Scenario **framing** and `governance.hazard` / `coverage_class` alignment
- Explicit **gaps** in the hazard matrix (must remain visible; do not invent coverage)
- Limitation and **non-claims** language in linked docs
- Security attack suite **evidence-contract** honesty (budgets, residual risk) relative to claims docs
- Whether golden `governance.reviewer` should remain `pending-domain-review` or may later reference a real reviewer id after signed approval

## Out of scope / non-goals

Reviewers **must not** treat their approval as:

- Clinical validation of laboratory software or procedures
- Medical-device certification, accreditation, or regulatory clearance
- Permission to run LabTrust-Gym as production laboratory control software
- Proof that benchmark or security-suite pass rates imply real-world safety
- Endorsement of any partner site, vendor, or clinical protocol
- Completion of LTG-PR9 by itself (release still needs its own technical gates)

Related non-claims:
[Verifier assurance non-claims](../verifier_assurance/non_claims.md),
[Scientific credibility](../benchmarks/scientific_credibility.md).

## Conflict of interest (COI)

Before accepting:

1. Disclose employment, consulting, equity, or recent funding ties to LabTrust-Gym
   maintainers, primary authors, or commercial forks under review.
2. Disclose prior co-authorship on LabTrust-Gym papers or releases in the last
   36 months if that would reasonably appear to compromise independence.
3. Recuse from the role if independence cannot be maintained; the slot stays
   `unsigned` rather than recording a compromised approval.
4. On an **approved** report, set `approval.conflicts_of_interest_disclosed` to
   `true` and summarize material COIs in `findings_summary` (or state none).

Maintainers must not pressure reviewers to clear gaps by weakening expects or by
hiding uncovered hazard classes.

## Deliverable

A report JSON conforming to
`policy/schemas/independent_review_report.v1.schema.json`, stored under
`benchmarks/reviews/` and registered in
`benchmarks/reviews/review_registry.v1.json`. Unsigned templates exist so paths
are stable; **do not fabricate signatures**.

## Status of repository slots

Until real reviewers complete the protocol, every role report remains
`approval.status: unsigned` with `approval.signed: false`. Golden scenarios keep
`governance.reviewer: pending-domain-review` and point here for process context.
