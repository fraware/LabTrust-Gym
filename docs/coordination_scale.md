# Coordination scale generator

Deterministic generation of large lab scenarios (many agents, specimens, devices, sites) for coordination benchmarks without changing frozen contracts (runner output v0.1, queue contract v0.1).

## Goal

Compare coordination methods at scale by producing reproducible `initial_state` and policy overlays from a compact **scale config**. Same `(seed_base, scale_config, partner_id)` yields identical generated state across runs.

## Scale config

**`CoordinationScaleConfig`** (in `src/labtrust_gym/benchmarks/coordination_scale.py`):

| Field | Type | Description |
|-------|------|-------------|
| `num_agents_total` | int | Total number of agents (IDs: A_WORKER_0001, A_WORKER_0002, ...). |
| `role_mix` | dict | `role_id -> fraction`; must sum to 1.0. Roles from base RBAC (e.g. ROLE_RUNNER, ROLE_ANALYTICS). |
| `num_devices_per_type` | dict | `device_type -> count`. Device IDs: DEV_{type}_{k:04d}. |
| `num_sites` | int | Number of sites (SITE_001, ...). Sites policy and routes built deterministically. |
| `specimens_per_min` | float | Arrival rate for specimen backlog and arrival schedule. |
| `horizon_steps` | int | Episode length (max_steps). |
| `timing_mode` | "explicit" \| "simulated" | Clock and device timing. |
| `partner_id` | optional str | Partner overlay ID; base policy merged with overlay when set. |

## Generator

**`generate_scaled_initial_state(scale, base_policy_root, seed) -> dict`**

- Builds **agents** with stable IDs and assigns roles from `role_mix` (deterministic RNG).
- Builds **device_placement** and **equipment_registry** from `num_devices_per_type`; places devices in zones by type.
- Builds **sites_policy** (sites, site_graph, routes) for `num_sites`.
- Builds **zone_layout** from base layout and overrides `device_placement` (or minimal layout if no base file).
- Builds **initial specimen backlog** and **arrival_schedule** from `specimens_per_min` and `horizon_steps` using the seed RNG.
- Returns `initial_state` with `effective_policy` (zone_layout, equipment_registry, rbac_policy.agents, sites_policy). Does not write policy files to disk.

The engine accepts **zone_layout** and **effective_policy** from `initial_state` (and `effective_policy.zone_layout`), so no file I/O is required for scale runs.

## Emit and auditability

Every scale run emits **COORD_SCALE_CONFIG** once at episode start (on the first step result). The payload is a sanitized copy of the scale config (no Paths, JSON-serializable) and is stored in `initial_state["_scale_config_sanitized"]`; the emit type is added to the engine step result so it appears in step outputs and logs. **COORD_SCALE_CONFIG** is in the emits vocab (`policy/emits/emits_vocab.v0.1.yaml`).

## Tasks

- **TaskG_COORD_SCALE**: Coordination at scale under nominal conditions. Uses a default small scale (10 agents, 2 CHEM_ANALYZER, 1 site).
- **TaskH_COORD_RISK**: Coordination under injected risks; same scale config, risk injection via study spec.

Both tasks use `scale_config` on the task instance; `get_initial_state(seed)` calls `generate_scaled_initial_state(scale_config, repo_root, seed)`.

## Benchmark runner

For `TaskG_COORD_SCALE` and `TaskH_COORD_RISK`:

1. A **probe** `initial_state` is generated with `base_seed` to obtain agent count and device/zone lists.
2. **Env factory** creates `LabTrustParallelEnv` with `scale_agents`, `scale_device_ids`, `scale_zone_ids` so the PZ env has `worker_0`..`worker_{N-1}` mapping to engine `A_WORKER_0001`..
3. **Scripted agents map** is built with one `ScriptedRunnerAgent` per worker (same zone_ids and device_ids as the scale).

Run:

```bash
labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 1 --seed 42 --out results.json
```

## Determinism guarantees

- Same **seed** and same **CoordinationScaleConfig** (and same **partner_id**) produce identical:
  - Agent IDs and order
  - Device IDs and placement
  - Site IDs
  - Initial specimen list (IDs and length)
  - Zone layout `device_placement` and effective_policy overlays
- Specimen counts and arrival schedule are derived from the same RNG state; different seeds yield different specimens but deterministic per seed.

## Constraints

- **Runner output contract v0.1** unchanged: step result shape (status, emits, violations, blocked_reason_code, token_consumed, hashchain) unchanged; only a new emit type **COORD_SCALE_CONFIG** added to the vocab.
- **Queue contract** unchanged: device queue semantics and START_RUN / QUEUE_RUN behavior unchanged.
- No ambient randomness: all randomness is seeded (seed passed into `generate_scaled_initial_state` and into env reset).

## See also

- [Coordination policy](coordination_policy.md): risk registry, method registry, method-risk matrix, study spec.
- [Frozen contracts](frozen_contracts.md): runner output, queue, invariant registry, enforcement map.
