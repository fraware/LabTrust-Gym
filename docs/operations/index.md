# Operations

CI, release, runbook, and how-to guides.

## CI and release

| Document | Description |
|----------|-------------|
| [CI](ci.md) | CI jobs, test matrix, gates (including PCS workflow). |
| [Releasing](releasing.md) | PyPI Trusted Publishing, pre-flight checklist, GitHub Release assets. |
| [PCS operator runbook](../examples/pcs_qc_release-operator.md) | QC-release reference workflow: setup, exports, release verification. |
| [PCS overview](../pcs/index.md) | Proof-carrying science hub and release checklist. |
| [Ops runbook](ops_runbook.md) | Operator runbook. |

## Operators and stakeholders

| Document | Description |
|----------|-------------|
| [Operator's summary](operators_summary.md) | One page on what the simulation proves, scope limits, and a minimal production checklist (links to threat model and policy pack). |
| [Reviewer runbook](reviewer_runbook.md) | One command sequence, expected artifacts (including coordination SOTA leaderboards and graphs in UI bundle), and how to interpret risk register and security gate for auditors and reviewers. Links LTG-PR8 independent domain-review materials (distinct from risk-register smoke). |
| [Independent review (LTG-PR8)](../reviews/README.md) | Charter, invitation, protocol, unsigned approval slots, signed-approval gate for LTG-PR9. |
| [Production runbook](production_runbook.md) | Config, key management, monitoring, rollback, and threat model scope for production deployment. |

## How-to guides

| Document | Description |
|----------|-------------|
| [Add coordination method](howto_add_coordination_method.md) | Register and implement a new coordination method. |
| [Add risk injection](howto_add_injection.md) | Add a risk injection. |
| [Tune selection policy](howto_selection_policy.md) | Tune coordination selection policy. |
| [Security and gate failures](howto_security_gate_failures.md) | Interpret security and gate failures. |
