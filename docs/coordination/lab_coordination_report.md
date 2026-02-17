# Lab coordination report

This document describes the **canonical flow for hospital lab** coordination evaluation: run the security pack matrix, aggregate results, choose the optimal method per scale, and produce a single lab report bundle.

## Canonical flow

1. **Run matrix**  
   Run the coordination security pack with a lab-tailored preset or full coverage:
   ```bash
   labtrust run-coordination-security-pack --out <dir> --matrix-preset hospital_lab
   ```
   Or without a preset (fixed or full methods/injections):
   ```bash
   labtrust run-coordination-security-pack --out <dir> --methods-from full --injections-from policy
   ```
   This writes `pack_summary.csv`, `pack_gate.md`, and `SECURITY/coordination_risk_matrix.csv` (and `.md`) under `<dir>`.

2. **Build report**  
   From the pack output directory, run the lab report builder to add SOTA leaderboard, method-class comparison, coordination decision, and a single markdown report:
   ```bash
   labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>] [--matrix-preset hospital_lab]
   ```
   If `--out` is omitted, artifacts are written into the pack directory. The builder runs `summarize-coordination` and `recommend-coordination-method` and then writes `LAB_COORDINATION_REPORT.md`.

3. **Use the decision**  
   Open `COORDINATION_DECISION.v0.1.json` or `COORDINATION_DECISION.md` for the **chosen method per scale**. Use `LAB_COORDINATION_REPORT.md` for a stakeholder-facing summary that links to the gate, risk matrix, leaderboard, and decision.

## Optimal methodology: what it means

The **recommended method** is produced by `recommend-coordination-method`, which:

- Loads the selection policy from `policy/coordination/coordination_selection_policy.v0.1.yaml`.
- Applies **hard constraints** (e.g. baseline violations ≤ 10, worst-case attack success rate ≤ 0.2, cost ceiling). A method is **admissible** only if it passes all constraints.
- Ranks admissible methods by the **objective** (e.g. `maximize_overall_score`). When `robustness.resilience_score` is present (e.g. from a matrix build), that is used; otherwise the fallback is throughput (max) then violations (min).
- Outputs one **chosen method per scale** (or "no admissible method" if none pass).

The **hospital lab at scale** profile uses the scale `medium_stress_signed_bus` (75 agents, 2 sites, signed bus). The selection policy’s per-scale rule for that scale prioritizes resilience over raw throughput (`resilience_weight_override: 1.2`). So the optimal method for the lab is the one that satisfies the constraints and ranks highest under that objective.

Evidence for the decision comes from the same run: `pack_summary.csv` (and optionally `pack_gate.md`, `SECURITY/coordination_risk_matrix`) provide the metrics that the decision builder uses. The lab report ties these together in one place.

## Related

- [Coordination studies](coordination_studies.md) – study runner, summary CSV, Pareto, SOTA leaderboard.
- [Security attack suite – Coordination security pack](../risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression) – pack matrix, gate rules, risk matrix.
- [Benchmarking plan](../benchmarks/benchmarking_plan.md) – Layer 1–3 and security pack outputs.
