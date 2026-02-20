# Plan results: coordination improvement

This document describes the artifact produced to record a run that demonstrates the coordination improvement plan (guardrails, round_robin protocol, scale config, attribution).

## What is run

A fixed scenario is executed:

- **Task:** coord_scale
- **Coordination method:** llm_auction_bidder
- **Scale:** small_smoke (from `policy/coordination/scale_configs.v0.1.yaml`), which sets `coord_auction_protocol: round_robin`
- **Pipeline:** llm_offline (deterministic backends; no network)
- **Episodes:** 2 (configurable)
- **Seed:** 100 (configurable)

The run produces `results.json` and optional attribution in `metadata.llm_attribution_summary` when `LABTRUST_LLM_TRACE=1` is set.

## How to reproduce

From the repo root:

```bash
python scripts/run_plan_results_coordination.py --out-dir labtrust_runs/plan_results_coordination
```

With attribution (optional):

```bash
LABTRUST_LLM_TRACE=1 python scripts/run_plan_results_coordination.py --out-dir labtrust_runs/plan_results_coordination
```

Output files under the given directory:

- `results.json` — full benchmark results (schema: results.v0.2)
- `plan_results_coordination_summary.json` — short summary (scenario, episode metrics sample, attribution presence)
- `plan_results_coordination_summary.md` — human-readable summary and reproduce command

## Related

- [Observability](observability.md): attribution and `LABTRUST_LLM_TRACE`
- [LLM coordinator trials](llm_coord_trials.md): full trials script with real OpenAI (all four methods, report schema)
- [Coordination methods](../coordination/coordination_methods.md): guardrails and multi-LLM protocol tests
- [Outputs and results](outputs_and_results.md): result types and metadata
