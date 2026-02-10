# How to add a new risk injection

Add a new risk injection so it can be used in the coordination security pack and study matrix.

## 1. Injection registry

Register the injection in `src/labtrust_gym/security/risk_injections.py` (e.g. `INJECTION_REGISTRY` or the equivalent mapping). The injection must have a unique ID (e.g. `INJ-MY-RISK-001`) and a callable or config that the runner uses to apply the injection (e.g. at a given step or phase). See existing entries for the expected shape (e.g. intensity, application_phase, seed_offset).

## 2. Policy (injections and gate)

- **Injections list:** Add the injection to `policy/coordination/injections.v0.2.yaml` (or the file referenced by the pack/study) so it appears in the “injections” list with `injection_id`, optional `intensity`, `application_phase`, etc. The pack and study runner use this to know which injections to run.
- **Gate rule (optional):** If the pack should evaluate a pass/fail rule for this injection, add a rule in `policy/coordination/coordination_security_pack_gate.v0.1.yaml` under `rules` with `injection_id` and `rule` (e.g. `attack_success_rate_zero`, `violations_within_delta`, or `detection_within_steps_or_not_supported`) and any parameters (e.g. `max_delta`, `max_detection_steps`). Without a rule, the cell verdict defaults to PASS.

## 3. Risk-to-injection mapping

If the injection corresponds to a risk in the risk register, ensure `policy/coordination/risk_to_injection_map.v0.1.yaml` (or equivalent) maps the risk ID to this injection ID so coverage and evidence link correctly.

## 4. Tests

Add or extend tests in `tests/test_risk_injections_deterministic.py` (or similar) so the new injection is applied in a controlled scenario and expected outcomes are asserted. Run the coordination security pack with a small matrix that includes the new injection to confirm the pack runs and gate (if defined) behaves as expected.

After adding the injection, run `labtrust validate-policy` and the risk-injection tests; then run the pack with `--injections-from policy` (or a path that includes the new injection) to verify end-to-end.
