# Design choices log

This document is the **reference log of design choices** for LabTrust-Gym. It records why the system is structured as it is and what was decided for orchestration, scale, coordination, security, and backward compatibility. Do not change behavior that contradicts these choices without an explicit design update and version bump.

**Related:** [Frozen contracts](../contracts/frozen_contracts.md), [Simulation, LLMs, and agentic systems](simulation_llm_agentic.md), [Coordination and env](../coordination/coordination_and_env.md).

---

## 1. Orchestration: simulation-centric vs agent-centric

### 1.1 Two modes, same env and action contract

**Choice:** The repo supports two orchestration modes; the **environment** (BenchmarkEnv, LabTrustParallelEnv) and the **action contract** (action_index 0..5, action_type, args, reason_code) are identical in both. Only **who owns the step loop** and **when time advances** differ.

**Rationale:** Keeps a single simulation backend and a single action schema. Benchmarks, metrics, and gates can compare runs across modes without redefining "step" at the env level.

**References:** `src/labtrust_gym/benchmarks/env_protocol.py`, `src/labtrust_gym/envs/action_contract.py`, [simulation_llm_agentic.md](simulation_llm_agentic.md).

### 1.2 Simulation-centric as default

**Choice:** **Simulation-centric** is the default. The **benchmark runner** owns the env and the step loop. Each tick it gets observations, calls the policy (scripted or coordination method), then calls `env.step(actions, action_infos)`. Time advances every tick. No flag means simulation-centric.

**Rationale:** Reproducibility, clear step boundary, single place for security and audit, and alignment with multi-agent simulation benchmarks. Agent-centric is opt-in.

**References:** `run_episode` in `src/labtrust_gym/benchmarks/runner.py`; CLI `run-benchmark` without `--agent-driven`.

### 1.3 Agent-centric as additive, core unchanged

**Choice:** Agent-centric is **additive**. The core `run_episode` loop is **not modified** for agent-centric. The branch is at the **call site**: when `agent_driven=True`, the episode loop calls `run_episode_agent_driven(...)` instead of `run_episode(...)`. No `if agent_driven` inside the simulation-centric loop.

**Rationale:** Prevents regressions in the default path and keeps the choice explicit at the top level.

**References:** `run_benchmark` in `runner.py` (branch around 2454–2493); design plan "Implementation Plan: Scale and Coordination" (agent-driven additive branch).

### 1.4 Agent-centric: single-driver vs multi-agentic

**Choice:** Agent-centric has two sub-modes:

- **Single-driver:** One LLM drives the loop. It calls **step_lab(proposal)** with a full per-agent proposal. Time advances only when the agent calls `step_lab`. No coordination method in the driver; the proposal is validated and shielded then passed to `env.step`.
- **Multi-agentic:** N agent backends (e.g. one per env agent). Each calls **submit_my_action** (or **submit_bid** for auction methods). When all have submitted or a round timeout expires, the driver calls **coord_method.combine_submissions** then runs shield, mutate_actions, and **env.step**. One "step" = one round of N submissions + one advance.

**Rationale:** Single-driver fits small N and one LLM; multi-agentic fits scale with many agentic LLMs without one LLM outputting N actions.

**References:** `AgentDrivenDriver` in `src/labtrust_gym/benchmarks/agent_driven_driver.py` (`mode="single"` vs `mode="multi_agentic"`); `step_lab` vs `submit_my_action` / `try_advance_step`.

---

## 2. Scale and coordination method contract

### 2.1 N_max: propose_actions only for small N

**Choice:** A configurable threshold **N_max** (`coord_propose_actions_max_agents`, default 50) determines the simulation-centric path:

- **N <= N_max:** Runner calls **coord_method.propose_actions(obs, infos, t)** (or `step(context)` for kernel-composed methods). One coordinator sees global state and returns one joint action (one entry per agent). **combine_submissions** is never called.
- **N > N_max:** Runner does **not** call `propose_actions`. It collects one **submission** per agent (from `scripted_agents_map` or NOOP), then calls **coord_method.combine_submissions(submissions, obs, infos, t)** to obtain the joint action. No single entity outputs N actions.

