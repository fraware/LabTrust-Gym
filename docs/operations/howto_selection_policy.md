# How to tune the selection policy for your organization

The coordination selection policy decides which method is “best” per scale by applying hard constraints and an objective. You can tune it per organization via the base policy or a partner overlay.

## Where the policy lives

- **Base:** `policy/coordination/coordination_selection_policy.v0.1.yaml`
- **Partner overlay:** `policy/partners/<partner_id>/coordination/coordination_selection_policy.v0.1.yaml` (when using `--partner <partner_id>` on `build-lab-coordination-report` or `recommend-coordination-method`). If the overlay file exists, it is used instead of the base file.

## Main knobs

1. **constraints**  
   List of hard constraints. A method is **admissible** only if it passes all of them. Each constraint typically has:
   - `constraint_id`: short identifier
   - `metric_key`: e.g. `safety.violations_total`, `sec.attack_success_rate`, `cost.estimated_cost_usd`
   - `operator`: `<=`, `>=`, or `<`, `>`
   - `threshold`: numeric value
   - `aggregation`: `baseline_only`, `max_over_attacks`, or `mean_over_attacks` (how to take the value from the pack summary for that method/scale)

   Example: keep baseline violations under 10 and worst-case attack success rate under 0.2:
   ```yaml
   constraints:
     - constraint_id: violations_ceiling
       metric_key: safety.violations_total
       operator: "<="
       threshold: 10
       aggregation: baseline_only
     - constraint_id: attack_success_ceiling
       metric_key: sec.attack_success_rate
       operator: "<="
       threshold: 0.2
       aggregation: max_over_attacks
   ```

2. **objective**  
   How to rank admissible methods. Typically `type: maximize_overall_score`. The “overall score” is derived from the pack summary (e.g. resilience score when present, else throughput minus normalized violations). Other objective types may be added in future.

3. **per_scale_rules**  
   Optional overrides per scale (e.g. `medium_stress_signed_bus`). You can set a different `resilience_weight_override` or other parameters so that the same policy file behaves differently per scale.

## Tuning steps

1. Copy the base `coordination_selection_policy.v0.1.yaml` to your partner overlay if you use one: `policy/partners/<id>/coordination/coordination_selection_policy.v0.1.yaml`.
2. Adjust `constraints` (thresholds or aggregation) to match your org’s risk appetite. Relaxing a threshold (e.g. higher violation ceiling) may make more methods admissible; tightening it may make the decision “no admissible method” until methods improve.
3. Run the pack and report with the same policy: `labtrust run-coordination-security-pack --out <dir> ...`, then `labtrust build-lab-coordination-report --pack-dir <dir> [--partner <id>]`. Open `COORDINATION_DECISION.md` to see which method was chosen and which were disqualified and why.
4. Iterate: change thresholds or add constraints, re-run the report (no need to re-run the pack if you only changed selection policy), and check the decision again.

## See also

- [Forker guide – Coordination selection policy](../getting-started/forkers.md#coordination-selection-policy)
- [Coordination studies](../coordination/coordination_studies.md)
