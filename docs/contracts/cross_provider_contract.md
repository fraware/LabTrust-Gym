# Cross-provider output contract

Cross-provider runs (e.g. `run-cross-provider-pack`) produce comparable outputs regardless of provider (openai_live, anthropic_live, ollama_live, prime_intellect_live). This document freezes the required shape and normalization rules so that summary_cross_provider and per-provider outputs remain comparable.

## Required fields

### live_evaluation_metadata.json (per provider run)

- **model_id**: string or null; canonical model identifier.
- **temperature**: number or null.
- **tool_registry_fingerprint**: string or null.
- **allow_network**: boolean.

### summary_cross_provider.json

- **seed_base**: integer.
- **smoke**: boolean.
- **providers**: list of provider id strings.
- **runs**: list of run objects; each must have:
  - **provider**: string.
  - **out_dir**: string (path).
  - **live_metadata**: object or null (same shape as live_evaluation_metadata).
  - **llm_live_version**: string or null.
  - **latency_and_cost**: object or null; when present must include **mean_latency_ms** with aggregate keys.

### latency_and_cost_statistics (e.g. in llm_live.json)

- **mean_latency_ms**: object with **min**, **max**, **mean**, **sum** (numeric). Units: milliseconds.

## Normalization rules

- Latency: all latency values in milliseconds; missing values are omitted (no sentinel).
- Token/cost accounting: when present, same keys across providers (input_tokens, output_tokens, cost_usd or equivalent).
- Rounding: latency and cost may be rounded for display; storage uses float.

## Missing handling

- Missing optional fields: key absent or null; consumers must not assume presence except for required fields above.
- Per-task breakdown (per_task): optional; when present, same task keys across providers.
