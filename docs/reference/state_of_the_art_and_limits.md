# State of the art status and limits

This document tracks what is state of the art (SOTA), what is deployment ready, and what is reusable for other users. It aligns with design choices, risk coverage, and the standards-of-excellence checklist.

## State of the art (implemented or documented)

### Scripted baselines (reference, not SOTA)

- **Scripted baselines** are intentionally not state of the art; they are the reference policy for deterministic benchmarking and regression. When no LLM or MARL is used, all four roles (ops, runners, QC, supervisor) are driven by ScriptedOpsAgent, ScriptedRunnerAgent, ScriptedQcAgent, and ScriptedSupervisorAgent. See [Scripted baselines](../agents/scripted_baselines.md).

### Global rate limiter

- **Bounded wait:** When **global_rate_limit_max_wait_s** is set in scale_config (or agent constructor), **act()** waits at most that many seconds for a token from the global rate limiter. No indefinite block. See [Design choices](../architecture/design_choices.md) section 6.2 and [Scale and operational limits](../benchmarks/scale_operational_limits.md).
- **Rate-limited outcome:** If the deadline is exceeded, the agent returns **NOOP** with **reason_code AGENT_RATE_LIMIT** and meta **_rate_limited: True**. Reason code is in `policy/reason_codes/reason_code_registry.v0.1.yaml`.

### Coordination methods (definition of done)

