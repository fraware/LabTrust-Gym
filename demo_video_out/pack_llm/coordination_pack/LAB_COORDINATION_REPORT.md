# Lab coordination report

Single report bundle for coordination security pack results, SOTA leaderboard, and recommended method per scale.

## Scope

Matrix preset: `hospital_lab`.

## Recommended method per scale

- **medium_stress_signed_bus**: chosen method `kernel_auction_whca_shielded`
- **small_smoke**: chosen method `llm_local_decider_signed_bus`

## Artifacts in this bundle

| Artifact | Description |
| -------- | ----------- |
| [SECURITY_REPORT.md](SECURITY_REPORT.md) | Security pack and gate summary; links to pack_gate and SECURITY/. |
| [SAFETY_CASE_REPORT.md](SAFETY_CASE_REPORT.md) | Safety case summary and links (when SAFETY_CASE/ present). |
| [pack_gate.md](pack_gate.md) | PASS/FAIL/not_supported per cell. |
| [SECURITY/coordination_risk_matrix.md](SECURITY/coordination_risk_matrix.md) | Method x injection x phase outcomes. |
| [summary/sota_leaderboard.md](summary/sota_leaderboard.md) | Per-method means (throughput, violations, resilience, stealth). |
| [summary/method_class_comparison.md](summary/method_class_comparison.md) | Comparison by method class. |
| [COORDINATION_DECISION.md](COORDINATION_DECISION.md) | Chosen method and rationale (constraints + objective). |

## How to interpret

- **pack_gate.md**: Each row is a cell (scale, method, injection). PASS = threshold met; FAIL = threshold violated (with evidence); SKIP = not evaluated (not_applicable, no_data, or disabled_by_config); not_supported = capability not present.
- **coordination_risk_matrix**: Security metrics (attack_success_rate, detection_latency_steps, verdict) per method and injection.
- **SOTA leaderboard**: Methods ranked by aggregate metrics over all cells; use for throughput vs safety trade-offs.
- **COORDINATION_DECISION**: The recommended method per scale under the selection policy (constraints + maximize_overall_score).

## Next steps

- Deploy the chosen method(s) from COORDINATION_DECISION for each scale.
- Re-run with a different matrix preset (e.g. `--matrix-preset hospital_lab`) or `--methods-from full` for full coverage.
- Use `labtrust run-coordination-security-pack --out <dir> --matrix-preset hospital_lab` then `labtrust build-lab-coordination-report --pack-dir <dir>` to refresh this report.
