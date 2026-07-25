# PettingZoo Parallel API

LabTrust-Gym exposes a **PettingZoo Parallel** environment wrapper so you can use standard multi-agent RL tooling (CleanRL, RLlib, SB3, etc.) without refactoring the engine internals.

## Installation

The wrapper depends on PettingZoo and Gymnasium. Install the optional extra:

```bash
pip install labtrust-gym[env]
# or from source: pip install -e ".[env]"
```

This adds `pettingzoo>=1.24` and `gymnasium>=0.29`. The rest of the package works without them; only the Parallel env and its tests require `[env]`. When installed from a wheel, policy is bundled; when developing from source, policy is read from the repo `policy/` directory (or set `LABTRUST_POLICY_DIR`).

## Basic usage

```python
from labtrust_gym.envs import LabTrustParallelEnv

env = LabTrustParallelEnv(num_runners=2)
observations, infos = env.reset(seed=42)

while env.agents:
    actions = {a: env.action_space(a).sample() for a in env.agents}
    observations, rewards, terminations, truncations, infos = env.step(actions)

env.close()
```

## AEC (Agent-Environment Cycle) usage

An **AEC** wrapper is provided on top of the Parallel env via PettingZoo’s `parallel_to_aec` conversion (no duplicated logic). Use it when you need sequential stepping, `agent_selection`, and `observe()` / `step(action)` semantics:

```python
from labtrust_gym.envs import labtrust_aec_env

env = labtrust_aec_env(num_runners=2)
env.reset(seed=42)

while env.agents:
    agent = env.agent_selection
    obs, reward, term, trunc, info = env.last()
    action = env.action_space(agent).sample()
    env.step(action)

env.close()
```

The AEC env cycles through agents in order; observation and action spaces are the same as the Parallel env. Determinism: same seed and same action sequence yield the same trajectory (see `tests/test_pz_aec_smoke.py`).

## Design rationale

- **Engine unchanged:** The wrapper uses the existing `CoreEnv` (reset, step, query). No refactor of engine internals; the engine remains the single source of truth for lab physics, trust skeleton, and contract output.
- **Determinism:** `reset(seed=...)` and `seed(seed)` set the RNG; the engine is reset with `deterministic=True` and `rng_seed=seed`. Same seed + same action sequence yields identical observations and rewards.
- **Parallel step semantics:** One PettingZoo `step(actions)` runs one engine `step(event)` per agent, in a fixed order (ops_0, runner_0, …, qc_0, supervisor_0). All events in a parallel step use the same `t_s` (clock advances once per parallel step). This keeps the audit log and queue semantics consistent. When the engine supports `step_batch(events)`, the wrapper calls it once per parallel step; otherwise it calls `step(event)` in a loop. `step_batch` processes events in the supplied order; contention (e.g. two agents claiming the same queue head) is resolved by order of execution (same semantics as calling `step()` N times). See **How the simulation works** below for a consolidated overview.

## Agent set

| Agent       | Role (conceptual) | Engine agent_id   | Default zone           |
|------------|-------------------|-------------------|------------------------|
| `ops_0`    | Scheduler         | `A_OPS_0`         | Z_ANALYZER_HALL_A      |
| `runner_0` … `runner_k` | Runners  | `A_RUNNER_0` …    | Z_SORTING_LANES        |
| `qc_0`     | QC                | `A_QC_0`          | Z_QC_SUPERVISOR        |
| `supervisor_0` | Supervisor    | `A_SUPERVISOR_0`  | Z_QC_SUPERVISOR        |

`num_runners` is configurable in the constructor (default 2). All agents are always present (`possible_agents` is fixed).

## Observation spec (stable, compact)

Per-agent observation is a **dict of numpy arrays** (no raw secrets). All agents share the same structure; content is global state plus the agent’s own position.

| Key                      | Type / shape      | Description |
|--------------------------|-------------------|-------------|
| `my_zone_idx`            | Discrete(n_zones+1) | Agent’s current zone (index into fixed zone list; 0 = unknown). |
| `door_restricted_open`   | 0/1               | Restricted airlock door open (1) or closed (0). |
| `door_restricted_duration_s` | float(1,)      | Seconds the restricted door has been open (0 if closed). |
| `restricted_zone_frozen` | 0/1               | Restricted zone state: 1 = frozen (breach), 0 = normal. |
| `queue_lengths`          | int32(n_devices)  | Per-device queue length. |
| `queue_has_head`         | int8(n_devices)   | 1 if device queue has a head, 0 otherwise. |
| `specimen_status_counts` | int32(8)          | Counts for statuses: arrived_at_reception, accessioning, accepted, held, rejected, in_transit, separated, unknown. |
| `device_qc_pass`         | int8(n_devices)   | 1 = pass, 0 = fail (or drift) per device. |
| `log_frozen`             | 0/1               | Audit log frozen (forensic freeze). |
| `token_count_override`  | int32(1)          | Count of active OVERRIDE-style tokens (no secrets). |
| `token_count_restricted`| int32(1)          | Count of active RESTRICTED_ENTRY-style tokens. |

