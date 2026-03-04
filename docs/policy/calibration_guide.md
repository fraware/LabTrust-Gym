# Calibration guide

Short reference for sites that need to align the simulation with local standards: what to tune, where in policy, and how to validate.

## What to tune

- **Critical thresholds:** Escalation tiers, max_ack_wait_s, required_fields, requires_readback. Affects when critical results trigger acknowledgment and escalation. Reference defaults are RCPath 2017 style; not clinically validated.
- **Stability and temperature rules:** Panel stability windows and temperature excursion handling. Affects when specimens are held or rejected for stability/temp.
- **Equipment:** Device types and instances, cycle times, capacity. Affects simulated device service times and queue behavior (e.g. in simulated timing mode).
- **Enforcement map:** Match invariant/severity/scope to throttle, kill_switch, freeze_zone, forensic_freeze; escalation tiers. Affects how violations are handled (e.g. throttle vs kill_switch).
- **Coordination selection policy:** Weights and constraints for choosing coordination methods (e.g. attack_success_rate_cap, violation_rate_gate). Optional constraint_overrides per method.
- **Resilience scoring (optional):** Weights and missing_metric_behavior for the composite resilience score in coordination studies. Used in pack summaries and Pareto reports.

## Where in policy

| Area | Policy path(s) | Partner overlay |
|------|----------------|-----------------|
| Critical thresholds | `policy/critical/critical_thresholds.v0.1.yaml` | `policy/partners/<partner_id>/critical/` |
| Escalation ladder | `policy/critical/` (escalation_ladder v0.2) | `policy/partners/<partner_id>/critical/` |
| Stability / temperature | `policy/stability/` | `policy/partners/<partner_id>/stability/` |
| Equipment | `policy/equipment/` (equipment_registry, etc.) | `policy/partners/<partner_id>/equipment/` |
| Enforcement map | `policy/enforcement/` | `policy/partners/<partner_id>/enforcement/` |
| Coordination selection | `policy/coordination/coordination_selection_policy.v0.1.yaml` | Via partner or LABTRUST_POLICY_DIR |
| Resilience scoring | `policy/coordination/resilience_scoring.v0.1.yaml` | Via partner or LABTRUST_POLICY_DIR |

Partner overlay layout: put overrides under `policy/partners/<partner_id>/` with the same subtree names (critical/, stability/, equipment/, enforcement/). Merge rules: see [Policy pack](policy_pack.md#partner-overlays). To use a fully custom policy tree (no repo), set `LABTRUST_POLICY_DIR` to the directory that contains `emits/`, `schemas/`, `critical/`, etc.; that directory is the policy root used by the loader.

## How to validate

1. **Schema and structure:** Run `labtrust validate-policy`. Use `labtrust validate-policy --partner <partner_id>` when using a partner overlay. Fix any schema or path errors before running benchmarks.
2. **Sanity run:** Run `labtrust quick-eval --seed 42` (or a small benchmark) and inspect metrics (throughput, violations, blocks). Confirm behavior matches expectations for your calibrated thresholds.
3. **Regression and golden (optional):** If you have golden outputs or regression tests (e.g. scripted baseline regression), run them after calibration changes to ensure you did not break existing contracts.

See [Policy pack](policy_pack.md) for production calibration (critical thresholds) and partner overlays. See [Operator's summary](../operations/operators_summary.md) and [Production runbook](../operations/production_runbook.md) for the broader production checklist.
