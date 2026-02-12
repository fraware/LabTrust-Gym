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
- **Parallel step semantics:** One PettingZoo `step(actions)` runs one engine `step(event)` per agent, in a fixed order (ops_0, runner_0, …, qc_0, supervisor_0). All events in a parallel step use the same `t_s` (clock advances once per parallel step). This keeps the audit log and queue semantics consistent.

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

## Action interface (MVP)

- **Space:** `Discrete(NUM_ACTION_TYPES)` per agent (e.g. 3: NOOP, TICK, QUEUE_RUN).
- **Semantics:** Each action is a discrete index. The wrapper maps it to an engine event (action_type, args, token_refs, reason_code) via `_action_to_event`. Extended actions (e.g. device_id, work_id) can be passed later via a structured action space or `infos` without changing the engine.

Current mapping:

- `0` (NOOP): engine event `action_type="NOOP"`, empty args.
- `1` (TICK): engine event `action_type="TICK"` (door timers, zone breach).
- `2`: `QUEUE_RUN` with a default device and default work_id (for testing).

Actions are deterministic given the same action indices.

## Translation layer (agent action → engine event)

`LabTrustParallelEnv._action_to_event(agent, action)` produces:

- `event_id`, `t_s` (from parallel step count and `dt_s`),
- `agent_id` (engine ID for that PZ agent),
- `action_type`, `args`, `reason_code`, `token_refs`.

The engine’s step contract (status, emits, violations, blocked_reason_code, hashchain) is unchanged; the wrapper does not expose it in the PZ step return except indirectly via rewards/infos.

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

## Tests

- **Smoke:** `tests/test_pz_parallel_smoke.py` — instantiate, `reset(seed=123)`, 50 steps with alternating NOOP/TICK, no crash.
- **Determinism:** Same seed + same actions (NOOP/TICK) → identical trajectory (obs hash, rewards, terminations).
- **Spaces:** Observation and action spaces defined for all agents; sample observation lies in `observation_space`, sample action in `action_space`.

Run with:

```bash
pytest tests/test_pz_parallel_smoke.py -v
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
