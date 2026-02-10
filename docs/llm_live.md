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

## Before using live providers

Do these two things first so you do not attribute failures to the model provider when the cause is missing env or a broken trust skeleton.

### 0) Load .env if you use it

The code **does not load `.env` automatically**. If you use a `.env` file for API keys, load it before any command; otherwise the code will not see the variables.

**macOS / Linux (bash/zsh):**

```bash
set -a
source .env
set +a
```

**Windows (PowerShell):**

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#') { return }
  if ($_ -match '^\s*$') { return }
  $k,$v = $_ -split '=',2
  [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim().Trim('"'), "Process")
}
```

**Sanity check (any OS):**

```bash
python -c "import os; print('OPENAI', bool(os.getenv('OPENAI_API_KEY'))); print('ANTHROPIC', bool(os.getenv('ANTHROPIC_API_KEY')))"
```

See also [Installation — Loading a .env file](installation.md#loading-a-env-file-optional).

### 1) Phase 2A — Does the repo still hold? (strict offline checks)

Run these **before** making live calls so you do not blame the provider for trust-skeleton or regression issues:

```bash
labtrust validate-policy
pytest -q
labtrust determinism-report
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q
```

**Acceptance (enforce mentally even if not gated in CI):**

- `validate-policy` is clean.
- `pytest` is clean.
- `determinism-report` asserts identical results across reruns.
- Golden suite passes.

If any of these fail, fix the repo first; only then treat live provider errors as provider issues.

## Enabling live LLM

Use the `--llm-backend` option with `run-benchmark` and (for openai_live/ollama_live) `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`:

```bash
labtrust run-benchmark --task throughput_sla --episodes 3 --seed 42 --out results.json --llm-backend openai_live --allow-network
```

Or set `LABTRUST_ALLOW_NETWORK=1` in the environment instead of `--allow-network`.

Backends:

- **deterministic** (default when using LLM): Seeded, offline, no API calls. Same seed and task yield identical results. Use for CI and reproducibility.
- **openai_live**: Calls OpenAI Chat Completions with Structured Outputs (ActionProposal schema). Requires `OPENAI_API_KEY`. Non-deterministic and incurs API cost.
- **openai_responses**: Production-grade OpenAI backend using the Responses API with a strict single-step decision JSON Schema (`action`, `args`, `reason_code`, `confidence`, `explanation_short`). Same env vars as openai_live; invalid schema responses yield NOOP with reason code **RC_LLM_INVALID_OUTPUT**.
- **anthropic_live**: Calls Anthropic Messages API with tool use (ActionProposal schema). Requires `ANTHROPIC_API_KEY`; install with `pip install -e ".[llm_anthropic]"`. Uses `LABTRUST_ANTHROPIC_MODEL` (default `claude-3-5-haiku-20241022`) and `LABTRUST_LLM_TIMEOUT_S`. Same metadata shape as openai_live for transparency aggregation.
- **ollama_live**: Calls a local Ollama server. Configure with `LABTRUST_LOCAL_LLM_URL`, `LABTRUST_LOCAL_LLM_MODEL`, `LABTRUST_LOCAL_LLM_TIMEOUT`. Non-deterministic; no API cost when running locally. For coordination methods (`llm_central_planner`, `llm_hierarchical_allocator`, `llm_auction_bidder`), `ollama_live` uses Ollama coordination and bid backends (proposal/bid JSON from the model; parse fallback to minimal valid on failure). See [LLM Coordination Protocol](llm_coordination_protocol.md).

If you omit `--llm-backend`, the benchmark uses scripted agents (no LLM). To use the deterministic LLM baseline:

```bash
labtrust run-benchmark --task throughput_sla --episodes 5 --llm-backend deterministic
```

Legacy flag `--use-llm-live-openai` is equivalent to `--llm-backend openai_live`.

## Environment variables (openai_live)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required for openai_live). | (none) |
| `LABTRUST_OPENAI_MODEL` | Model name (e.g. gpt-4o-mini, gpt-4o). | gpt-4o-mini |
| `LABTRUST_LLM_TIMEOUT_S` | Request timeout in seconds. | 20 |
| `LABTRUST_LLM_RETRIES` | Number of retries on transient errors. | 0 |

The code does not load `.env` automatically. If you use a `.env` file, load it first (see [Before using live providers](#before-using-live-providers)); otherwise set these in the shell or use a tool that injects them.

## Structured Outputs and machine-safe responses

Live OpenAI backends use **Structured Outputs** (OpenAI response_format with JSON Schema) so that the model response is constrained to a fixed shape. This eliminates parsing brittleness: you get schema-valid JSON every time or a safe fallback.

- **openai_live**: Uses an ActionProposal schema (action_type, args, reason_code, token_refs, rationale, confidence, safety_notes). The API returns only valid JSON matching that schema.
- **openai_responses**: Uses a single-step decision schema: `action`, `args`, `reason_code`, `confidence`, `explanation_short` (maxLength 280). The backend maps this to the internal ActionProposal format. If the model returns invalid JSON or a value outside the schema (e.g. confidence not in [0,1], explanation_short > 280 chars), the backend returns **NOOP** with reason code **RC_LLM_INVALID_OUTPUT** and does not pass the response through. This keeps runs machine-safe and auditable.

Deterministic and llm_offline runs **never** call the live backend; pipeline gating ensures no network is used unless pipeline_mode is **llm_live** and **allow_network** is set.

## Live LLM plumbing checks (per provider)

Use three layers for confidence: **healthcheck** (fastest) → **1-episode smoke** → **short multi-episode**. Run each layer for every backend you intend to compare so you do not attribute failures to the wrong layer.

### 3.1 Live backend healthcheck (fastest feedback)

Run the healthcheck for each live backend you plan to use. This confirms the provider is reachable and returns schema-valid output before you run any benchmark.

**OpenAI (Responses API, recommended):**

```bash
labtrust llm-healthcheck --backend openai_responses --model gpt-4o-mini --allow-network
```

**OpenAI (legacy Chat Completions):**

```bash
labtrust llm-healthcheck --backend openai_live --allow-network
```

(Default model from `LABTRUST_OPENAI_MODEL`.)

**Anthropic:**

```bash
labtrust llm-healthcheck --backend anthropic_live --allow-network
```

Requires `ANTHROPIC_API_KEY` and `pip install -e ".[llm_anthropic]"`. Default model from `LABTRUST_ANTHROPIC_MODEL`.

**Ollama:** The CLI does not currently expose an `ollama_live` healthcheck. Use a 1-episode smoke run (e.g. `run-benchmark --episodes 1 --llm-backend ollama_live --allow-network`) to confirm the local backend.

**Acceptance (per backend):**

- Exit code 0.
- Output reports `model_id`, `latency_ms`, and no schema mismatch (stderr: `ok`, `model_id`, `latency_ms`, `usage`; `error` only if the check failed).

Requires `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`. Output is on stderr: `ok`, `model_id`, `latency_ms`, `usage`; `error` only if the check failed. Exit code 0 when the single minimal request succeeded and the response matched the expected schema; 1 otherwise.

### 4.1 Single episode smoke (throughput_sla)

Do one episode first to validate that network gating actually enables calls, results include `pipeline_mode=llm_live` and backend/model identifiers, and (if you emit it) **LLM_DECISION** audit is present in logs.

**Example:**

```bash
labtrust run-benchmark \
  --task throughput_sla \
  --episodes 1 \
  --seed 42 \
  --out labtrust_runs/live_smoke/openai_taskA.json \
  --pipeline-mode llm_live \
  --llm-backend openai_responses \
  --llm-model gpt-4o-mini \
  --allow-network
