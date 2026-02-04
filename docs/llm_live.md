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
- **ollama_live**: Calls a local Ollama server. Configure with `LABTRUST_LOCAL_LLM_URL`, `LABTRUST_LOCAL_LLM_MODEL`, `LABTRUST_LOCAL_LLM_TIMEOUT`. Non-deterministic; no API cost when running locally.

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

## Environment variables (ollama_live)

| Variable | Description | Default |
|----------|-------------|---------|
| `LABTRUST_LOCAL_LLM_URL` | Base URL for Ollama (e.g. http://localhost:11434). | http://localhost:11434 |
| `LABTRUST_LOCAL_LLM_MODEL` | Model name (e.g. llama3.2). | (required) |
| `LABTRUST_LOCAL_LLM_TIMEOUT` | Request timeout in seconds. | 60 |

## Results metadata

When `--llm-backend` is set, the results JSON may include an optional **metadata** object (schema-safe; v0.2 allows it via `additionalProperties` or the optional `metadata` property):

- **llm_backend_id**: Backend identifier (e.g. `deterministic_constrained`, `openai_live`).
- **llm_model_id**: Model name (e.g. `gpt-4o-mini`) or `n/a` for deterministic.
- **llm_error_rate**: Fraction of LLM calls that returned an error (0.0 for deterministic).
- **mean_llm_latency_ms**: Mean latency per call in milliseconds (null for deterministic).
- **p50_llm_latency_ms**, **p95_llm_latency_ms**: Latency percentiles (openai_live when token usage is captured).
- **total_tokens**, **tokens_per_step**: Token usage aggregates (openai_live).
- **estimated_cost_usd**: Optional; from policy/llm/model_pricing.v0.1.yaml when model is listed.

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
    "mean_llm_latency_ms": 450.5,
    "p50_llm_latency_ms": 380.0,
    "p95_llm_latency_ms": 920.0,
    "total_tokens": 12500,
    "tokens_per_step": 250.0,
    "estimated_cost_usd": 0.0025
  },
  "episodes": [...]
}
```

## Warnings

### Non-determinism

Runs with `--llm-backend openai_live` or `--llm-backend ollama_live` are **not deterministic**. Same task and seed can produce different throughput, violations, and blocked counts. Do not use for regression or reproducibility checks; use `--llm-backend deterministic` or scripted agents for that.

### Cost

Each step that uses the LLM (e.g. ops_0) consumes tokens (prompt + response). Cost depends on model and episode length. Set `LABTRUST_OPENAI_MODEL` to a smaller model (e.g. gpt-4o-mini) and limit `--episodes` when experimenting.

### Rate limits and errors

The live backend respects `LABTRUST_LLM_TIMEOUT_S` and `LABTRUST_LLM_RETRIES`. On timeout, refusal, or provider error the agent falls back to a NOOP action and the error is counted in **llm_error_rate**. Check **metadata.llm_error_rate** and **metadata.mean_llm_latency_ms** after a run to spot issues.

## Cost accounting

When using **openai_live**, the backend captures token usage from the API (**prompt_tokens**, **completion_tokens**, **total_tokens**) and aggregates over the run. Results **metadata** (and v0.3 reporting) may include:

- **total_tokens**: Sum of tokens across all LLM calls.
- **tokens_per_step**: Average tokens per step (total_tokens / total_calls).
- **p50_llm_latency_ms**, **p95_llm_latency_ms**: Latency percentiles (v0.3; kept in metadata for v0.2 compatibility).
- **estimated_cost_usd**: Optional. Computed from **policy/llm/model_pricing.v0.1.yaml** (per-1M token input/output prices). Only present when the model is listed in that file.

Per-call token counts are stored in each **LLM_DECISION** audit payload (**prompt_tokens**, **completion_tokens**, **total_tokens**) in the episode log and evidence bundle.

To add or update pricing for a model, edit **policy/llm/model_pricing.v0.1.yaml** (keys: **input_price_per_1m**, **output_price_per_1m** in USD). If the model is not listed, **estimated_cost_usd** is omitted from metadata.

When running **package-release** with profile **paper_v0.1**, if any summarized results used an LLM backend, **TABLES/llm_economics.csv** (and **llm_economics.md**) are written with one row per run: task, agent_baseline_id, llm_backend_id, llm_model_id, total_tokens, tokens_per_step, estimated_cost_usd, mean_llm_latency_ms, p50_llm_latency_ms, p95_llm_latency_ms, llm_error_rate.

## Schema compatibility

Results files remain valid under **results.v0.2** and **results.v0.3**. The **metadata** object is optional and does not break existing consumers. Deterministic runs (scripted or `--llm-backend deterministic`) are unchanged and do not include **metadata** unless an LLM backend was used.
