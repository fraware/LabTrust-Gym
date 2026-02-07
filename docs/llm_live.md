# Live LLM benchmark mode

This document describes pipeline modes (deterministic vs LLM offline vs LLM live), how to run benchmarks with a live LLM backend (e.g. OpenAI), environment variables, and important caveats about non-determinism and cost.

## Pipeline modes

LabTrust-Gym uses a first-class **pipeline_mode** to separate deterministic/offline runs from live-LLM runs:

| Mode | Description | Network |
|------|-------------|---------|
| **deterministic** | Scripted agents only; no LLM interface is invoked. | Forbidden (fail-fast if any HTTP is attempted). |
| **llm_offline** | Uses the LLM agent interface but only with the deterministic, offline backend (seeded; no API). | Forbidden. |
| **llm_live** | Allows network-backed LLM backends (OpenAI, Ollama). | Allowed only when explicitly opted in (see below). |

**Defaults:** `run-benchmark`, `quick-eval`, `run-official-pack`, and `package-release` default to **deterministic** (no LLM, no network). CI and regression runs stay offline by default.

**Network gating:**

- In **deterministic** and **llm_offline**, any attempt to use network (e.g. live LLM backend) fails fast with a clear error.
- In **llm_live**, you must explicitly allow network: pass **`--allow-network`** or set **`LABTRUST_ALLOW_NETWORK=1`**. Otherwise the run fails with a message asking for one of these.

**Startup banner:** When a benchmark or pack run starts, the CLI prints pipeline_mode, llm_backend id (if any), and whether network is allowed, e.g.:

```
[LabTrust] pipeline_mode='deterministic' llm_backend='none' network=disabled
```

When **llm_live** is selected and network is allowed, the CLI also prints a **red warning**: **WILL MAKE NETWORK CALLS / MAY INCUR COST**.

**Where pipeline is recorded:** So a reviewer can tell at a glance whether a run was live-LLM or deterministic, the following are always written:

- **results.json** (top-level): **pipeline_mode**, **llm_backend_id**, **llm_model_id** (if any), **allow_network**.
- **metadata.json** (package-release): same fields when applicable.
- **index.json** (UI export zip): same fields for display in the UI.

**Why you saw no OpenAI calls:** Runs are offline by default. If you expected the live LLM to be called and saw no API traffic, you were likely in **deterministic** or **llm_offline** mode (or **llm_live** without `--allow-network`). Use `--pipeline-mode llm_live --allow-network` and the red warning will confirm that network is enabled.

## Enabling live LLM

Use the `--llm-backend` option with `run-benchmark` and (for openai_live/ollama_live) `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`:

```bash
labtrust run-benchmark --task TaskA --episodes 3 --seed 42 --out results.json --llm-backend openai_live --allow-network
```

Or set `LABTRUST_ALLOW_NETWORK=1` in the environment instead of `--allow-network`.

Backends:

- **deterministic** (default when using LLM): Seeded, offline, no API calls. Same seed and task yield identical results. Use for CI and reproducibility.
- **openai_live**: Calls OpenAI Chat Completions with Structured Outputs (ActionProposal schema). Requires `OPENAI_API_KEY`. Non-deterministic and incurs API cost.
- **openai_responses**: Production-grade OpenAI backend using the Responses API with a strict single-step decision JSON Schema (`action`, `args`, `reason_code`, `confidence`, `explanation_short`). Same env vars as openai_live; invalid schema responses yield NOOP with reason code **RC_LLM_INVALID_OUTPUT**.
- **ollama_live**: Calls a local Ollama server. Configure with `LABTRUST_LOCAL_LLM_URL`, `LABTRUST_LOCAL_LLM_MODEL`, `LABTRUST_LOCAL_LLM_TIMEOUT`. Non-deterministic; no API cost when running locally. For coordination methods (`llm_central_planner`, `llm_hierarchical_allocator`, `llm_auction_bidder`), `ollama_live` uses Ollama coordination and bid backends (proposal/bid JSON from the model; parse fallback to minimal valid on failure). See [LLM Coordination Protocol](llm_coordination_protocol.md).

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

