# Independent review invitation template (LTG-PR8)

Copy, fill bracketed fields, and send out of band. Do not invent acceptances or
signatures in the repository.

---

**Subject:** Invitation to independently review LabTrust-Gym scenario framing
(LTG-PR8) — [ROLE_TITLE]

Dear [REVIEWER_NAME],

We invite you to serve as an **independent reviewer** for LabTrust-Gym, an open
multi-agent **simulation and research benchmark** for hospital laboratory
workflow and trust controls (not a clinical product).

**Role:** [ROLE_TITLE]
(`role_id`: `[laboratory_workflow_expert | safety_or_quality_specialist | multi_agent_benchmark_reviewer]`)

### What we ask you to review

1. **Scenario plausibility** — whether golden GS-* scenarios are reasonable as
   *simulated* laboratory-workflow hazards (not site-specific clinical truth).
2. **Hazard coverage honesty** — whether the hazard matrix and governance
   metadata state coverage and gaps without overclaim.
3. **Non-claims / limitations** — whether docs remain fail-closed on clinical
   validation and deployment readiness.

Charter: `docs/reviews/charter.md`
Protocol and checklist: `docs/reviews/protocol_and_checklist.md`
Non-claims: `docs/verifier_assurance/non_claims.md`,
`docs/benchmarks/scientific_credibility.md`
Golden governance: `docs/benchmarks/golden_suite_governance.md`
Attack suite (evidence contracts): `docs/risk-and-security/security_attack_suite.md`

### What this review is not

Your review does **not** clinically validate LabTrust-Gym, certify laboratory
software, clear a medical device, or authorize production deployment. Passing
benchmark or security tests remains in-engine evidence only.

### Conflict of interest

Please disclose relevant affiliations per the charter before accepting. If you
cannot review independently, decline and we will keep the role slot unsigned.

### Deliverable and timeline

- Complete the checklist in `docs/reviews/protocol_and_checklist.md`
- Return a report matching `policy/schemas/independent_review_report.v1.schema.json`
  (we can supply a filled draft from the unsigned slot under
  `benchmarks/reviews/slots/`)
- Suggested window: [DEADLINE / N weeks]
- Contact: [MAINTAINER_EMAIL]

Repo: [REPO_URL]

Thank you for considering this. We will not record an approval in-tree until you
provide an explicit signed report.

Sincerely,
[MAINTAINER_NAME]
[AFFILIATION]

---

## Maintainer notes (do not send)

- Recruitment is out of band; do not commit fake signed JSON.
- After a real approval, follow `docs/reviews/signed_approval_gate.md` before any
  "scientifically reviewed" language in LTG-PR9.
- Leave other unsigned slots unchanged until their reviewers complete.
