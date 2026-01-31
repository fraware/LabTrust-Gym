# Reproducibility and seeding

LabTrust-Gym is deterministic when seeds and config are fixed.

## Seeding

- **Golden runner**: `reset(initial_state, deterministic=True, rng_seed=<from scenario>)`. The engine uses a single RNG wrapper (`engine/rng.py`); no ambient `random` outside it.
- **Benchmarks**: `run_episode(task, episode_seed, ...)` passes `episode_seed` into env `reset(seed=episode_seed, options={"initial_state": ...})`. Same task + same seed ⇒ same episode trajectory and metrics.
- **Studies**: Condition seeds are `seed_base + condition_index`. Same spec + same code + same seeds ⇒ identical manifest and per-condition result hashes.
- **Plots**: Data tables (CSVs) are deterministic; same study run ⇒ identical CSV output.

## Timing modes

- **explicit** (default): Event `t_s` is explicit; no simulated device service times. Golden suite and most tests use this.
- **simulated**: Device service times from equipment registry; RNG samples from policy. Use for benchmarks where p95 TAT is meaningful.

Set `initial_state.timing_mode: "simulated"` (or via study spec) to enable.

## Policy and versions

- Policy files are versioned under `policy/`. Validate with `labtrust validate-policy`.
- Study manifest records policy paths and (when available) file hashes for reproducibility.
