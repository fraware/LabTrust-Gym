# Live LLM benchmark mode

This document describes pipeline modes (deterministic vs LLM offline vs LLM live), how to run benchmarks with a live LLM backend (e.g. OpenAI), environment variables, and important caveats about non-determinism and cost.

## Pipeline modes

LabTrust-Gym uses exactly three **pipeline_mode** values: **deterministic** | **llm_offline** | **llm_live**. The code and CLI accept only these literals (see `src/labtrust_gym/pipeline.py` and `--pipeline-mode` choices).

### Canonical definitions

| Mode | Description | Network | Reproducibility | Typical use |
|------|-------------|---------|----------------|-------------|
| **deterministic** | Scripted agents only; no LLM interface is invoked. | Forbidden (fail-fast if any HTTP is attempted). | Same seed yields same results; byte-identical outputs when not using non-deterministic features. | CI, regression, reproduce, paper artifact, default for most commands. |
| **llm_offline** | Uses the LLM agent/coordination interface but only with a deterministic backend (fixture lookup or seeded RNG). No real API calls. | Forbidden. | Reproducible given same seed or same fixtures. | Offline LLM evaluation, tests without API cost, tasks that use LLM-shaped agents (e.g. llm_safe_v1) in CI. |
| **llm_live** | Allows network-backed LLM backends (OpenAI, Ollama, Anthropic). | Allowed only when explicitly opted in (`--allow-network` or `LABTRUST_ALLOW_NETWORK=1`). | No; runs record `non_deterministic: true`. | Interactive or cost-accepting runs; live model comparison. |

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

## Where the LLM sits in the benchmark

When you run a benchmark with an LLM (per-agent or coordination), the **benchmark runner** owns the PettingZoo env (LabTrustParallelEnv). Each step it gets observations from the env, passes them to the LLM agent or coordination method, and steps the env with the returned actions. The LLM never talks to the env directly; it is a policy that maps observations to actions. For a full breakdown of PettingZoo, LLMs, and agentic coordination, see [Simulation, LLMs, and agentic systems](../architecture/simulation_llm_agentic.md).

## LLM live pipeline contract

The llm_live pipeline guarantees the following so that live runs are auditable and safe:

| Guarantee | Description |
|-----------|-------------|
| **Schema-valid decisions** | All provider responses are validated against the ActionProposal (or single-step decision) schema. Invalid JSON or out-of-schema values yield **NOOP** with reason code **RC_LLM_INVALID_OUTPUT** and are never passed to the engine. |
| **Hard-fail to NOOP** | On timeout, refusal, provider error, or rate limit (429), the agent returns NOOP and records the reason code. **llm_error_rate** and **metadata** reflect counts and latency. |
| **Metadata recorded** | Every run records **pipeline_mode**, **llm_backend_id**, **llm_model_id**, and (when available) **mean_llm_latency_ms**, **llm_error_rate**, token usage, and **estimated_cost_usd**. Same shape across openai_live, anthropic_live, ollama_live for cross-provider comparison. |
| **Redaction in traces** | When using LLM_TRACE or transparency logs, request content is redacted via **secret_scrubber** (API keys, secrets, sensitive fields). Prompt hashes and tool registry fingerprint are logged; full prompt text is not. |
| **Per-call latency and usage** | When a trace collector is used (e.g. llm_live_eval profile), each call records token usage and **latency_ms** (when provided by the backend). The LLM_TRACE **usage.json** includes **per_call** (one entry per call, with latency_ms when available) and an aggregate **latency_ms** (min, max, mean, sum) for debugging and cost attribution. |
| **Network gating** | Live backends are only used when **pipeline_mode=llm_live** and **--allow-network** (or LABTRUST_ALLOW_NETWORK=1). Otherwise the run fails fast with a clear error. |

**Structured outputs:** For **openai_live** and **anthropic_live**, the ActionProposal `args` use a strict schema (`additionalProperties: false`, explicit `required` and property set). Provider responses that include extra fields or omit required fields are rejected and yield NOOP; use `scripts/check_llm_backends_live.py` to confirm the backend returns valid structure before long runs.

