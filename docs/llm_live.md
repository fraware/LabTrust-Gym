# Live LLM benchmark mode

This document describes how to run benchmarks with a live LLM backend (e.g. OpenAI), environment variables, and important caveats about non-determinism and cost.

## Enabling live LLM

Use the `--llm-backend` option with `run-benchmark`:

```bash
labtrust run-benchmark --task TaskA --episodes 3 --seed 42 --out results.json --llm-backend openai_live
```

Backends:

- **deterministic** (default when using LLM): Seeded, offline, no API calls. Same seed and task yield identical results. Use for CI and reproducibility.
- **openai_live**: Calls OpenAI Chat Completions with Structured Outputs. Requires `OPENAI_API_KEY`. Non-deterministic and incurs API cost.

If you omit `--llm-backend`, the benchmark uses scripted agents (no LLM). To use the deterministic LLM baseline:

```bash
labtrust run-benchmark --task TaskA --episodes 5 --llm-backend deterministic
```

Legacy flag `--use-llm-live-openai` is equivalent to `--llm-backend openai_live`.

## Environment variables (openai_live)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required for openai_live). | (none) |
| `LABTRUST_OPENAI_MODEL` | Model name (e.g. gpt-4o-mini, gpt-4o). | gpt-4o-mini |
| `LABTRUST_LLM_TIMEOUT_S` | Request timeout in seconds. | 20 |
| `LABTRUST_LLM_RETRIES` | Number of retries on transient errors. | 0 |

The code does not load `.env` automatically; set these in the shell or use a tool that injects them.

## Results metadata

When `--llm-backend` is set, the results JSON may include an optional **metadata** object (schema-safe; v0.2 allows it via `additionalProperties` or the optional `metadata` property):

- **llm_backend_id**: Backend identifier (e.g. `deterministic_constrained`, `openai_live`).
- **llm_model_id**: Model name (e.g. `gpt-4o-mini`) or `n/a` for deterministic.
- **llm_error_rate**: Fraction of LLM calls that returned an error (0.0 for deterministic).
- **mean_llm_latency_ms**: Mean latency per call in milliseconds (null for deterministic).

Example (openai_live):

```json
{
  "schema_version": "0.2",
  "task": "TaskA",
  "agent_baseline_id": "llm_live_openai_v1",
  "metadata": {
    "llm_backend_id": "openai_live",
    "llm_model_id": "gpt-4o-mini",
    "llm_error_rate": 0.02,
    "mean_llm_latency_ms": 450.5
  },
  "episodes": [...]
}
```

## Warnings

### Non-determinism

Runs with `--llm-backend openai_live` are **not deterministic**. Same task and seed can produce different throughput, violations, and blocked counts. Do not use for regression or reproducibility checks; use `--llm-backend deterministic` or scripted agents for that.

### Cost

Each step that uses the LLM (e.g. ops_0) consumes tokens (prompt + response). Cost depends on model and episode length. Set `LABTRUST_OPENAI_MODEL` to a smaller model (e.g. gpt-4o-mini) and limit `--episodes` when experimenting.

### Rate limits and errors

The live backend respects `LABTRUST_LLM_TIMEOUT_S` and `LABTRUST_LLM_RETRIES`. On timeout, refusal, or provider error the agent falls back to a NOOP action and the error is counted in **llm_error_rate**. Check **metadata.llm_error_rate** and **metadata.mean_llm_latency_ms** after a run to spot issues.

## Schema compatibility

Results files remain valid under **results.v0.2** and **results.v0.3**. The **metadata** object is optional and does not break existing consumers. Deterministic runs (scripted or `--llm-backend deterministic`) are unchanged and do not include **metadata** unless an LLM backend was used.
