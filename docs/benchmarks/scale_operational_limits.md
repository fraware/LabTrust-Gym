# Scale and operational limits

This document defines what “coordination at scale” means for LabTrust-Gym, the intended envelope of supported runs, and design notes for persistence and observability.

## At-scale semantics and profile

**Supported agent counts:** Configurations in `policy/coordination/scale_configs.v0.1.yaml` define scales from 4 agents (`small_smoke`) to 75 (`medium_stress_signed_bus`) and 200 (`corridor_heavy`). The reference implementation is tested with these scales. Runs with 100s of agents are in scope; 1000s of agents are not validated and may hit memory or wall-clock limits.

**Episode length:** Step counts are scale- and task-dependent (e.g. 50–300 steps for coord_scale/coord_risk). Long episodes (e.g. 1000+ steps) are not part of the default matrix and may require tuning (e.g. checkpointing) for stability.

**Wall-clock vs simulated timing:** Use `--timing simulated` for Layer 3 and latency/TAT metrics; the engine advances time according to device service times and arrival rates. Wall-clock (real time) is not used for benchmark correctness; runs are deterministic given seed and timing mode.

**Designated at-scale profile:** **`corridor_heavy`** (200 agents, 2 sites, narrow corridor zones) is the “at scale” profile for stress-testing the coordinator and router. It is exercised in Layer 3 scripts (`scripts/run_benchmarking_layer3_scale.sh`) and can be added to coordination-nightly or a dedicated CI job (e.g. one episode per method at `corridor_heavy`) so forkers know the intended envelope. **`medium_stress_signed_bus`** (75 agents) is the default “pathology lab (blood sciences) at scale” for selection policy and lab report.

**Known limits:** Large scales increase memory (agent state, episode log) and runtime. The pack and study runners do not currently cap episode length or agent count in code; policy-defined scale configs are the source of truth. For production-like or very long runs, consider persistence and checkpointing (below).

**Parallel multi-agentic and rate limiting:** When running agent-centric multi-agentic with per-agent LLM (`--agent-driven --multi-agentic --use-parallel-multi-agentic` and an LLM backend), the following parameters are configurable via `run_benchmark` or (when using scale tasks) via scale_config dict overrides:

- **round_timeout_s** (default 60.0): Maximum wall-clock seconds per round before the driver forces advance (missing agents get NOOP). Passed to `AgentDrivenDriver` and `ParallelMultiAgenticBackend`. Recommended: 60s for production; lower for tests.
- **parallel_multi_agentic_max_workers** (default None): Max threads in the pool for parallel agent backends. When None, uses `min(N, 64)`. Recommended: `min(N, 64)` for 200 agents.
- **global_rate_limit_rps** / **global_rate_limit_capacity** (defaults 10.0, 20.0): TokenBucket rate and capacity for the shared global rate limiter passed to every per-agent `LLMAgentWithShield`. Optional; when not set in scale_config, runner uses these defaults. Tune for your LLM provider limits.
- **global_rate_limit_max_wait_s** (optional): Maximum seconds each agent waits for a token from the global rate limiter before returning NOOP with reason_code **AGENT_RATE_LIMIT** (bounded wait; no indefinite block). When not set, agents wait indefinitely. Set (e.g. 60.0) in scale_config for production-style behavior.

See [Design choices](../architecture/design_choices.md) (sections 3.4, 6, 7) for thread safety, round timeout semantics, and parallel backend behavior.

**Recommended max N and memory (200 LLM agents):** A single process can run up to about **200** per-agent LLM agents (e.g. `LLMAgentWithShield`) with the default backends and shared global rate limiter. Each agent instance holds its own RateLimiter, CircuitBreaker, and shield context; 200 such instances are relatively heavy in memory. Use a **shared backend** (one OpenAILiveBackend or DeterministicConstrainedBackend) and one **global_rate_limiter** (TokenBucket) for all agents so that API usage and connection count stay bounded. For higher N or constrained memory, consider: (1) reducing `parallel_multi_agentic_max_workers` to cap concurrency; (2) an optional “light” per-agent wrapper that shares a single CircuitBreaker per backend: set **shared_circuit_breaker_per_backend: true** in scale_config (or scale_config_override) so the runner creates one CircuitBreaker per backend and passes it to each LLMAgentWithShield; default is one CircuitBreaker per agent. The designated at-scale profile **corridor_heavy** (200 agents) is validated in Layer 3 and coordination-nightly; for production-like runs, monitor memory and tune rate limits.