**Optional guardrails** (env-configured): circuit breaker (skip LLM after consecutive blocks; cooldown), rate limiter (max calls per time window), fallback model chain (try next model on refusal/timeout), request cache (skip API for identical prompt hash). See [Guardrails (circuit breaker and rate limiter)](#guardrails-circuit-breaker-and-rate-limiter).

### Definition of done (new LLM methods or backends) {#llm-excellence-checklist-for-new-methods-or-backends}

When adding a **new** LLM coordination method or live backend, the following must be satisfied before considering it done:

| Requirement | Description |
|-------------|-------------|
| **Schema-valid decisions** | All provider responses are validated against the ActionProposal (or single-step decision) schema; invalid or out-of-schema output yields NOOP with a reason code and is never passed to the engine. |
| **Hard-fail to NOOP** | On timeout, refusal, provider error, or rate limit (429), the agent returns NOOP and records the reason code; run metadata reflects counts and latency. |
| **Metadata** | Every run records **llm_backend_id**, **llm_model_id**, and (when available) **mean_llm_latency_ms**, **llm_error_rate**, token usage, **estimated_cost_usd** in the same shape as existing backends. |
| **Integration** | Prompt fingerprint and transparency log (when enabled) include the new backend; redaction and secret scrubbing apply. |

Confirm this checklist when contributing a new method or backend; see [CONTRIBUTING](../../CONTRIBUTING.md) for the reference link.

## Pre-flight checklist

Before any live run, complete this checklist so you do not blame the provider for env or trust-skeleton issues:

| Step | Action | Acceptance |
|------|--------|------------|
| **0. Env** | Load `.env` if you use it; set API key in process. | `python -c "import os; print('OPENAI', bool(os.getenv('OPENAI_API_KEY')))"` shows key present. From repo root, `python scripts/check_llm_backends_live.py --backends openai_live` (or anthropic_live) loads `.env` when present and is the recommended minimal live-backend check. |
| **1. Phase 2A** | Run offline checks. | `validate-policy`, `pytest -q`, `determinism-report`, `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q` all pass. |
| **2. Healthcheck** | Run backend healthcheck. | `labtrust llm-healthcheck --backend <backend> --allow-network` exits 0 and reports model_id, latency_ms. |
| **3. Cost awareness** | Know model and episode count. | Small model (e.g. gpt-4o-mini), limited `--episodes` when experimenting; check **metadata.estimated_cost_usd** after run. |

## Before using live providers

Do the steps above first so you do not attribute failures to the model provider when the cause is missing env or a broken trust skeleton.

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

See also [Installation — Loading a .env file](../getting-started/installation.md#loading-a-env-file-optional).

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
- **ollama_live**: Calls a local Ollama server. Configure with `LABTRUST_LOCAL_LLM_URL`, `LABTRUST_LOCAL_LLM_MODEL`, `LABTRUST_LOCAL_LLM_TIMEOUT`. Non-deterministic; no API cost when running locally. For coordination methods (`llm_central_planner`, `llm_hierarchical_allocator`, `llm_auction_bidder`), `ollama_live` uses Ollama coordination and bid backends (proposal/bid JSON from the model; parse fallback to minimal valid on failure). See [LLM Coordination Protocol](../benchmarks/llm_coordination_protocol.md).

If you omit `--llm-backend`, the benchmark uses scripted agents (no LLM). To use the deterministic LLM baseline:

```bash
labtrust run-benchmark --task throughput_sla --episodes 5 --llm-backend deterministic
```

Legacy flag `--use-llm-live-openai` is equivalent to `--llm-backend openai_live`.

**Per-role coordinator backends:** You can use different backends or models per coordination role (planner, bidder, repair, detector) in one run. Use `--coord-planner-backend`, `--coord-bidder-backend`, `--coord-repair-backend`, `--coord-detector-backend` (values: `inherit`, `openai_live`, `ollama_live`, `anthropic_live`, etc.) and optionally `--coord-planner-model`, `--coord-bidder-model`, `--coord-repair-model`, `--coord-detector-model`. When unset or `inherit`, the role uses `--llm-backend` and `--llm-model`. See [Coordination methods audit](../coordination/coordination_methods_audit.md#multi-backend-configuration-per-role-backends).

### Running coordinator tasks with live LLM

To run **coordinator** tasks (`coord_scale`, `coord_risk`) with a live LLM backend, use `run-benchmark` with `--task coord_scale` or `--task coord_risk`, `--coord-method`, `--pipeline-mode llm_live`, `--allow-network`, and `--llm-backend openai_live` (or `anthropic_live`, `ollama_live`). Example:

```bash
labtrust run-benchmark --task coord_scale --episodes 1 --seed 42 --out results.json \
  --pipeline-mode llm_live --allow-network --llm-backend openai_live \
  --coord-method llm_central_planner
```

Supported coordinator methods with live backends include `llm_central_planner`, `llm_auction_bidder`, `llm_central_planner_debate`, and `llm_central_planner_agentic`. For `llm_auction_bidder` with round-robin protocol, the scale config must set `coord_auction_protocol: round_robin` (task or pack policy may provide this).

**Attribution and cost:** Full attribution and cost aggregation require `LABTRUST_LLM_TRACE=1` (or an equivalent trace collector). See [Observability](../reference/observability.md).

**Tests and commands:** Live integration tests for both the agent path and the coordinator path live in `tests/test_openai_live.py`. They run only when `LABTRUST_RUN_LLM_LIVE=1` and `OPENAI_API_KEY` are set. To run all OPENAI_API_KEY-gated tests and the trials script in one go, use the runner scripts; see [Tests requiring OPENAI_API_KEY](#tests-requiring-openai_api_key). The optional CI workflow (LLM live optional smoke) runs a coord live smoke step when the OpenAI key is present.

### Running full LLM coordinator trials (OpenAI)

To run **all four** LLM coordinator methods (llm_central_planner, llm_auction_bidder, llm_central_planner_debate, llm_central_planner_agentic) with real OpenAI and gather results into a single report, use the trials script:

```bash
LABTRUST_LLM_TRACE=1 python scripts/run_llm_coord_trials_openai.py --out-dir labtrust_runs/llm_coord_trials_openai
```

**Requirements:** `OPENAI_API_KEY` must be set. Set `LABTRUST_LLM_TRACE=1` (or pass `--trace`) so the report includes attribution (by_backend call_count, latency_ms_sum, cost_usd_sum).

**Output:** Per-method `results.json` files and `llm_coord_trials_report.json` / `llm_coord_trials_report.md` with duration and attribution per method. See [LLM coordinator trials](../reference/llm_coord_trials.md) for the report schema and reproduce steps.

The same lab policies (RBAC, shield, invariants) apply to these runs as to the deterministic pipeline.

### Tests requiring OPENAI_API_KEY

The following tests and commands use `OPENAI_API_KEY` and (where noted) `LABTRUST_RUN_LLM_LIVE=1`. Running them all confirms that agent path, coordinator methods, prompt-injection live check, and trials work with your key.

| Gate | Test or command | Notes |
|------|-----------------|--------|
| `LABTRUST_RUN_LLM_LIVE=1` + `OPENAI_API_KEY` | `tests/test_openai_live.py -m live` | All 7 tests: one_episode_task_a, central_planner, auction_bidder, debate, central_planner_two_episodes, agentic, per_role_backends. Per-role test also needs `ANTHROPIC_API_KEY` or it is skipped. |
| Same | `tests/test_llm_prompt_injection_golden.py::test_openai_live_prompt_injection_schema_valid_and_constrained` | Live prompt-injection schema and constraint check. |
| Same | `scripts/run_llm_coord_trials_openai.py` | All four coord methods, 1 episode each (or more with `--episodes`). |
| `RUN_ONLINE_TESTS=1` + `OPENAI_API_KEY` | `tests/test_llm_backends.py::test_openai_hosted_backend_integration` | Hosted backend integration; different env from live tests. |
| `LABTRUST_RUN_LLM_ATTACKER` + `OPENAI_API_KEY` | `tests/test_security_attack_suite.py` (tests marked `@pytest.mark.live`) | Red-team / attacker regression; separate purpose. |

**One-command runners (recommended):** These run the test_openai_live.py live tests, the prompt-injection openai_live test, and the trials script. Set `OPENAI_API_KEY` and `LABTRUST_RUN_LLM_LIVE=1` first.

- **PowerShell:** `.\scripts\run_llm_live_coord_checks.ps1`
- **Bash:** `LABTRUST_RUN_LLM_LIVE=1 OPENAI_API_KEY=sk-... ./scripts/run_llm_live_coord_checks.sh`

They do not run `RUN_ONLINE_TESTS=1` or `LABTRUST_RUN_LLM_ATTACKER` tests; run those separately if needed.

## Environment variables (openai_live)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required for openai_live). | (none) |
| `LABTRUST_OPENAI_MODEL` | Model name (e.g. gpt-4o-mini, gpt-4o). | gpt-4o-mini |
| `LABTRUST_LLM_TIMEOUT_S` | Request timeout in seconds. | 20 |
| `LABTRUST_LLM_RETRIES` | Number of retries on transient errors. | 0 |

For tracing and cost/latency attribution (including OTLP export and per-agent/backend summary), see [Observability](../reference/observability.md).

The code does not load `.env` automatically. If you use a `.env` file, load it first (see [Before using live providers](#before-using-live-providers)); otherwise set these in the shell or use a tool that injects them.

## Structured Outputs and machine-safe responses

Live OpenAI backends use **Structured Outputs** (OpenAI response_format with JSON Schema) so that the model response is constrained to a fixed shape. This eliminates parsing brittleness: you get schema-valid JSON every time or a safe fallback.

- **openai_live**: Uses an ActionProposal schema (action_type, args, reason_code, token_refs, rationale, confidence, safety_notes). The API returns only valid JSON matching that schema.
- **openai_responses**: Uses a single-step decision schema: `action`, `args`, `reason_code`, `confidence`, `explanation_short` (maxLength 280). The backend maps this to the internal ActionProposal format. If the model returns invalid JSON or a value outside the schema (e.g. confidence not in [0,1], explanation_short > 280 chars), the backend returns **NOOP** with reason code **RC_LLM_INVALID_OUTPUT** and does not pass the response through. This keeps runs machine-safe and auditable.

Deterministic and llm_offline runs **never** call the live backend; pipeline gating ensures no network is used unless pipeline_mode is **llm_live** and **allow_network** is set.

## Offline replay and fault injection

**Fault model (llm_offline):** Today the LLM fault model applies only to the **repair** backend of `llm_repair_over_kernel_whca`. Configuration is in `policy/llm/llm_fault_model.v0.1.yaml` (invalid_output, empty_output, high_latency, inconsistent_plan). When enabled, the repair path injects seeded failures and records fallback counts and reason codes. Planned improvements extend the fault model to the **agent** path and to **proposal/bid** backends (llm_central_planner, llm_auction_bidder) so fallbacks and metrics can be tested offline for all LLM entry points.

### Capture and replay (first-class workflow)

**Step 1 — Capture:** Run once with network enabled to record request/response pairs.

- **Agent path:** Use **record-llm-fixtures**; it populates `tests/fixtures/llm_responses/fixtures.json` (and merges into existing keys).

```bash
labtrust record-llm-fixtures --task insider_key_misuse --episodes 1 --llm-backend openai_responses
```

- **Coordination path (optional):** For coord_risk or coord_scale with llm_central_planner or llm_auction_bidder, run **record-coordination-fixtures** to write `tests/fixtures/llm_responses/coordination_fixtures.json`.

```bash
labtrust record-coordination-fixtures --task coord_risk --coord-method llm_central_planner --llm-backend openai_live --episodes 1 --seed 42
```

Use `--llm-backend openai_hosted`, `openai_live`, `openai_responses`, `anthropic_live`, or `ollama_live` for agent; for coordination use `openai_live`, `ollama_live`, or `anthropic_live`. Set the corresponding API key; for Ollama ensure the local server is running.

**Step 2 — Replay:** Run the same task with **llm_offline**, **deterministic** (FixtureBackend for agents), and (for coord tasks) **--coord-fixtures-path** pointing at the fixtures dir. Use the same `--task`, `--seed`, and `--episodes`. No network is used.

```bash
# Agent-only replay
labtrust run-benchmark --task insider_key_misuse --episodes 1 --seed 42 --out replay_out.json --pipeline-mode llm_offline --llm-backend deterministic

# Coord replay (same seed and task as capture)
labtrust run-benchmark --task coord_risk --coord-method llm_central_planner --episodes 1 --seed 42 --out replay_coord.json --pipeline-mode llm_offline --llm-backend deterministic --coord-fixtures-path tests/fixtures/llm_responses
```

Alternatively use **replay-from-fixtures** (see below) to replay from a previous run directory or with explicit task/seed/fixtures.

**Acceptance:** Same seed and task yield comparable results (throughput, violation counts) between the live run and the offline replay, with no network on replay. Pipeline mode and `llm_backend_id` in results identify the run as offline replay. Use for regression (decoder/shield changes) and audit (exact replay of a past live run).

### replay-from-fixtures

To replay a prior capture without remembering all flags, use:

```bash
labtrust replay-from-fixtures --task <task> --episodes <n> --seed <s> [--coord-method <method>] [--out <path>]
```

This runs the benchmark with `--pipeline-mode llm_offline`, `--llm-backend deterministic`, and (for coord_risk/coord_scale) `--coord-fixtures-path tests/fixtures/llm_responses`. Omit `--coord-method` for non-coord tasks. If a fixture is missing (e.g. you did not record coordination), the run fails with a clear remediation message.

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

**Ollama:**

```bash
labtrust llm-healthcheck --backend ollama_live --allow-network
```

Optional `--model` overrides `LABTRUST_LOCAL_LLM_MODEL`. Requires local Ollama (e.g. `LABTRUST_LOCAL_LLM_URL`, default `http://localhost:11434`). Exit code 0 and `model_id`, `latency_ms` on stderr when the minimal request succeeds and the response matches the expected NOOP schema.

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

**Entry point for cross-provider comparison:** Use **`labtrust run-cross-provider-pack --out <dir> --providers openai_live,anthropic_live,ollama_live`** to run the same (full) official pack once per provider with the same seeds; the command emits per-provider output dirs and a merged **`summary_cross_provider.json`** and **`summary_cross_provider.md`** for comparison. No separate script or manual matrix is required.

This writes `<out>/<provider>/` for each provider (full pack output: baselines/, SECURITY/, SAFETY_CASE/, TRANSPARENCY_LOG/, llm_live.json, live_evaluation_metadata.json) and `<out>/summary_cross_provider.json` plus `summary_cross_provider.md` with model_id and mean_latency_ms per run. Use `--no-smoke` to run the full pack per provider.

### Contract tests (same schema across providers)

The repo includes contract tests (`tests/test_cross_provider_contract.py`) that assert **live_evaluation_metadata.json** and **TRANSPARENCY_LOG/llm_live.json** have the same top-level shape and canonical latency keys (e.g. mean_latency_ms) whether the run came from openai_live, anthropic_live, or ollama_live. They use synthetic result files (no network), so CI stays deterministic. This ensures the transparency aggregator and risk register accept all providers consistently.

## LLM coordination entry points and standards-of-excellence checklist

The following entry points use an LLM (or deterministic) backend for coordination. Each should satisfy the same design requirements as single-agent LLM backends (schema-valid decisions, hard-fail to NOOP, metadata, integration). See [LLM Coordination Protocol](../benchmarks/llm_coordination_protocol.md) for proposal schema, shield semantics, and repair loop.

| Entry point | Component | Schema-valid | Hard-fail NOOP | Metadata | Integration |
|-------------|-----------|--------------|----------------|---------|-------------|
| **llm_central_planner** | Central coordinator (state_digest -> backend -> proposal) | Yes: `validate_proposal` before use | Yes: invalid/error -> all NOOP | Yes: meta in proposal, results.metadata | prompt_fingerprint, policy_fingerprint, transparency log |
| **llm_hierarchical_allocator** | Hub allocator + local controller | Yes: `validate_proposal` | Yes: invalid/error -> all NOOP | Yes | same |
| **llm_auction_bidder** | Bid backend -> dispatcher | Yes: bid schema / proposal validation where used | Yes: safe_fallback -> all NOOP | Yes | same |
| **llm_gossip_summarizer** | Summarizer backend -> per-agent actions | Yes: proposal validation before execution | Yes: error/empty -> NOOP | Yes | same |
| **llm_repair_over_kernel_whca** | Repair backend (on shield block) | Yes: repair response validated; parse error -> NOOP | Yes: timeout/refusal/parse -> all NOOP, repair_fallback_noop_count | Yes: coordination.llm_repair metrics | repair_request_hash, shield_outcome_hash in audit |
| **llm_local_decider_signed_bus** | Per-agent ActionProposal -> signed bus | Yes: ActionProposal schema per message | Yes: invalid/rejected -> NOOP for that agent | Yes: comm metrics, per-agent outcome | signed bus, reconciler |
| **llm_constrained** | Constrained planner backend | Yes: `validate_proposal` | Yes: invalid -> all NOOP | Yes | same |
| **llm_detector_throttle_advisor** | Detector/advisor LLM -> throttle or NOOP | Yes: advisor output validated | Yes: invalid -> safe_detector_fallback (NOOP) | Yes: assurance metrics | detector_advisor, simplex |
| **Single-agent LLM** (throughput_sla, etc.) | baselines/llm/agent + backends | Yes: ActionProposal / single-step schema | Yes: RC_LLM_INVALID_OUTPUT, LLM_REFUSED -> NOOP | Yes: results.metadata | prompt/tool fingerprint, LLM_DECISION audit |

**Gaps to fix (if any):** When adding a new LLM coordination method or backend, ensure (1) all responses pass through the same schema validation (`validate_proposal` for CoordinationProposal, or the appropriate ActionProposal schema), (2) on validation failure, timeout, or refusal the code path returns NOOP and does not pass invalid output through, (3) backend_id, model_id, latency (and optionally tokens) are recorded in proposal meta and results metadata, (4) prompt_fingerprint and policy_fingerprint are set and transparency log / episode log receive the expected audit entries.

### LLM excellence checklist (for new methods or backends)

When contributing a **new** LLM coordination method or backend, the PR must confirm that the following four criteria are satisfied. Use the table above as the reference; add a row for the new entry point.

| Criterion | Requirement |
|-----------|-------------|
| **Schema-valid decisions** | All responses pass through the same schema validation (e.g. `validate_proposal` for CoordinationProposal, or the appropriate ActionProposal schema). |
| **Hard-fail to NOOP** | On validation failure, timeout, or refusal, return safe NOOP and do not pass invalid output through. |
| **Metadata** | backend_id, model_id, latency (and optionally tokens) in proposal meta and results metadata. |
| **Integration** | prompt_fingerprint, policy_fingerprint, and transparency log / episode log audit entries. |

In the PR description, state that the new method/backend satisfies the checklist and add it to the entry-point table in this section.

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

## Guardrails (circuit breaker and rate limiter)

When **pipeline_mode=llm_live**, the LLM agent uses optional **circuit breaker** and **rate limiter** so repeated blocks or high call volume do not hammer the API.

### Guardrails contract

- **Circuit breaker:** When the pre-LLM or shield path blocks consecutively at least `LABTRUST_CIRCUIT_BREAKER_THRESHOLD` times, the circuit opens. The next `LABTRUST_CIRCUIT_BREAKER_COOLDOWN` LLM calls are skipped: the agent returns NOOP with reason_code **CIRCUIT_BREAKER_OPEN** and no live call is made. The circuit resets on the first successful (non-blocked) decision (i.e. when the LLM is invoked and the returned action is accepted).
- **Rate limiter:** At most `LABTRUST_RATE_LIMIT_MAX_CALLS` LLM calls are allowed per sliding window of `LABTRUST_RATE_LIMIT_WINDOW_SECONDS` seconds. When the limit is reached, the next call is skipped (NOOP with reason_code **RATE_LIMITED**) until the window slides and a slot frees.

Provider-level errors (e.g. HTTP 429, timeouts, refusal) are handled by each backend (NOOP fallback, optional retries). When a backend sets **last_error_code** after such an error, **LLMAgentWithShield** calls **circuit_breaker.record_block()**, so consecutive provider failures open the circuit (same as shield or pre-LLM blocks). Backends that implement **last_error_code** (e.g. openai_live, anthropic_live, ollama_live) thus drive the circuit on 429/timeout/refusal.

Both are configured via environment variables (defaults are applied if unset):

| Variable | Description | Default |
|----------|-------------|---------|
| `LABTRUST_CIRCUIT_BREAKER_THRESHOLD` | Consecutive blocks before opening circuit. | 5 |
| `LABTRUST_CIRCUIT_BREAKER_COOLDOWN` | Number of calls to skip while circuit is open. | 10 |
| `LABTRUST_RATE_LIMIT_MAX_CALLS` | Max LLM calls per window. | 60 |
| `LABTRUST_RATE_LIMIT_WINDOW_SECONDS` | Sliding window length (seconds). | 60.0 |

Use lower thresholds or smaller windows for cost control or to avoid provider rate limits (e.g. 429). Reset happens at episode start so limits apply per episode.

### Coordinator guardrails

The **coordinator path** is any call to `proposal_backend.generate_proposal`, `bid_backend.generate_proposal`, `repair_backend.repair` (or its inner `generate`), and `detector_backend` when it uses an LLM. These run inside the runner's episode loop when a coordination method uses a live LLM backend; they are not in the CLI.

**Contract:** The same idea as the agent path applies to the coordinator path when guardrails are enabled:

- **Circuit breaker:** After K consecutive failures or 429s from the coordinator backend, the circuit opens for N steps. During cooldown, the coordinator returns a safe fallback (e.g. all NOOP or last valid proposal) and does not call the live backend.
- **Rate limit:** At most M coordinator LLM calls per sliding window of W seconds. When the limit is reached, the next call is skipped and the coordinator returns the same safe fallback.
- **Timeout:** Existing `LABTRUST_LLM_TIMEOUT_S` applies to coordinator calls where the backend supports it.

On circuit open or rate limit, the coordinator returns a safe fallback (all NOOP for proposal/bid/repair) and a **reason code** in meta: **CIRCUIT_BREAKER_OPEN** or **RATE_LIMITED**. The runner wraps coordinator backends (proposal, bid, repair) with a guardrail layer that uses the same environment variables as the agent (`LABTRUST_CIRCUIT_BREAKER_THRESHOLD`, `LABTRUST_CIRCUIT_BREAKER_COOLDOWN`, `LABTRUST_RATE_LIMIT_MAX_CALLS`, `LABTRUST_RATE_LIMIT_WINDOW_SECONDS`) unless dedicated `LABTRUST_COORD_*` overrides are set. Reset happens at episode start so limits apply per episode.

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

Report model_id and temperature (from this file or env) for reproducibility. The validator and risk-register exporter accept pack output that includes these artifacts; they are linked in the risk register when present. See [Official benchmark pack](../benchmarks/official_benchmark_pack.md).

### Test policy (real API vs mocks)

- **Real LLM API tests** (openai_responses, anthropic_live, ollama_live) are **not** run on every push/PR; they require secrets or local services and are opt-in.
- **Scheduled (nightly) and workflow_dispatch:** When API keys are configured, the optional smoke workflow runs healthcheck and a short pack run; see [CI](../operations/ci.md#llm-live-optional-smoke-nightly--manual).
- **Unit and integration tests that mock backends** (e.g. `test_network_guard_ci`, `test_ollama_live` with mocked urlopen, `test_llm_guardrails`) run in normal CI and must pass.

## Deterministic and LLM live: standalone use and interoperability

Both pipelines are designed to make sense when run by themselves and to interoperate via shared artifacts and tooling.

### Standalone use

| Pipeline | Purpose | Typical use |
|----------|---------|-------------|
| **Deterministic** | Scripted agents only; no LLM, no network. Same seed yields identical metrics. | CI, regression (baseline guard, golden suite), reproducibility, release verification. |
| **llm_live** | Live LLM backends (OpenAI, Anthropic, Ollama). Requires `--allow-network`. Non-deterministic. | Live evaluation, provider comparison, transparency logs, cost/latency attribution. |

- **Deterministic** is the default for `run-benchmark`, `quick-eval`, `generate-official-baselines`, `package-release`, and `run-official-pack`. Official baselines in `benchmarks/baselines_official/v0.2/` are produced with the deterministic pipeline only; baseline regression compares against those and must stay deterministic.
- **llm_live** is used when you pass `--pipeline-mode llm_live --allow-network` and a live `--llm-backend`. The official pack can be run in llm_live mode (`run-official-pack --pipeline-mode llm_live --allow-network`), which uses **benchmark_pack.v0.2** and emits TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json. Cross-provider runs (`run-cross-provider-pack`) are llm_live-only (one pack run per provider, then a merged summary).

### How they speak to each other

- **Same results schema:** Both pipelines write **results.v0.2** (and v0.3 where applicable). Every results JSON includes **pipeline_mode**, **llm_backend_id**, and (for llm_live with network) **non_deterministic**. So any downstream tool can tell which pipeline produced a file.
- **Summarize-results:** `labtrust summarize-results --in <paths> --out <dir>` accepts result files from **both** pipelines in a single run. It normalizes to v0.2 shape (task, seeds, agent_baseline_id, episodes) and aggregates by task + baseline + partner_id. You can mix deterministic baseline runs and llm_live runs in one directory and summarize them together to compare scripted vs LLM in one table.
- **Evidence and risk register:** Evidence bundles, verify-bundle, and export-risk-register consume run directories regardless of pipeline_mode. Deterministic runs produce deterministic receipts and hashes; llm_live runs add LLM_DECISION audit entries and (for packs) TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json, which the risk register links when present.
- **What is pipeline-specific:** Baseline regression and official baseline generation use the deterministic pipeline only. Cross-provider pack and CoordinationMatrix build use llm_live runs only. For comparing “scripted vs live” on the same task, run both (e.g. deterministic then llm_live), put both result files in one dir, and run summarize-results on that dir.

### Summary

| Question | Answer |
|----------|--------|
| Do both pipelines make sense by themselves? | Yes. Deterministic for CI/repro/regression; llm_live for live eval and provider comparison. |
| Can they speak to each other? | Yes. Same schema, same summarize-results, same evidence/risk-register flows. Mix result files from both in summarize-results to get one comparison table. |
| When must I use only one? | Baseline regression and official baselines: deterministic only. Cross-provider pack and emit-coordination-matrix: llm_live only. |

## Schema compatibility

Results files remain valid under **results.v0.2** and **results.v0.3**. The **metadata** object is optional and does not break existing consumers. Deterministic runs (scripted or `--llm-backend deterministic`) are unchanged and do not include **metadata** unless an LLM backend was used.
