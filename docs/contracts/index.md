# Contracts

Frozen contracts and formal API/data contracts. These define correctness and the anti-regression backbone.

## Frozen contracts

| Document | Description |
|----------|-------------|
| [Frozen contracts](frozen_contracts.md) | Runner output, queue, invariant registry, enforcement map, study spec (v0.1 / v1.0). |

## Data and API contracts

| Document | Description |
|----------|-------------|
| [UI data contract](ui_data_contract.md) | ui-export bundle format. When run has coordination data: **coordination_artifacts** (pack_summary, SOTA leaderboard main/full, method-class comparison) and **coordination/graphs/** (HTML charts: SOTA key metrics, throughput, violations, resilience, method-class). See [Frontend handoff](../reference/frontend_handoff_ui_bundle.md). |
| [Risk register contract (v0.1)](risk_register_contract.v0.1.md) | RiskRegisterBundle.v0.1 format. |
| [Queue contract (v0.1)](queue_contract.v0.1.md) | Queue contract. |
| [CLI contract](cli_contract.md) | CLI behavior and output. |
| [Scripted baseline policy](scripted_baseline_contract.md) | Scripted ops/runner policy YAML paths, keys, and loader; no file => in-code defaults. |
| [Metrics contract](metrics_contract.md) | Metrics schema, stability, and uncertainty metrics in standard reports. |
| [Injector get_metrics contract](injector_get_metrics_contract.md) | Risk injector `get_metrics()` return shape for `sec.*` episode metrics (coordination security pack). |
| [Cross-provider contract](cross_provider_contract.md) | Cross-provider comparability. |

Coordination method and matrix contracts are under [Coordination](../coordination/index.md).
