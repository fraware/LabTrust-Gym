# Golden suite governance

Change control for `policy/golden/golden_scenarios.v0.1.yaml` and its link to the
hazard coverage matrix. This is the LTG-PR3 contract. It does **not** claim clinical
validation or deployment readiness.

## Sources of truth

| Artifact | Role |
|----------|------|
| `policy/golden/golden_scenarios.v0.1.yaml` | Scenario scripts + per-scenario `governance` metadata |
| `policy/schemas/golden_scenarios.v0.1.schema.json` | Structural schema (governance fields required) |
| `policy/coverage/hazard_coverage_matrix.v0.1.yaml` | Class-level GS-*/SEC-* map and **explicit gaps** |
| `labtrust validate-policy` | Schema validation + fail-closed coverage gate |

Related: [Scientific credibility](scientific_credibility.md), [Testing strategy](../reference/testing_strategy.md),
[Canonical state machine](../architecture/canonical_state_machine.md),
[Independent review charter](../reviews/charter.md).

## Required governance fields (every scenario)

Each scenario must record:

| Field | Location | Meaning |
|-------|----------|---------|
| `scenario_id` | scenario root | Stable GS-* id |
| `hazard` | `governance.hazard` | Short hazard framing (not a clinical claim) |
| `initial_state` | scenario root | Episode start state |
| `policy_version` | `governance.policy_version` | Suite/policy pack version pin |
| `action_sequence` | `governance.action_sequence` | Ordered `action_type` list; must match `script` |
| `expected_reason_codes` | `governance.expected_reason_codes` | Asserted blocked / last reason codes (may be empty) |
| `expected_terminal_state` | `governance.expected_terminal_state` | Inspectable terminal summary |
| `required_evidence` | `governance.required_evidence` | What must be present to accept coverage |
| `coverage_class` | `governance.coverage_class` | One of the 12 matrix hazard classes |
| `reviewer` | `governance.reviewer` | Domain reviewer id, or `pending-domain-review` until a signed independent review exists ([charter](../reviews/charter.md); do not mass-flip) |

Suite-level pointer: `golden_suite.governance` (`matrix_ref`, `policy_version`, `change_control_doc`).

## Coverage gate (fail-closed)

`validate_golden_hazard_coverage_gate` (also run from `validate_all_policy_schemas` /
`validate_golden_scenarios`) fails when:

1. A scenario lacks a valid `governance` object or required fields.
2. `governance.coverage_class` is not a known matrix class.
3. The scenario claims a class but its `scenario_id` is **not** listed in that class's
   `golden_scenario_ids` in the matrix.
4. `governance.action_sequence` does not equal `script[*].action_type` in order.
5. A matrix class has `coverage: uncovered` without a non-empty `gap`, or lists GS ids
   while uncovered.
6. The matrix lists a `golden_scenario_id` that does not exist in the suite.

Uncovered hazards (for example `catalog_drift`) **remain explicit gaps** in the matrix.
Do not invent scenarios to clear a gap without accurate fixtures and honest framing.

## How to add a scenario

1. Author the script under `golden_suite.scenarios` with deterministic `expect` blocks.
2. Add a `governance` block with all required fields. Set `coverage_class` to the
   **primary** hazard class. Set `reviewer` to `pending-domain-review` unless a
   **signed** independent-review report already names a reviewer
   ([charter](../reviews/charter.md), [signed approval gate](../reviews/signed_approval_gate.md)).
   Do not invent reviewer ids.
3. Update `policy/coverage/hazard_coverage_matrix.v0.1.yaml`: append the new `scenario_id`
   under that class's `golden_scenario_ids`. If the scenario also supports a secondary
   class (for example token + stability), list it under both; keep one primary on the
   scenario.
4. If the hazard class was `uncovered` / `partially_covered`, update `coverage`, `gap`,
   and `notes` honestly. Prefer documenting a remaining gap over overstating coverage.
5. Bump `EXPECTED_GOLDEN_SCENARIO_COUNT` in `tests/test_docs_truthfulness.py` if the
   count changes.
6. Run focused checks (default CI; no need for full env golden unless behavior changed):

```bash
labtrust validate-policy
pytest -q tests/test_policy_validation.py tests/test_golden_governance.py tests/test_independent_review_gate.py
```

7. Full golden env suite remains gated by `LABTRUST_RUN_GOLDEN=1` / `@pytest.mark.slow`.

## Gap policy

- **Uncovered class:** empty `golden_scenario_ids`, non-empty `gap` string, `coverage: uncovered`.
- **Partial class:** list what exists; keep an honest `gap` for what is missing.
- **Do not** clear `catalog_drift` (or similar) by inventing clinical catalogue-drift claims.
- **Do not** weaken existing scenario expects to make a new scenario pass.
- Domain reviewers (LTG-PR8) approve hazard framing and limitation language via
  [independent review](../reviews/README.md); until signed reports exist,
  `reviewer: pending-domain-review` is required and visible. Process materials do
  **not** clinically validate the suite.

## Non-claims

Passing golden scenarios demonstrates **in-engine** regression against the suite
specification. It does not demonstrate clinical safety, regulatory fitness, or real-world
deployment readiness. See [Scientific credibility](scientific_credibility.md) and
[Paper claims](PAPER_CLAIMS.md).
