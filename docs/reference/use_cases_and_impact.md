# Use cases and impact

These tasks and the official pack are designed to reflect high-impact lab operations (safety, security, coordination).

## Task and pack mapping to impact

| Task / pack | Impact domain | Evidence |
|-------------|---------------|---------|
| throughput_sla | Operational efficiency | results + EvidenceBundles |
| stat_insertion, qc_cascade | Result integrity | results + EvidenceBundles |
| adversarial_disruption, insider_key_misuse | Security | security suite, EvidenceBundles |
| coord_scale, coord_risk, coordination security pack | Multi-agent safety | pack_summary.csv, pack_gate.md, risk register |

Running the official pack (or coordination pack) produces EvidenceBundles and risk register entries that document performance and safety for these scenarios.

## Capability metrics

The stack is built for high-impact, auditable use. Summary metrics (source: [Benchmark card](../benchmarks/benchmark_card.md), [Official benchmark pack](../benchmarks/official_benchmark_pack.md), [Risk register](../risk-and-security/risk_register.md)):

- **Tasks:** 8 (throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk).
- **Coordination methods:** Defined in `policy/coordination/coordination_methods.v0.1.yaml`; multiple methods (centralized, hierarchical, market, swarm, kernel+EDF/WHCA/auction, LLM planners, etc.) with coordination security pack coverage.
- **Risk register coverage:** required_bench cells are evidenced (by benchmarks, security pack, or studies) or explicitly waived; `validate-coverage --strict` gates un-evidenced required risks.
- **Security suite coverage:** Security attack suite (smoke/full), coordination security pack (method × scale × injection), prompt-injection defense, safety case.
- **Export:** Every run can produce FHIR R4 bundles and EvidenceBundles (via export-receipts and export-fhir from episode logs and receipts).

These capability metrics support the claim that the stack is built for high-impact, auditable use in safety, security, and coordination.