**Rationale:** Having one coordinator output 200 actions is not scalable or realistic; at scale, per-agent policies plus a combine step is the only supported design.

**References:** `runner.py` around 382–455; `scale_config_dict.get("coord_propose_actions_max_agents", 50)`; [coordination_and_env.md](../coordination/coordination_and_env.md).

### 2.2 combine_submissions as the scale API

**Choice:** **combine_submissions(submissions, obs, infos, t)** is the **primary API for playing with multiple agents at scale**. It is used in simulation-centric when N > N_max and in agent-centric multi-agentic. **propose_actions** is used only in simulation-centric when N <= N_max.

**Contract:** Input: `submissions` = one dict per agent (shape defined by method: action, bid, vote); `obs`, `infos`, `t` as in `propose_actions`. Output: joint action dict (agent_id -> action_dict with at least `action_index`). Default implementation (base class): treat each submission as that agent's action; fill missing agents with NOOP.

**Rationale:** Single contract for "many agents, one joint action" across both workflows; methods can override for auction (bids), consensus (votes), etc.

**References:** `CoordinationMethod.combine_submissions` in `src/labtrust_gym/baselines/coordination/interface.py`; [frozen_contracts.md](../contracts/frozen_contracts.md) Coordination baseline contract.

### 2.3 Submission shapes per method

**Choice:** Per method_id, the expected submission shape (action vs bid vs vote) is defined in policy (e.g. `policy/coordination/coordination_submission_shapes.v0.1.yaml` or coordination_methods metadata). The runner and driver use **adapt_submission(shape, action_index, action_info)** so that per-agent output (e.g. from `agent.act()`) fits the shape expected by **combine_submissions** (action dict, bid dict, or vote).

**Rationale:** Auction methods need bids; consensus methods need votes; plain methods need actions. One adapter keeps the env action contract while allowing method-specific submission formats.

**References:** `adapt_submission` in `src/labtrust_gym/policy/coordination.py`; runner combine path (runner.py 388–403); `get_submission_shape`.

---

## 3. Agent-driven driver

### 3.1 Driver holds env; only driver calls env.step

**Choice:** The **AgentDrivenDriver** holds the BenchmarkEnv and is the **only** component that calls `env.reset` and `env.step` in agent-centric mode. The backend(s) never call the env directly; they call driver tools (**step_lab**, **submit_my_action**, **get_current_obs**, **end_episode**).

**Rationale:** Single place for stepping and for applying shield and risk injector; same safety semantics as simulation-centric.

**References:** `agent_driven_driver.py`; `step_lab`, `try_advance_step` (multi-agentic).

### 3.2 step_lab takes proposal, not raw actions

**Choice:** **step_lab(proposal)** accepts a **proposal** in the same format as the coordination contract (per_agent list with agent_id, action_type, args, reason_code). The driver runs **validate_proposal** and **get_actions_from_proposal** (shield + RBAC) to convert proposal to (actions, action_infos). It does not accept raw (actions, action_infos) from the agent.

**Rationale:** Reuses the same validation and shield path as the rest of the codebase; one code path for safety.

**References:** `step_lab` in `agent_driven_driver.py`; `validate_proposal`, `get_actions_from_proposal` in baselines/coordination.

### 3.3 Shield applied after combine in multi-agentic

**Choice:** In multi-agentic mode, submissions are stored raw in **pending_submissions**. When **try_advance_step** runs, it calls **combine_submissions** to get the joint action dict, then builds a **synthetic proposal** from that dict and runs **get_actions_from_proposal(..., apply_shield, ...)**. So the shield is applied **after** combine and **before** mutate_actions and env.step. No submission bypasses the shield.

