# Invariants

Invariants are defined in `policy/invariants/` (tokens, zones, critical results). They specify:

- **Triggers**: which events or conditions invoke the check.
- **Logic**: assertions (e.g. token active, co-location, ACK present).
- **Enforcement**: DENY_ACTION, BLOCK_ACTION, FORENSIC_FREEZE_LOG, etc.
- **Reason codes**: canonical code returned on violation.

The engine evaluates invariants at the appropriate hooks (e.g. pre_action_validate, post_action_log) and returns violations in the step result. The golden runner asserts expected violation tokens in scenario expectations.
