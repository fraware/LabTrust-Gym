# Architecture

LabTrust-Gym is structured as:

- **Core simulator (`engine/`)** — `core_env` (reset, step, query), audit log (hash chain, forensic freeze), zones (graph, doors, device placement), specimens (acceptance, hold/reject), QC (result gating), critical (notify/ack), queueing (per-device queues), devices (state machine, service times when `timing_mode: simulated`), clock, RNG (deterministic). BLOCKED steps do not mutate world state except audit logging; hash chain break triggers forensic freeze.
- **Trust skeleton (`policy/`)** — Versioned YAML/JSON under `policy/` (emits vocab, zones, reason codes, tokens, invariants, catalogue, stability, equipment, critical, golden scenarios). All policy files are validated against JSON schemas in `policy/schemas/` via `labtrust validate-policy`.
- **Runner (`runner/`)** — Golden runner and `LabTrustEnvAdapter` interface; emits vocabulary enforced (unknown emits fail).
- **Envs (`envs/`)** — PettingZoo Parallel and AEC wrappers over the core engine; observations, actions, rewards, infos (require `.[env]`).
- **Baselines (`baselines/`)** — Scripted ops and scripted runner agents.
- **Benchmarks (`benchmarks/`)** — Task definitions (TaskA/B/C), metrics, runner; CLI `labtrust run-benchmark`, `labtrust bench-smoke`.

Determinism: single RNG wrapper (`rng.py`) seeded from scenario; no ambient randomness. Timing: `timing_mode: explicit` (default, event `t_s` only) or `simulated` (device service times from equipment registry).