```

Repeat for other provider/model variants only after the 1-episode path works.

**Acceptance:**

- Results JSON is written and schema-valid.
- Metadata present: `llm_backend_id`, `llm_model_id`, `mean_llm_latency_ms` (where applicable), `llm_error_rate`.
- `allow_network=true` is recorded (e.g. in results or manifest).

### 4.2 Short multi-episode sanity (5 episodes)

After 1-episode smoke passes, run a short multi-episode run to sanity-check error rate and latency before longer comparisons.

```bash
labtrust run-benchmark \
  --task throughput_sla \
  --episodes 5 \
  --seed 100 \
  --out labtrust_runs/live_sanity/openai_throughput_sla_5ep.json \
  --pipeline-mode llm_live \
  --llm-backend openai_responses \
  --llm-model gpt-4o-mini \
  --allow-network
```

**Acceptance:**

- `llm_error_rate` is low (set your own threshold; e.g. flag anything above 1–2% on throughput_sla).
- Latency distribution is stable enough to compare providers at least directionally.

## Cross-provider benchmark suite (what to run)

To compare providers responsibly, use the **same evaluation slice** across all providers: same seeds, episodes, `timing_mode`, and role assignments.

### Recommended provider-comparison suite (minimal but meaningful)

Run each of the following with identical config across providers:

| Task | Focus |
|------|--------|
| **throughput_sla** | Throughput under nominal conditions |
| **adversarial_disruption** | Adversarial disruption: detection/containment |
| **insider_key_misuse** | Insider/key misuse: RBAC/signature containment |
| **coord_scale** | Coordination nominal (choose 1–2 scales) |
| **coord_risk** | Coordination under 1–2 injections |

**Agent LLM baseline (throughput_sla, adversarial_disruption, insider_key_misuse):** Run with `--llm-backend <provider>` (and model). Keep episodes small initially (e.g. 3–5).

**Coordination LLM methods (coord_scale, coord_risk):** Run with:

- `--coord-method llm_central_planner` and/or `llm_hierarchical_allocator` and/or `llm_auction_bidder`
- `--pipeline-mode llm_live`
- `--allow-network`

**Example (coord_risk, one injection):**

```bash
labtrust run-benchmark \
  --task coord_risk \
  --coord-method llm_central_planner \
  --injection INJ-ID-SPOOF-001 \
  --episodes 3 \
  --seed 200 \
  --out labtrust_runs/provider_matrix/openai_taskH_spoof.json \
  --pipeline-mode llm_live \
  --llm-backend openai_responses \
  --llm-model gpt-4o-mini \
  --allow-network