**Rationale:** Parity with single-driver (step_lab uses get_actions_from_proposal); second line of defense so that even if an agent backend is compromised, the combined action is still shielded.

**References:** `try_advance_step` in `agent_driven_driver.py` (after combine_submissions, before mutate_actions).

### 3.4 Thread safety and round timeout (multi-agentic)

**Choice:** **pending_submissions** is protected by a **threading.Lock**. **submit_my_action** and **submit_bid** write under the lock; **try_advance_step** reads and clears under the lock. **is_done** and **reset** also use the lock for _done and _pending_submissions. A **round_timeout_s** (configurable, default 60s) is enforced: when the time since the first submission of the round exceeds it, **try_advance_step(force=True)** is used (missing agents filled with NOOP, timed-out agents logged).

**Rationale:** Multiple backends may call submit from different threads; without a lock the dict can corrupt. Timeout prevents one slow agent from blocking the episode indefinitely.

**References:** `agent_driven_driver.py`: `_lock`, `_round_start`, `_round_timeout_s`; timeout check inside `try_advance_step`; ParallelMultiAgenticBackend uses `wait(futures, timeout=...)` and then `try_advance_step(force=True)`.

### 3.5 step_lab disabled in multi-agentic; submit_my_action disabled in single

**Choice:** In **multi_agentic** mode, **step_lab** is not used to advance the env (the driver advances only via **try_advance_step** after submissions). In **single** mode, **submit_my_action** and **submit_bid** return an error payload (`"multi_agentic_only"`) and do not store anything.

**Rationale:** Clear separation of modes; avoids mixing single-driver and multi-agentic in one episode.

**References:** `submit_my_action` / `submit_bid` check `_mode != "multi_agentic"`; `try_advance_step` checks `_mode != "multi_agentic"`.

---

## 4. Risk injector and safety

### 4.1 Same risk injector interface in both modes

**Choice:** The **RiskInjector** interface (reset, mutate_obs, mutate_actions, observe_step) is unchanged. In simulation-centric, the runner calls these in order: mutate_obs before policy, mutate_actions before env.step, observe_step after step. In agent-centric, the driver calls the same hooks at the same logical points (mutate_obs before returning obs to the agent / after step; mutate_actions before env.step; observe_step after step).

**Rationale:** One harness for adversarial testing and detection; same semantics regardless of who drives the loop.

**References:** `runner.py` (mutate_obs, mutate_actions, observe_step); `agent_driven_driver.py` (reset, get_current_obs, step_lab, try_advance_step); `src/labtrust_gym/security/risk_injections.py`.

### 4.2 Shield in runner vs driver

**Choice:** In **simulation-centric**, the runner does not apply a separate "shield" on the joint action dict produced by propose_actions or combine_submissions. For the combine path, each per-agent policy can be an **LLMAgentWithShield**, so the shield runs inside **agent.act()**. In **agent-centric single**, the shield is applied inside **step_lab** via **get_actions_from_proposal**. In **agent-centric multi-agentic**, the shield is applied inside **try_advance_step** after combine_submissions (see 3.3).

**Rationale:** In simulation-centric combine path, per-agent LLM already goes through the shield; in agent-centric, the driver is the single point that steps the env, so applying shield there guarantees no raw proposal or combined action reaches env.step without being checked.

**References:** Runner does not call apply_shield on the joint dict; driver calls get_actions_from_proposal in step_lab and try_advance_step.

### 4.3 No runner-level shield on propose_actions / step(context) path

**Choice:** In simulation-centric mode, when the runner calls **propose_actions** or **step(context)** (N <= N_max), it does **not** apply a shield to the joint action dict. Shield is applied only: (a) in the combine path, inside each per-agent LLM's act(), and (b) in agent-centric mode, in the driver (step_lab / try_advance_step). So "all actions go through the shield" is true only in those paths; the classic single-coordinator propose_actions path has no runner-level shield. The engine still enforces RBAC, signatures, and invariants on every action.