Zones and devices use fixed lists aligned with the engine’s default layout (`DEFAULT_ZONE_IDS`, `DEFAULT_DEVICE_IDS` in `pz_parallel.py`).

## Action interface

- **Space:** `Discrete(NUM_ACTION_TYPES)` per agent with `NUM_ACTION_TYPES = 6` (indices **0..5**).
- **Semantics:** Each action is a discrete index. The wrapper maps it to an engine event (action_type, args, token_refs, reason_code) via `_action_to_event`. Extended args (e.g. device_id, work_id, to_zone) can be passed via `action_infos` without changing the engine.

Current mapping (see `envs/action_contract.py`):

| Index | Constant | Engine `action_type` |
|------:|----------|----------------------|
| `0` | `ACTION_NOOP` | `NOOP` |
| `1` | `ACTION_TICK` | `TICK` |
| `2` | `ACTION_QUEUE_RUN` | `QUEUE_RUN` |
| `3` | `ACTION_MOVE` | `MOVE` |
| `4` | `ACTION_OPEN_DOOR` | `OPEN_DOOR` |
| `5` | `ACTION_START_RUN` | `START_RUN` |

Actions are deterministic given the same action indices (and optional `action_infos`).

**Observation note:** The declared Dict RL space covers the compact numeric fields listed above. The Parallel env may also attach LLM/context keys (`zone_id`, `work_list`, `role_id`, …) on the same observation dict. PettingZoo `api_test` requires `observation_space.contains(obs)`; official AEC conformance tests therefore project observations onto declared space keys (see `envs/api_conformance.py`). `parallel_api_test` runs on the raw Parallel env. For MARL, prefer `FlattenObsWrapper` / `LabTrustGymnasiumWrapper`.

## Translation layer (agent action → engine event)

`LabTrustParallelEnv._action_to_event(agent, action)` produces:

- `event_id`, `t_s` (from parallel step count and `dt_s`),
- `agent_id` (engine ID for that PZ agent),
- `action_type`, `args`, `reason_code`, `token_refs`.

The engine’s step contract (status, emits, violations, blocked_reason_code, hashchain) is unchanged; the wrapper surfaces it only indirectly in the PZ step return via rewards and infos.

## Rewards

- **Default:** All agents get reward `0` each step.
- **Hooks (optional, via `reward_config`):**
  - `throughput_reward`: scalar added when a result is released (emits contain `RELEASE_RESULT`).
  - `violation_penalty`: scalar × violation count (from engine step responses).
  - `blocked_penalty`: scalar × number of BLOCKED steps in that parallel step.

Example:

```python
env = LabTrustParallelEnv(
    num_runners=2,
    reward_config={
        "throughput_reward": 1.0,
        "violation_penalty": 0.1,
        "blocked_penalty": 0.05,
    },
)
```

Rewards are per agent; in the default config every agent gets the same shared reward components. Custom per-agent reward can be added later without changing the engine.

## Seeding and determinism

- `env.reset(seed=42)` — recommended: sets internal seed and resets the engine with `rng_seed=42`.
- `env.seed(42)` then `env.reset()` — equivalent to `reset(seed=42)`.
- Same `seed` and same sequence of `step(actions)` must yield the same sequence of (observations, rewards, terminations). Tests in `tests/test_pz_parallel_smoke.py` enforce this (e.g. hashing observations and comparing two runs).

**Reset options:** `reset(seed=..., options={...})` accepts optional keys: `initial_state` (dict passed to the engine), `timing_mode` (e.g. `"explicit"` or `"simulated"`, injected into initial state for the engine), and `dt_s` (integer, updates the env’s time step for the new episode).

## How the simulation works

- **CoreEnv** is the underlying simulator: one event per `step(event)` call, or a batch via `step_batch(events)` when supported.
- **PettingZoo `step(actions)`** runs N sequential engine steps at the same `t_s`, in fixed agent order (ops_0, runner_0, …, qc_0, supervisor_0). The wrapper builds one event per agent, then calls `step_batch(events)` if the engine supports it, else `step(event)` in a loop.
- **Observations.** Shared state is collected with `query_many`; per-agent data (zone, role) uses batch `get_agent_zones` / `get_agent_roles` when available. Results are cached per step so multiple consumers share one computation.
- **Determinism:** Same `seed` and same action sequence yield the same trajectory. Fixed agent ordering is part of the contract.
- **Rendering:** With `render_mode="ansi"` or `"human"`, `render()` returns or prints a text summary of the current state (see Rendering below).

## Rendering

When `render_mode` is set in the constructor, `render()` is supported:

