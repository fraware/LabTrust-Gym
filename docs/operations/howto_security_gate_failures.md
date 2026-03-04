# How to interpret and act on a failed security or gate result

When the coordination security pack or the selection policy reports a failure, use this to interpret and fix it.

## Security gate failed (pack_gate.md has FAIL cells)

**What it means:** At least one cell (scale x method x injection) in the coordination security pack failed the rule defined for that injection in `policy/coordination/coordination_security_pack_gate.v0.1.yaml`. The coordination decision verdict is set to **security_gate_failed** and no method is recommended for deployment until the gate passes.

**How to interpret:**

1. Run `labtrust check-security-gate --run <pack_dir>`. It exits 1 and prints each failing cell (scale_id / method_id / injection_id).
2. Open `<pack_dir>/pack_gate.md` and find those cells; the **rationale** column explains why (e.g. `attack_success_rate=0.2 (expected 0)`, or `violations_total=12 > nominal+5=10`).
3. Open `<pack_dir>/SECURITY/coordination_risk_matrix.md` (or `.csv`) for the underlying metrics (attack_success_rate, detection_latency_steps, etc.).

**What to do:**

- **Fix the method or defenses:** Improve the coordination method or detector so the metric meets the rule (e.g. block the attack so attack_success_rate is 0, or reduce violations).
- **Or relax the gate rule (with approval):** Edit `coordination_security_pack_gate.v0.1.yaml` (e.g. increase `max_delta` for violations_within_delta, or change the rule for that injection). Document the rationale and get approval before deploying.
- Re-run the pack and report: `labtrust run-coordination-security-pack --out <dir> ...`, then `labtrust build-lab-coordination-report --pack-dir <dir>`, then `labtrust check-security-gate --run <dir>`. Do not treat the run as admissible until the gate passes.

## No admissible method (selection policy constraints)

**What it means:** Every method was disqualified by at least one hard constraint in the selection policy (e.g. violation ceiling, attack success rate ceiling, cost). The decision verdict is **no_admissible_method**.

**How to interpret:**

1. Open `COORDINATION_DECISION.md` or `COORDINATION_DECISION.v0.1.json`. The “Disqualified” section lists each method and the reason (e.g. `violations_ceiling: 15 > 10`).
2. The `no_admissible_method.violated_constraints` (in JSON) or “Violated constraints (sample)” (in MD) shows which constraint(s) and thresholds were missed.

**What to do:**

- **Improve methods:** Re-run with improved coordination methods or defenses so at least one method passes all constraints.
- **Relax constraints (with approval):** Edit `policy/coordination/coordination_selection_policy.v0.1.yaml` (or partner overlay) to loosen thresholds (e.g. higher violation ceiling, higher attack success rate ceiling). Re-run the report (same pack output is fine) and confirm one method becomes admissible.
- Use the “Recommended actions” in the decision (e.g. “Tighten defenses or add safe fallback for failing methods”) as a checklist.

## Both gate failed and no admissible method

If the pack has FAIL cells, the decision verdict is **security_gate_failed** and takes precedence. Fix the gate first (so no FAIL cells), then re-run the report. If the verdict becomes **no_admissible_method**, address constraints as above.

## See also

- [Troubleshooting](../getting-started/troubleshooting.md) – pack gate failures, no admissible method.
- [Forker guide – Security and safety gates](../getting-started/forkers.md#security-and-safety-gates)
- [Trust verification](../risk-and-security/trust_verification.md) and [CI](ci.md) – do not release with gate failed or broken E2E chain.