**Rationale:** Single coordinator is trusted in that path; the shield is primarily for agent/LLM output. Engine enforcement remains the safety boundary.

**Assumption and limits:** The single coordinator is *assumed* trusted on this path; we do not verify correctness or safety. Engine RBAC and invariants are the only enforcement. Integrators who cannot assume a trusted coordinator should use a path that applies a shield (e.g. agent-centric or combine path) or enable the optional runner-level shield via scale_config `apply_runner_shield_on_propose_actions: true` (when implemented). Determinism means same inputs to same outputs; it does **not** imply correctness or safety. A deterministic coordinator can still emit schema-valid but unsafe or policy-violating actions. Safety is not guaranteed on the unshielded path. When `apply_runner_shield_on_propose_actions` is true, the runner applies a shield even for deterministic coordinators.

---

## 5. Security suite and gates

### 5.1 Agent/shield tests without PZ env

**Choice:** **scenario_ref** and **llm_attacker** attacks in the security suite do **not** run the PZ env. They use **synthetic observations** and call the agent (e.g. LLMAgentWithShield.act) with the same observation shape as the env. Pass/fail is based on whether the action is in **allowed_actions_for_assert** (from locked assertion policy). So the same agent and shield code path are tested without starting the simulator.

**Rationale:** Fast, deterministic, CI-safe; no dependency on env for prompt-injection and LLM-attacker regression.

**References:** `_run_prompt_injection_attack`, `_run_llm_attacker_attack` in `security_runner.py`; [security_attack_suite.md](../risk-and-security/security_attack_suite.md).

### 5.2 Agent-driven mode in security suite

**Choice:** When **agent_driven_mode** is `"single"` or `"multi_agentic"`, the suite dispatches **scenario_ref** and **llm_attacker** to **\_run_agent_driven_scenario_ref_attack** and **\_run_agent_driven_llm_attacker_attack**. With **use_full_driver_loop** a full driver loop (env + AgentDrivenDriver + run_episode_agent_driven) runs and asserts on step results. With **use_mock_env** (and use_full_driver_loop), **MockBenchmarkEnv** is used instead of LabTrustParallelEnv so agent/shield regression runs without CoreEnv or full sim (see benchmarks/mock_env.py and run-security-suite --use-mock-env).

**Rationale:** One assertion implementation; agent-driven mode is a dispatch option for consistency and future expansion.

**References:** `run_security_suite` in `security_runner.py` (agent_driven_mode); `_run_agent_driven_scenario_ref_attack`, `_run_agent_driven_llm_attacker_attack`.

### 5.3 coord_pack_ref and multi_agentic

**Choice:** **coord_pack_ref** entries in the security suite run the coordination security pack (same as `run-coordination-security-pack`). When the ref is a dict with **multi_agentic: true**, **run_coordination_security_pack** is called with **multi_agentic=True**, so those cells run the **agent-centric multi-agentic** loop (driver + N backends + combine + risk injectors) under the same gate rules. Step counting for gates is "one round = one step" in that case.

**Rationale:** The combine path and multi-agentic driver are exercised under attack; gate thresholds (attack_success_rate_zero, etc.) apply unchanged.