- **`render_mode="ansi"`:** `render()` returns a multi-line string summarizing current state (step count, episode time, agent zones/roles, door status, queue lengths, specimen counts).
- **`render_mode="human"`:** `render()` prints the same string to stdout and returns `None`.
- **`render_mode=None` (default):** `render()` returns `None` (no-op).

State for the summary comes from the same observation cache used by `step()` and `get_timing_summary()`; no extra engine queries are performed.

**Wrappers:** For algorithms that expect a single flat observation vector per agent, use `FlattenObsWrapper` from `labtrust_gym.baselines.marl` (or `sb3_wrapper`). It wraps any LabTrust Parallel env and exposes `observation_space(agent)` as a `Box`; `reset()` and `step()` return flattened float32 vectors. See `tests/test_pz_parallel_smoke.py::test_flatten_obs_wrapper_smoke`.

## Tests

- **Smoke:** `tests/test_pz_parallel_smoke.py` — instantiate, `reset(seed=123)`, 50 steps with alternating NOOP/TICK, no crash.
- **Determinism:** Same seed + same actions (NOOP/TICK) → identical trajectory (obs hash, rewards, terminations).
- **Spaces:** Observation and action spaces defined for all agents; projected observation (Dict space keys) lies in `observation_space`; actions are Discrete **0..5**.
- **Official API:** `tests/test_pz_api_conformance.py` — PettingZoo `parallel_api_test` on `LabTrustParallelEnv`, `api_test` on AEC+`FlattenObsWrapper` (Box), Dict.contains via space projection, lifecycle/seeding/parallel–AEC equivalence.
- **Gymnasium:** `tests/test_gymnasium_check_env.py` — `gymnasium.utils.env_checker.check_env` on `LabTrustGymnasiumWrapper`.

Run with:

```bash
pytest tests/test_pz_parallel_smoke.py tests/test_pz_aec_smoke.py tests/test_pz_api_conformance.py tests/test_gymnasium_check_env.py -v
```

Requires `.[env]`. The golden suite remains unchanged and still passes with `LABTRUST_RUN_GOLDEN=1`.

## Optional engine queries used by the wrapper

The wrapper uses only the public engine API (`reset`, `step`, `query`). It relies on these query forms (already implemented):

- `agent_zone('AGENT_ID')` — agent’s current zone (for `my_zone_idx`).
- `door_state('D_RESTRICTED_AIRLOCK')` — `{open, open_since_ts, open_duration_s}`.
- `zone_state('Z_RESTRICTED_BIOHAZARD')` — `'normal'` or `'frozen'`.
- `queue_length('DEV_ID')`, `queue_head('DEV_ID')`.
- `specimen_counts` — dict of status → count.
- `device_qc_state('DEV_ID')` — `'pass'` or `'fail'`.
- `system_state('log_frozen')` — `'true'` / `'false'`.
- `token_active` — list of active token IDs (wrapper only counts by type, no secrets).

No engine internals are refactored; only minimal query support was added where needed for the observation spec.

## Relationship to LLMs and agentic systems

**PettingZoo** (LabTrustParallelEnv) implements **BenchmarkEnv** and is the **simulation backend** for benchmarks. In the default (simulation-centric) mode, the **benchmark runner** is the only component that calls `env.step`; LLM agents and coordination methods are policies that receive observations and return actions. For runs without LLM or MARL, **scripted baselines** — deterministic, hand-coded reference policies — fill those roles for comparison and reproducibility. State-of-the-art control in this repo is the OR kernel, LLM coordination methods, and MARL PPO. QC and supervisor are part of the agent set and are driven by ScriptedQcAgent and ScriptedSupervisorAgent in the default benchmark setup unless a coordination method or task config overrides them. For where "state of the art" is defined in this repo, see [State of the art status and limits](../reference/state_of_the_art_and_limits.md) and [Coordination benchmark card](../coordination/coordination_benchmark_card.md) (baselines for SOTA comparison). In **agent-driven** mode (`run-benchmark --agent-driven`), a driver holds the env and steps it only when the agent calls the step_lab tool. The security suite uses the PZ env for system-level coordination-under-attack (coord_pack_ref); agent/shield tests use synthetic observations and skip the env. For a single diagram and full breakdown, see [Simulation, LLMs, and agentic systems](../architecture/simulation_llm_agentic.md).

**Vectorized env:** Implemented in `src/labtrust_gym/envs/vectorized.py`. `LabTrustVectorEnv` holds N `LabTrustParallelEnv` instances; `reset(seed, options)` and `step(actions_list)` operate on all envs synchronously. Each env gets seed `base_seed + env_index`. Same agent list and observation/action contract per env. **AsyncLabTrustVectorEnv** runs reset/step in parallel via a thread pool (same API; use for overlapping stepping when steps release the GIL). See [Design choices](../architecture/design_choices.md) (section 10.1).
