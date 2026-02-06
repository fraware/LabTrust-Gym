# Safety case (auto-generated)

Claim -> control -> test(s) -> artifact(s) -> verification command.
Source: policy/safety_case/claims.v0.1.yaml

---

## SC-CONTRACT-001

**Statement:** Step output satisfies runner output contract (status, emits, violations, hashchain).

**Controls:**
- Runner output schema enforcement
- Golden runner validates contract

**Tests:**
- `tests.test_golden_suite`
- `tests.test_metamorphic_properties`

**Artifacts:**
- policy/schemas/runner_output_contract.v0.1.schema.json
- SAFETY_CASE/safety_case.json

**Verification commands:**
- `pytest tests/test_golden_suite.py -q`
- `pytest tests/test_metamorphic_properties.py -q`

---

## SC-DETERMINISM-001

**Statement:** Same seed yields identical step outcomes (determinism).

**Controls:**
- Single RNG wrapper seeded per episode
- No ambient randomness in step

**Tests:**
- `tests.test_metamorphic_properties`
- `tests.test_failure_models_deterministic`

**Artifacts:**
- _repr/
- SAFETY_CASE/safety_case.md

**Verification commands:**
- `pytest tests/test_metamorphic_properties.py -q`
- `pytest tests/test_failure_models_deterministic.py -q`

---

## SC-SECURITY-001

**Statement:** Security attack suite scenarios are blocked or detected as expected.

**Controls:**
- CTRL-LLM-SHIELD
- CTRL-RBAC
- CTRL-TOOL-SANDBOX
- CTRL-COORD-IDENTITY

**Tests:**
- `tests.test_security_attack_suite`
- `tests.test_securitization`

**Artifacts:**
- SECURITY/attack_results.json
- SECURITY/coverage.json
- SECURITY/coverage.md

**Verification commands:**
- `labtrust run-security-suite --out <dir> --smoke --seed 42`
- `pytest tests/test_security_attack_suite.py tests/test_securitization.py -q`

---

## SC-POLICY-001

**Statement:** All policy files validate against their JSON schemas.

**Controls:**
- validate-policy before release

**Tests:**
- `tests.test_policy_validation`

**Artifacts:**
- policy/schemas/

**Verification commands:**
- `labtrust validate-policy`

---

## SC-FAILURE-PHYSICS-001

**Statement:** Maintenance windows block START_RUN with RC_DEVICE_MAINT; reagent stockout blocks with RC_REAGENT_STOCKOUT.

**Controls:**
- failure_models.v0.1 maintenance_schedule
- reagent_policy.v0.1 panel_requirements

**Tests:**
- `tests.test_failure_models_deterministic`

**Artifacts:**
- policy/equipment/failure_models.v0.1.yaml
- policy/reagents/reagent_policy.v0.1.yaml

**Verification commands:**
- `pytest tests/test_failure_models_deterministic.py -q`

---

## SC-PAPER-ARTIFACT-001

**Statement:** Paper v0.1 artifact is self-contained and includes SECURITY, receipts, TABLES, FIGURES, SAFETY_CASE.

**Controls:**
- package-release paper_v0.1 pipeline

**Tests:**
- `tests.test_package_release`

**Artifacts:**
- SECURITY/
- receipts/
- TABLES/
- FIGURES/
- SAFETY_CASE/
- RELEASE_NOTES.md

**Verification commands:**
- `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`

---