**References:** `_run_coord_pack_ref_attack` in `security_runner.py`; `run_coordination_security_pack(multi_agentic=...)`; [coordination_security_pack_gate.v0.1.yaml](https://github.com/fraware/LabTrust-Gym/blob/main/policy/coordination/coordination_security_pack_gate.v0.1.yaml).

### 5.4 Step semantics for gates

**Choice:** Gate thresholds (max_steps, detection_within_steps, time_to_attribution_steps_below, etc.) use the same **step** definition everywhere:

- **Simulation-centric:** One runner loop iteration = one step.
- **Agent-centric single:** One **step_lab** call = one step.
- **Agent-centric multi-agentic:** One round (N submissions + **try_advance_step**) = one step.

This is documented in **coordination_security_pack_gate.v0.1.yaml** (top-level comment) and in **docs/risk-and-security/security_attack_suite.md**.

**Rationale:** So that gate evaluation is consistent across modes and "step" is unambiguous for metrics and thresholds.

**References:** `policy/coordination/coordination_security_pack_gate.v0.1.yaml`; `docs/risk-and-security/security_attack_suite.md` (Step semantics for gates).

---

## 6. Scale: per-agent LLM and rate limiting

### 6.1 Per-agent LLM population when N > N_max

**Choice:** When a scale task uses LLM agents and **N > N_max**, the runner **populates scripted_agents_map** with one **LLMAgentWithShield** per agent_id. All share one backend instance (e.g. OpenAILiveBackend or DeterministicConstrainedBackend) and an optional **global rate limiter** (TokenBucket). Each agent has its own RateLimiter, CircuitBreaker, and shield context.

Two code paths contribute to this population:

**(a) Per-method population (llm_constrained branch):** When `coord_method_for_branch == "llm_constrained"` and N > n_max, the runner builds one LLMAgentWithShield per agent and fills scripted_agents_map in that branch (reference `runner.py` around 1168–1188).

**(b) Shared scale-capable block:** After scripted_agents_map is initialized for the task, a second block runs when the coordination method is in the **scale-capable set** (see §6.3), is_scale_task, and N > n_max. It populates scripted_agents_map with one LLMAgentWithShield per agent (shared backend and optional global rate limiter). This applies to any method in the scale-capable set, including llm_central_planner and llm_constrained when so marked in policy. Reference `runner.py` around 2357–2440.

**Rationale:** So the simulation-centric combine path actually uses N LLM agents instead of one coordinator outputting N actions; shared backend and global rate limiter keep API usage bounded. The scale-capable set is defined in policy (§6.3).

**References:** `runner.py` ~1168–1188 (llm_constrained branch); `runner.py` ~2357–2440 (shared scale-capable block); §6.3 for scale-capable set.

### 6.2 Global rate limiter optional

**Choice:** **LLMAgentWithShield** accepts an optional **global_rate_limiter** (e.g. TokenBucket). When set, **act()** waits on it (short sleep loop) before calling the backend. Default is **None** (no global cap) for backward compatibility. The runner or ParallelMultiAgenticBackend creates one TokenBucket when needed and passes it to all agent instances.

**Bounded wait and rate_limited outcome:** When **global_rate_limit_max_wait_s** is set (e.g. via scale_config or agent constructor), **act()** waits at most that many seconds for a token. If the deadline is exceeded, the agent returns **NOOP** with **reason_code AGENT_RATE_LIMIT** and meta **_rate_limited: True** (no indefinite block). If global_rate_limit_max_wait_s is **None** (default), the wait loop has no timeout (backward compatible). Set **global_rate_limit_max_wait_s** in scale_config (e.g. 60.0) for production-style bounded wait. Reason code **AGENT_RATE_LIMIT** is in `policy/reason_codes/reason_code_registry.v0.1.yaml`.

**Rationale:** With 200 agents and one API key, aggregate calls would exceed provider limits without a shared cap.

**References:** `LLMAgentWithShield` in `src/labtrust_gym/baselines/llm/agent.py`; `TokenBucket` in `src/labtrust_gym/online/rate_limit.py`; runner and ParallelMultiAgenticBackend construction.

### 6.3 Scale-capable methods

**Choice:** **Scale-capable methods** are those that support the combine path with per-agent LLM at N > N_max. The set is configured in policy: in `policy/coordination/coordination_methods.v0.1.yaml`, a method entry may set **scale_capable: true**. The runner derives the set via `list_scale_capable_method_ids(reg_path)` (in `src/labtrust_gym/policy/coordination.py`). For backward compatibility, if no method in the registry has scale_capable set to true, the effective set falls back to {llm_constrained, llm_central_planner}.

**Rationale:** So new scale-capable methods can be added without code changes; a single source of truth in policy.

**References:** `policy/coordination/coordination_methods.v0.1.yaml`; `list_scale_capable_method_ids` in `src/labtrust_gym/policy/coordination.py`; runner scale-capable block (~2357–2440).

---

## 7. Parallel execution (multi-agentic)

### 7.1 ParallelMultiAgenticBackend

**Choice:** **ParallelMultiAgenticBackend** runs one **ThreadPoolExecutor** per episode. Each step round it submits one future per agent; each future runs a per-agent backend that calls **driver.submit_my_action** (or submit_bid). The main thread **waits** with a timeout (**round_timeout_s**); on timeout it cancels stragglers and calls **driver.try_advance_step(force=True)**. The next round does not start until **try_advance_step** has returned (step-epoch fence). **round_timeout_s**, **max_workers**, and optional **global_rate_limit_rps** / **global_rate_limit_capacity** are configurable via `run_benchmark(round_timeout_s=..., parallel_multi_agentic_max_workers=...)` or, for scale tasks, via scale_config dict keys (same names). Recommended: round_timeout_s 60s, max_workers min(N, 64).

**Rationale:** So N agent backends can run in parallel without blocking each other; timeout and force advance avoid deadlock.

**References:** `ParallelMultiAgenticBackend` in `agent_driven_driver.py`; `concurrent.futures.ThreadPoolExecutor`, `wait(..., timeout=...)`.

### 7.2 No change to sequential DeterministicMultiAgenticBackend

**Choice:** **DeterministicMultiAgenticBackend** remains sequential (for each agent, submit_my_action then try_advance_step when all submitted). Parallel execution is an **additional** backend (ParallelMultiAgenticBackend), not a replacement.

**Rationale:** Deterministic backend is simpler and sufficient for tests and small N; parallel is for scale and optional.

**References:** `DeterministicMultiAgenticBackend` in `agent_driven_driver.py`.

---

## 8. CLI and pipeline

### 8.1 Flags for agent-centric and multi-agentic

**Choice:** **run-benchmark** accepts **--agent-driven** (agent-centric) and **--multi-agentic** (multi-agentic mode). Defaults: no flag => simulation-centric; **--agent-driven** alone => agent-centric single-driver (multi_agentic=False). So **--agent-driven --multi-agentic** is required for N agent backends + combine path.

**Rationale:** Explicit user choice; backward compatible (defaults preserve current behavior).

**References:** `cli/main.py` run-benchmark parser; `run_benchmark(agent_driven=..., multi_agentic=...)` in runner.py.

### 8.2 run-security-suite agent_driven_mode

**Choice:** **run-security-suite** accepts **--agent-driven-mode single | multi_agentic**. When set, scenario_ref and llm_attacker use the agent-driven entry points. Default is **None** (simulation-centric only for those attacks). coord_pack_ref is independent and uses its own **multi_agentic** in the ref dict.

**Rationale:** So the security suite can target agent-driven flows without changing the default (deterministic, no env for scenario_ref/llm_attacker).

**References:** `security_runner.py` run_security_suite(agent_driven_mode=...); CLI --agent-driven-mode.

---

## 9. Backward compatibility

### 9.1 N <= N_max path unchanged

**Choice:** When N <= N_max, the runner continues to call **propose_actions** (or step(context)); **combine_submissions** is not used. No behavioral change for existing small-N benchmarks.

**Rationale:** Existing studies and gates that assume one coordinator per step remain valid.

**References:** Runner branch `use_combine = len(env.agents) > n_max and hasattr(coord_method, "combine_submissions")`; tests in test_backward_compat.py.

### 9.2 run_episode unchanged

**Choice:** The body of **run_episode** is not modified to support agent-centric. The branch is in **run_benchmark**: if agent_driven, call **run_episode_agent_driven**; else call **run_episode**. So all existing callers of run_episode see the same behavior.

**Rationale:** Reduces risk of regressions in the default simulation-centric path.

**References:** runner.py episode loop (no "if agent_driven" inside run_episode).

### 9.3 Metrics and result schema shared

**Choice:** **compute_episode_metrics** and the results schema (steps, throughput, violations, etc.) are the same for both modes. The driver collects **step_results_per_step** and **t_s_list** in the same format as the runner; **run_episode_agent_driven** calls **compute_episode_metrics** with the same signature. So one run (simulation-centric or agent-centric) produces a valid results.json and comparable metrics.

**Rationale:** So gates, summaries, and papers can use the same metrics regardless of mode.

**References:** `run_episode_agent_driven` in agent_driven_driver.py; `compute_episode_metrics` in metrics.py; step_results_per_step, t_s_list format.

---

## 10. Extensions: implemented and future

### 10.1 Vectorized envs (implemented)

**Implemented:** `LabTrustVectorEnv` in `src/labtrust_gym/envs/vectorized.py` holds N `LabTrustParallelEnv` instances in one process; synchronous `reset(seed, options)` and `step(actions_list)` over the vector. Each env gets seed `base_seed + env_index`. The wrapper respects the existing LabTrust env API: `reset(options=...)` (including `timing_mode`, `dt_s`), same agent list and observation/action contract per env. **Async/await:** `reset_async()` and `step_async()` are provided for async training loops (implemented via `asyncio.to_thread`); same return shapes as sync. **AsyncLabTrustVectorEnv** runs reset/step in parallel via a thread pool (same sync API; no separate async/await). Use for overlapping env stepping when steps release the GIL; tune `max_workers` for large N. Entry points (e.g. which benchmarks or studies use vectorized envs) can be added when needed.

**References:** [pettingzoo_api.md](../agents/pettingzoo_api.md) (single-env and vectorized usage); [scale_operational_limits.md](../benchmarks/scale_operational_limits.md) (at-scale profile).

---

## 11. Summary table

| Area | Choice | Default / when |
|------|--------|-----------------|
| Orchestration | Simulation-centric = runner drives loop; agent-centric = driver + agent(s) drive | Simulation-centric |
| Scale threshold | N_max = coord_propose_actions_max_agents (default 50) | 50 |
| At scale (sim) | Per-agent submissions + combine_submissions; no propose_actions | When N > N_max |
| Agent-centric single | step_lab(proposal); no submit_my_action | When --agent-driven, not --multi-agentic |
| Agent-centric multi | submit_my_action / submit_bid; try_advance_step; combine_submissions | When --agent-driven --multi-agentic |
| Shield in multi-agentic | After combine_submissions, before mutate_actions (in try_advance_step) | Always in driver |
| Risk injector | Same interface; runner and driver call mutate_obs, mutate_actions, observe_step | Both modes |
| Security scenario_ref/llm_attacker | No PZ env; synthetic obs; agent.act; assert allowed_actions | Default; agent_driven_mode optional |
| coord_pack_ref | Runs coordination security pack; multi_agentic in ref => agent-centric multi | Optional in suite |
| Step for gates | Sim: one loop iter; single: one step_lab; multi: one round | Documented in gate YAML and security docs |
| Per-agent LLM at scale | scripted_agents_map filled with one LLMAgentWithShield per agent when N > N_max | When llm_agents + scale task |
| Global rate limiter | Optional TokenBucket passed to all LLM agents | When many agents share one backend |
| Parallel multi-agentic | ParallelMultiAgenticBackend with ThreadPoolExecutor + timeout | Optional backend |
| run_episode | No agent-centric logic inside; branch in run_benchmark | Invariant |

---

*Document version: 1.0. Last updated to reflect current codebase (scale, coordination, agent-driven driver, security suite, parallel execution, backward compatibility, future extensions).*
