# Safety case (auto-generated)

Claim -> control -> reproduce command (primary) -> artifact. Tests are supporting (what the command runs).
Source: policy/safety_case/claims.v0.1.yaml

---

## SC-CONTRACT-001

**Statement:** Step output satisfies runner output contract (status, emits, violations, hashchain).

**Controls:**
- Runner output schema enforcement
- Golden runner validates contract

**Reproduce (primary):**
- `pytest tests/test_golden_suite.py -q`
- `pytest tests/test_metamorphic_properties.py -q`

**Supporting tests:**
- `tests.test_golden_suite`
- `tests.test_metamorphic_properties`

**Artifacts:**
- policy/schemas/runner_output_contract.v0.1.schema.json
- SAFETY_CASE/safety_case.json

---

## SC-DETERMINISM-001

**Statement:** Same seed yields identical step outcomes (determinism).

**Controls:**
- Single RNG wrapper seeded per episode
- No ambient randomness in step

**Reproduce (primary):**
- `pytest tests/test_metamorphic_properties.py -q`
- `pytest tests/test_failure_models_deterministic.py -q`

**Supporting tests:**
- `tests.test_metamorphic_properties`
- `tests.test_failure_models_deterministic`

**Artifacts:**
- _repr/
- SAFETY_CASE/safety_case.md

---

## SC-SECURITY-001

**Statement:** Security attack suite scenarios are blocked or detected as expected.

**Controls:**
- CTRL-LLM-SHIELD
- CTRL-RBAC
- CTRL-TOOL-SANDBOX
- CTRL-COORD-IDENTITY
- CTRL-DETECTOR-ADVISOR

**Reproduce (primary):**
- `labtrust run-security-suite --out <dir> --smoke --seed 42`
- `pytest tests/test_security_attack_suite.py tests/test_securitization.py -q`

**Supporting tests:**
- `tests.test_security_attack_suite`
- `tests.test_securitization`

**Artifacts:**
- SECURITY/attack_results.json
- SECURITY/coverage.json
- SECURITY/coverage.md

---

## SC-SECURITY-002

**Statement:** All in-scope coordination methods are stress-tested against the coordination injection set (and optional application phases). Evidence is pack_summary.csv and pack_gate.md from run-coordination-security-pack with full method list; optionally SECURITY/coordination_risk_matrix.csv.

**Controls:**
- Coordination security pack (scale x method x injection matrix)

**Reproduce (primary):**
- `labtrust run-coordination-security-pack --out <dir> --methods-from full --injections-from policy`

**Supporting tests:**
- `tests.test_security_coverage_gate::test_coordination_pack_full_method_list_non_empty`
- `tests.test_security_coverage_gate::test_coordination_pack_full_method_list_used`

**Artifacts:**
- pack_summary.csv
- pack_gate.md
- SECURITY/coordination_risk_matrix.csv

---

## SC-POLICY-001

**Statement:** All policy files validate against their JSON schemas.

**Controls:**
- validate-policy before release

**Reproduce (primary):**
- `labtrust validate-policy`

**Supporting tests:**
- `tests.test_policy_validation`

**Artifacts:**
- policy/schemas/

---

## SC-FAILURE-PHYSICS-001

**Statement:** Maintenance windows block START_RUN with RC_DEVICE_MAINT; reagent stockout blocks with RC_REAGENT_STOCKOUT.

**Controls:**
- failure_models.v0.1 maintenance_schedule
- reagent_policy.v0.1 panel_requirements

**Reproduce (primary):**
- `pytest tests/test_failure_models_deterministic.py -q`

**Supporting tests:**
- `tests.test_failure_models_deterministic`

**Artifacts:**
- policy/equipment/failure_models.v0.1.yaml
- policy/reagents/reagent_policy.v0.1.yaml

---

## SC-PAPER-ARTIFACT-001

**Statement:** Paper v0.1 artifact is self-contained and includes SECURITY, receipts, TABLES, FIGURES, SAFETY_CASE.

**Controls:**
- package-release paper_v0.1 pipeline

**Reproduce (primary):**
- `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`

**Supporting tests:**
- `tests.test_package_release`

**Artifacts:**
- SECURITY/
- receipts/
- TABLES/
- FIGURES/
- SAFETY_CASE/
- RELEASE_NOTES.md

---