**Combine path at scale (N_max):** When the number of agents exceeds **coord_propose_actions_max_agents** (default 50, set in `CoordinationScaleConfig` or scale_config_override), the runner does **not** call `coord_method.propose_actions`. Instead it collects one **submission** per agent (from scripted_agents_map or NOOP), then calls **`coord_method.combine_submissions(submissions, obs, infos, t)`** to obtain the joint action. So at scale, only the combine path is used; submission shape per method is defined in `policy/coordination/coordination_submission_shapes.v0.1.yaml` (action, bid, or vote).

## Persistence and replay (design)

**Goal:** Support long or production-like runs by persisting episode logs incrementally, saving checkpoints at step N, and resuming from a checkpoint so runs can be audited and resumed after interruption.

**Design (current state):** When `--log` is set, the runner appends one JSON line per completed episode to `run_dir/episodes.jsonl` so that a crash leaves a partial, verifiable log of episode records. Step-level (method trace, coord_decisions) is written by the episode driver to the path given by `--log`. Optionally, use `--log-step-interval N` (N=1 for every step, N=10 for every 10 steps; default 0=off) to append a compact step record to `run_dir/steps.jsonl` each N steps (fields: episode, step, t_s, violations). Checkpoints are written at end of every N episodes (and after the last episode); step-level checkpoint is documented separately.

**Implementation status:**

1. **Append-only step log:** Implemented. Use `--log-step-interval 1` (or N) with `--log` to append each step (or every N steps) to `run_dir/steps.jsonl`; a crash leaves a partial log up to the last written step.
2. **Checkpoint at step N:** Implemented (minimal). Use `--checkpoint-every-steps N` with `--log`; the runner writes a step checkpoint every N steps (engine clock and RNG state in `checkpoint_step_latest.json`). Full store serialization is not implemented; resume-from-step is best-effort. Coordinator state is not serialized.
3. **Replay from checkpoint:** Implemented. The command `labtrust run-benchmark --resume-from <run_dir>` loads the episode checkpoint and continues the run (skips completed episodes). Use the same `--out` and `--log` paths as the original run. Evidence bundle and verify-bundle accept a run produced in multiple segments.

The helper module `labtrust_gym.benchmarks.checkpoint` provides `write_checkpoint`, `load_checkpoint`, `start_episode_index_from_resume`, and step-level `write_step_checkpoint` / `load_step_checkpoint`. The CLI supports `--resume-from <dir>`, `--checkpoint-every N`, and `--checkpoint-every-steps N` (step checkpoint requires `--log`). Use `--log <run_dir>/episodes.jsonl` and `--checkpoint-every N` for long runs; resume with `--resume-from <run_dir>`.

## Observability

**Logging:** Application logging uses the standard `logging` module. For structured logging (e.g. run_id, step, agent_id), add context to log records in the runner and engine (e.g. `extra={"run_id": run_id, "step": step}`). This allows log aggregation and filtering by run or step without parsing free text.

**Metrics export:** There is no Prometheus or OpenTelemetry export in the current code. A future extension could expose counters or histograms (e.g. steps per episode, violations per run, throughput) via a small HTTP endpoint or a file that a sidecar could scrape. Metrics would be optional and off by default to keep the core deterministic and dependency-light.

**Run summary:** Use `labtrust run-summary --run <dir>` to print one-line stats (episodes, steps, violations, throughput) for a run directory. The directory may contain `results.json` or (for partial runs) `episodes.jsonl`. Use `--format json` for machine-readable output. The existing `labtrust summarize-results` and report builders (e.g. LAB_COORDINATION_REPORT.md, pack_gate.md) provide full aggregation across multiple runs.

## See also

- [Coordination studies](../coordination/coordination_studies.md) – Study runner and matrix.
- [CI](../operations/ci.md) – coordination-nightly and optional at-scale job.