```

### Aggregation (so you can compare)

After producing a directory of `*.json` results across providers/models:

```bash
labtrust summarize-results --in labtrust_runs/provider_matrix/*.json --out labtrust_runs/provider_matrix/summary
```

### What to inspect in the summary

- **Performance:** throughput, p95 TAT (if simulated), on_time_rate
- **Safety:** violations_total / violation_rate
- **Security (adversarial_disruption / insider_key_misuse / coord_risk):** detection latency, containment success, attack_success_rate, stealth_success_rate
- **Operational:** llm_error_rate, mean/p95 latency, total_tokens, estimated_cost_usd (only if pricing policy is complete)

**Comparability rule:** If `policy/llm/model_pricing.v0.1.yaml` does not list models for a provider, cost comparisons are invalid. Update pricing first or omit cost from provider comparisons.

### Provider-matrix runner (one command per provider)

To run the official pack once per backend and get comparable outputs and a merged summary:

```bash
labtrust run-cross-provider-pack --out ./cross_provider_out --providers openai_live,anthropic_live,ollama_live --seed-base 100
```

This writes `<out>/<provider>/` for each provider (full pack output: baselines/, SECURITY/, SAFETY_CASE/, TRANSPARENCY_LOG/, llm_live.json, live_evaluation_metadata.json) and `<out>/summary_cross_provider.json` plus `summary_cross_provider.md` with model_id and mean_latency_ms per run. Use `--no-smoke` to run the full pack per provider.

### Contract tests (same schema across providers)

The repo includes contract tests (`tests/test_cross_provider_contract.py`) that assert **live_evaluation_metadata.json** and **TRANSPARENCY_LOG/llm_live.json** have the same top-level shape and canonical latency keys (e.g. mean_latency_ms) whether the run came from openai_live, anthropic_live, or ollama_live. They use synthetic result files (no network), so CI stays deterministic. This ensures the transparency aggregator and risk register accept all providers consistently.

## Anthropic backend (implemented)

The **anthropic_live** backend is implemented in `baselines/llm/backends/anthropic_live.py` with the same contract guarantees as openai_live. The following checklist is satisfied; use it as a reference for adding further providers.

### 6.1 Add an Anthropic backend with the same contract guarantees

Design requirements (standards-of-excellence level):

- **Schema-valid decisions:** Emit decisions that conform to the same JSON schema used elsewhere (e.g. ActionProposal or single-step decision schema).
- **Hard-fail into safe NOOP:** On schema mismatch, refusal, or timeouts, return safe NOOP and do not pass invalid output through.
- **Results metadata:** Record provider id, model id, and latency in results metadata (same shape as openai_live / openai_responses).
- **Integration:** Use the same prompt registry, tool registry fingerprinting, and transparency log plumbing (e.g. prompt hashes, tool_registry_fingerprint in pack/evidence).

### 6.2 Add a healthcheck path for Anthropic

Expose a healthcheck so Phase 2C (live plumbing checks) does not depend on running a full benchmark. Add `anthropic_live` to the `llm-healthcheck --backend` choices and implement a minimal request that validates connectivity and schema-valid response.

### 6.3 Add unit tests that mock the provider client

Test at least:

- **Schema mismatch** → NOOP + reason code **RC_LLM_INVALID_OUTPUT**.
- **Timeout** → NOOP + error counter increments.
- **Refusal / empty** → NOOP + **LLM_REFUSED** (or the canonical refusal reason code).
- **Metadata correctness:** provider id, model id, and latency recorded in results/metadata.

### 6.4 Update CLI and docs (done)

- **CLI:** `--llm-backend anthropic_live` is supported for `run-benchmark` and `llm-healthcheck`.
- **Env vars:** `ANTHROPIC_API_KEY`, `LABTRUST_ANTHROPIC_MODEL` (default `claude-3-5-haiku-20241022`), `LABTRUST_LLM_TIMEOUT_S`.
- **.env:** The code does not load `.env` automatically; users must load it or set vars in the shell (see [Before using live providers](#before-using-live-providers)).

Install with `pip install -e ".[llm_anthropic]"` to use anthropic_live. Cross-provider contract tests validate the same metadata and llm_live.json shape across openai_live, anthropic_live, and ollama_live.

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
  "task": "throughput_sla",
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

**Run coord_risk with fault model:** Use **--pipeline-mode llm_offline** and **--llm-backend deterministic** with **llm_repair_over_kernel_whca**; the runner loads the fault model from policy and wraps the repair backend when enabled.

```bash
labtrust run-benchmark --task coord_risk --episodes 1 --seed 42 --out results.json --coord-method llm_repair_over_kernel_whca --injection none --pipeline-mode llm_offline --llm-backend deterministic
```

## Official pack with llm_live

When running the Official Benchmark Pack in live LLM mode, use:

```bash
labtrust run-official-pack --out ./official_pack_result --seed-base 100 --pipeline-mode llm_live --allow-network
```

The pack then loads **v0.2** policy (`policy/official/benchmark_pack.v0.2.yaml`), which defines the live coordination evaluation protocol (required metadata, cost accounting, reproducibility expectations). The run produces:

- **TRANSPARENCY_LOG/llm_live.json** — Prompt hashes, tool registry fingerprint, model version identifiers, latency and cost statistics; reviewable without exposing sensitive prompt text.
- **live_evaluation_metadata.json** — Required protocol fields: model_id, temperature, tool_registry_fingerprint, allow_network.

Report model_id and temperature (from this file or env) for reproducibility. The validator and risk-register exporter accept pack output that includes these artifacts; they are linked in the risk register when present. See [Official benchmark pack](official_benchmark_pack.md).

## Schema compatibility

Results files remain valid under **results.v0.2** and **results.v0.3**. The **metadata** object is optional and does not break existing consumers. Deterministic runs (scripted or `--llm-backend deterministic`) are unchanged and do not include **metadata** unless an LLM backend was used.
