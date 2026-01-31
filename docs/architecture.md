# Architecture

LabTrust-Gym is structured as:

- **Core simulator (`engine/`)** — `core_env` (reset, step, query), audit log (hash chain, forensic freeze), zones (graph, doors, device placement), specimens (acceptance, hold/reject), QC (result gating), critical (notify/ack), queueing (per-device queues), devices (state machine, service times when `timing_mode: simulated`), clock, RNG (deterministic), **invariants_runtime** (registry-driven checks post-step), **enforcement** (policy-driven throttle/kill_switch/freeze_zone/forensic_freeze). BLOCKED steps do not mutate world state except audit logging; hash chain break triggers forensic freeze.
- **Trust skeleton (`policy/`)** — Versioned YAML/JSON under `policy/` (emits vocab, zones, reason codes, tokens, invariants registry v1.0, catalogue, stability, equipment, critical, enforcement map, studies, llm action schema, golden scenarios). All policy files are validated against JSON schemas in `policy/schemas/` via `labtrust validate-policy`.
- **Runner (`runner/`)** — Golden runner and `LabTrustEnvAdapter` interface; emits vocabulary enforced (unknown emits fail).
- **Envs (`envs/`)** — PettingZoo Parallel and AEC wrappers over the core engine; observations, actions, rewards, infos (require `.[env]`).
- **Baselines (`baselines/`)** — Scripted ops, scripted runner, adversary, LLM agent (mock + OpenAI stub), PPO/MARL (optional `.[marl]`).
- **Benchmarks (`benchmarks/`)** — Task definitions (TaskA, TaskB, TaskC, TaskD), metrics, runner; CLI `labtrust run-benchmark`, `labtrust bench-smoke`.
- **Studies (`studies/`)** — Study runner (ablations → conditions), plots (figures + data tables), reproduce (minimal sweep + plots); CLI `labtrust run-study`, `labtrust make-plots`, `labtrust reproduce --profile minimal | full`.

**CLI:** `validate-policy`, `run-benchmark`, `bench-smoke`, `run-study`, `make-plots`, `reproduce`, `train-ppo`, `eval-ppo`.

Determinism: single RNG wrapper (`rng.py`) seeded from scenario; no ambient randomness. Timing: `timing_mode: explicit` (default, event `t_s` only) or `simulated` (device service times from equipment registry).
