# Coordination scale generator

Deterministic generation of large lab scenarios (many agents, specimens, devices, sites) for coordination benchmarks without changing frozen contracts (runner output v0.1, queue contract v0.1).

## Goal

Compare coordination methods at scale by producing reproducible `initial_state` and policy overlays from a compact **scale config**. Same `(seed_base, scale_config, partner_id)` yields identical generated state across runs.

## Named scale presets

**`policy/coordination/scale_configs.v0.1.yaml`** defines named presets that can be referenced by id in study specs or loaded via **`load_scale_config_by_id(repo_root, config_id)`**.

| Preset id | Description |
|-----------|-------------|
| **small_smoke** | Fast unit/smoke: 4 agents, 2 CHEM + 1 CENTRIFUGE, 1 site, 50 steps, explicit timing. |
| **corridor_heavy** | High contention: 200 agents, 2 sites, narrow corridors; 150 steps, explicit. |
| **medium_stress_signed_bus** | Medium stress for signed message bus and coordination identity: 75 agents, 8–12 devices (6 CHEM, 3 CENTRIFUGE, 1 ALIQUOTER), 2 sites; arrival rate 3.5 specimens/min tuned so queues form without saturation; 300 steps; timing_mode **simulated** when supported (otherwise explicit; see limitation below). |

To use a named preset in a coordination study spec, add a scale dimension **`scale_preset`** with values listing preset ids:

```yaml
scales:
  - name: scale_preset
    values: ["small_smoke", "medium_stress_signed_bus"]
```

The study runner loads each preset from the YAML and uses it as the scale config for that row. coord_scale and coord_risk consume the same **CoordinationScaleConfig** (via `scale_config_override` when running from the study, or from the task default when running standalone).

**Timing mode**: `medium_stress_signed_bus` sets `timing_mode: "simulated"`. If the task or runner does not yet support simulated timing for coordination scale, it may fall back to explicit step-derived timing; behavior is documented in the task and runner. Explicit mode still yields deterministic, comparable runs.

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

- **coord_scale**: Coordination at scale under nominal conditions. Uses a default small scale (10 agents, 2 CHEM_ANALYZER, 1 site).
- **coord_risk**: Coordination under injected risks; same scale config, risk injection via study spec.

Both tasks use `scale_config` on the task instance; `get_initial_state(seed)` calls `generate_scaled_initial_state(scale_config, repo_root, seed)`.

## Benchmark runner

For `coord_scale` and `coord_risk`:

1. A **probe** `initial_state` is generated with `base_seed` to obtain agent count and device/zone lists.
2. **Env factory** creates `LabTrustParallelEnv` with `scale_agents`, `scale_device_ids`, `scale_zone_ids` so the PZ env has `worker_0`..`worker_{N-1}` mapping to engine `A_WORKER_0001`..
3. **Scripted agents map** is built with one `ScriptedRunnerAgent` per worker (same zone_ids and device_ids as the scale).

Run:

```bash
labtrust run-benchmark --task coord_scale --episodes 1 --seed 42 --out results.json
```

## Network policy and determinism

Coordination message delivery can use a **network policy** (`policy/coordination/network_policy.v0.1.yaml`, schema `policy/schemas/network_policy.v0.1.schema.json`) to simulate delay (p50/p95 ms), drop rate, partition schedule, and bounded reorder. When a risk injection supplies `CommsConfig.network_policy`, **CommsModel** routes all delivery through **NetworkModel** (`src/labtrust_gym/coordination/network.py`). Network randomness is **seeded solely from the episode seed** (`--seed`): same seed and same policy yield identical delivery and metrics. Telemetry includes `comm.p95_latency_ms`, `comm.drop_rate`, `comm.partition_events`, and `coordination.stale_action_rate` in coordination study summaries (`summary_coord.csv`). coord_risk network injections: **INJ-NET-PARTITION-001**, **INJ-NET-REORDER-001**, **INJ-NET-DROP-SPIKE-001**.

## Determinism guarantees

- Same **seed** and same **CoordinationScaleConfig** (and same **partner_id**) produce identical:
  - Agent IDs and order
  - Device IDs and placement
  - Site IDs
  - Initial specimen list (IDs and length)
  - Zone layout `device_placement` and effective_policy overlays
- Specimen counts and arrival schedule are derived from the same RNG state; different seeds yield different specimens but deterministic per seed.
- **Network model**: when `network_policy` is set, all delay/drop/partition/reorder are driven by the same episode RNG; no ambient randomness.

## Constraints

- **Runner output contract v0.1** unchanged: step result shape (status, emits, violations, blocked_reason_code, token_consumed, hashchain) unchanged; only a new emit type **COORD_SCALE_CONFIG** added to the vocab.
- **Queue contract** unchanged: device queue semantics and START_RUN / QUEUE_RUN behavior unchanged.
- No ambient randomness: all randomness is seeded (seed passed into `generate_scaled_initial_state` and into env reset).

## See also

- [Coordination policy](../policy/coordination_policy.md): risk registry, method registry, method-risk matrix, study spec.
- [Frozen contracts](../contracts/frozen_contracts.md): runner output, queue, invariant registry, enforcement map.