## Structured Outputs and machine-safe responses

Live OpenAI backends use **Structured Outputs** (OpenAI response_format with JSON Schema) so that the model response is constrained to a fixed shape. This eliminates parsing brittleness: you get schema-valid JSON every time or a safe fallback.

- **openai_live**: Uses an ActionProposal schema (action_type, args, reason_code, token_refs, rationale, confidence, safety_notes). The API returns only valid JSON matching that schema.
- **openai_responses**: Uses a single-step decision schema: `action`, `args`, `reason_code`, `confidence`, `explanation_short` (maxLength 280). The backend maps this to the internal ActionProposal format. If the model returns invalid JSON or a value outside the schema (e.g. confidence not in [0,1], explanation_short > 280 chars), the backend returns **NOOP** with reason code **RC_LLM_INVALID_OUTPUT** and does not pass the response through. This keeps runs machine-safe and auditable.

Deterministic and llm_offline runs **never** call the live backend; pipeline gating ensures no network is used unless pipeline_mode is **llm_live** and **allow_network** is set.

## Live healthcheck

To verify that the live OpenAI backend is reachable and returns schema-valid output without running a full benchmark:

```bash
labtrust llm-healthcheck --backend openai_responses --model gpt-4o-mini --allow-network
```

Or use the default model (from `LABTRUST_OPENAI_MODEL`):

```bash
labtrust llm-healthcheck --backend openai_live --allow-network
```

Output (stderr): `ok`, `model_id`, `latency_ms`, `usage`, and `error` if the check failed. Exit code 0 if the single minimal request succeeded and the response matched the expected schema; 1 otherwise. Requires `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`.

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

## llm_offline fault model

In **llm_offline** mode, a deterministic **LLM fault model** can wrap the coordination repair backend to simulate failure modes for testing fallback and metrics. Configuration is in **policy/llm/llm_fault_model.v0.1.yaml** (schema: **policy/schemas/llm_fault_model.v0.1.schema.json**). Set **enabled: true** to activate.

**Fault types (seeded, deterministic):**

- **invalid_output**: Schema violation; fallback to NOOP, reason code **RC_LLM_INVALID_OUTPUT**.
- **empty_output**: Empty or refusal; fallback to NOOP, reason code **LLM_REFUSED**.
- **high_latency**: Simulated high latency; **meta.latency_ms** set to a configured value (e.g. 5000 ms); affects repair latency metrics and, where wired, coordination timing (view_age / stale_action_rate).
- **inconsistent_plan**: Contradictory assignments; fallback to NOOP, reason code **RC_LLM_FAULT_INJECTED**.

Faults are applied with a **probability** (per fault, per repair call) or on **step_intervals** (specific step indices). Same seed and same repair input yield the same fault decisions. When a fault triggers, the system returns safe NOOP (or the configured fallback) and records the reason code.

**Metrics:** Results v0.2 **coordination.llm** (or **coordination.llm_repair**) include **llm.fault_injected_rate** and **llm.fallback_rate** when the fault model is active.

**Reason code:** **RC_LLM_FAULT_INJECTED** is used for high_latency and inconsistent_plan; it is documented in **policy/reason_codes/reason_code_registry.v0.1.yaml**.

**Run TaskH with fault model:** Use **--pipeline-mode llm_offline** and **--llm-backend deterministic** with **llm_repair_over_kernel_whca**; the runner loads the fault model from policy and wraps the repair backend when enabled.

```bash
labtrust run-benchmark --task TaskH_COORD_RISK --episodes 1 --seed 42 --out results.json --coord-method llm_repair_over_kernel_whca --injection none --pipeline-mode llm_offline --llm-backend deterministic
```

## Schema compatibility

Results files remain valid under **results.v0.2** and **results.v0.3**. The **metadata** object is optional and does not break existing consumers. Deterministic runs (scripted or `--llm-backend deterministic`) are unchanged and do not include **metadata** unless an LLM backend was used.