- **Dashboard:** Run `python scripts/refresh_sota_checklist.py` for a per-method table (pass_budget, pass_evidence, strictly_better_test, envelope_yaml, envelope_docstring).
- **Conformance:** `pytest tests/coord_methods/conformance/` runs the contract matrix; skips are in `tests/coord_methods/conformance/conformance_config.yaml`. Remove skips when a method is upgraded to pass.
- **Incremental:** For methods with N in the dashboard, add property and strictly-better tests and document compute/latency envelope where missing. **Envelope script:** `python scripts/run_envelope_per_method.py [--methods METHOD_ID ...] [--out-dir docs/benchmarks/envelopes]` runs a short probe per method and writes `envelope_<method_id>.yaml` with `step_ms_mean`, `step_ms_p95`, `max_agents`, `recommended_hardware`. Methods without an envelope file are noted as "no envelope" in the dashboard. **CBS (MAPF) backend:** See [MAPF backend](../coordination/coordination_methods_how_they_work.md#mapf-backend-adapter-contract). CBS/ECBS/LNS/RHCR are placeholders until a [mapf] dependency is chosen; equivalence test remains skipped.

### R-TOOL-001 (tool selection)

- **Real injector:** **ToolSelectionNoiseInjector** in `src/labtrust_gym/security/risk_injections.py` (mutates action_dict: swap tool_id or corrupt one arg; deterministic). Pack ID **inj_tool_selection_noise** is implemented, not reserved.
- **Dedicated test:** **SEC-TOOL-SELECT-001** with test_ref `test_tool_selection_wrong_tool_blocked_by_registry`. Coverage is active. See [Security attack suite](../risk-and-security/security_attack_suite.md).

### LLM provider errors (429 / timeout)

- **Circuit driven by provider errors:** When a backend sets **last_error_code** after 429/timeout/refusal, **LLMAgentWithShield** calls **circuit_breaker.record_block()**, so consecutive provider failures open the circuit. Backends that implement last_error_code (e.g. openai_live, anthropic_live, ollama_live) drive the circuit. See [LLM live](../agents/llm_live.md) Guardrails section.

### Debate / multi-round protocols

- **Current:** Debate aggregation is deterministic (majority) by default. When `coord_debate_aggregator: llm` and an aggregator backend is configured (e.g. via scale_config or params.aggregator_backend), an LLM merges N proposals into one; on parse/generate failure the method falls back to majority. round_robin is N bidder calls then merge, not full multi-round negotiation. Documented in coordination and llm_coord_trials docs.

### Standards of excellence: vectorized envs

- **Current:** `LabTrustVectorEnv` and `AsyncLabTrustVectorEnv` in `src/labtrust_gym/envs/vectorized.py` wrap N `LabTrustParallelEnv` instances; synchronous or thread-pool-parallel reset/step over the vector, each env gets its own seed. Same agent list and observation/action contract per env. See [Design choices](../architecture/design_choices.md) section 10.1 and [PettingZoo API](../agents/pettingzoo_api.md).

## Deployment readiness

- **Threat model / disclaimer:** "Deployment, key management, and operational security are the responsibility of integrators. The threat model describes what the simulation enforces, not production hardening." Passing all sim tests and gates does **not** imply production safety. See [Systems and threat model](../architecture/systems_and_threat_model.md) and [Threat model](../architecture/threat_model.md).
- **Production checklist:** Treat simulation as one input to assurance, not the whole story. Before production: calibrate thresholds for your environment; run red-team or penetration tests in staging; define production monitoring and rollback. See [Threat model](../architecture/threat_model.md), [Policy pack](../policy/policy_pack.md), and [Production runbook](../operations/production_runbook.md).
- **Critical thresholds:** Shipped thresholds are reference defaults (e.g. RCPath 2017 style), not clinically validated. For production, calibrate per [Policy pack](../policy/policy_pack.md) and production calibration.
- **Default .env loading:** The CLI loads `.env` at startup from the current directory (or `LABTRUST_DOTENV_PATH`), so API keys in `.env` are available for live LLM without sourcing manually. See [Installation](../getting-started/installation.md).
- **CI and production:** CI is described for merge gates; production use of live LLM/network is left to operators. See [CI](../operations/ci.md).
- **Security gate:** No method is recommended for deployment until the coordination security gate passes. See [How to handle security gate failures](../risk-and-security/howto_security_gate_failures.md).
- **Scale / long runs:** Checkpoint and resume are implemented. Use `--log` and `--checkpoint-every N` when running; resume with `--resume-from <run_dir>`. For production-like or very long runs, persistence and checkpointing are recommended. See [Scale and operational limits](../benchmarks/scale_operational_limits.md).
- **labtrust serve:** Request-level protections and multi-key roles are described for production-style use; key management and deployment topology are integrator responsibility. See [Security online](../risk-and-security/security_online.md).

## Reusability for other users

- **Policy path and repo root:** Many code paths use `get_repo_root()` or `LABTRUST_POLICY_DIR`. When installed from wheel, policy is loaded from package data by default; from source, run from repo root (or any subdirectory of the repo) or set **LABTRUST_POLICY_DIR**. See [Installation](../getting-started/installation.md).
- **Extension example:** Two minimal examples demonstrate reuse: **extension_example** (custom task/plugin) and **coord_method_example** (custom coordination method only). See [Extension development](../agents/extension_development.md).
- **Default .env loading:** The CLI loads `.env` at startup; reusers can place API keys in `.env` for live LLM. Documented in Installation.
- **Optional deps and skips:** Without `.[env]` many tests/commands skip; without `.[marl]` PPO is unavailable. Install the extras you need (see [Installation](../getting-started/installation.md) for the table: `[env]`, `[marl]`, `[docs]`, `[full]`). New users can use `pip install -e ".[full]"` to minimize skips. See [CI](../operations/ci.md).
- **Windows path and locale:** Use a simple path (e.g. `C:\LabTrust-Gym`); see [Recommended Windows setup](../getting-started/windows_setup.md) for path, shell, file-lock mitigation (`--skip-system-level` for demos), and locale. See also [Installation](../getting-started/installation.md).
- **Cross-provider / live LLM in release:** The release workflow (`.github/workflows/release.yml`) optionally runs a **live-llm-smoke** job when `OPENAI_API_KEY` is set: healthcheck and official pack llm_live smoke; artifacts are uploaded to the workflow run. The job uses `continue-on-error: true`, so the release succeeds even if the job is skipped or fails. For additional assurance, run the llm_live optional smoke workflow locally and attach artifacts. See [CI](../operations/ci.md) section "Release and live LLM".

- **Generalization and limits:** Results apply to the specified scale grid and injection list only; extrapolation is out of scope. See [Generalization and limits](../coordination/generalization_and_limits.md) for what was tested, what was not, and how to compare with other benchmarks.

## See also

- [Design choices](../architecture/design_choices.md) – Rate limiting, scale, parallel execution
- [LLM live](../agents/llm_live.md) – Pipeline contract, guardrails, definition of done
- [Security attack suite](../risk-and-security/security_attack_suite.md) – Coverage and controls
