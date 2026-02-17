# Scale and operational limits

This document defines what “coordination at scale” means for LabTrust-Gym, the intended envelope of supported runs, and design notes for persistence and observability.

## At-scale semantics and profile

**Supported agent counts:** Configurations in `policy/coordination/scale_configs.v0.1.yaml` define scales from 4 agents (`small_smoke`) to 75 (`medium_stress_signed_bus`) and 200 (`corridor_heavy`). The reference implementation is tested with these scales. Runs with 100s of agents are in scope; 1000s of agents are not validated and may hit memory or wall-clock limits.

**Episode length:** Step counts are scale- and task-dependent (e.g. 50–300 steps for coord_scale/coord_risk). Long episodes (e.g. 1000+ steps) are not part of the default matrix and may require tuning (e.g. checkpointing) for stability.

**Wall-clock vs simulated timing:** Use `--timing simulated` for Layer 3 and latency/TAT metrics; the engine advances time according to device service times and arrival rates. Wall-clock (real time) is not used for benchmark correctness; runs are deterministic given seed and timing mode.

**Designated at-scale profile:** **`corridor_heavy`** (200 agents, 2 sites, narrow corridor zones) is the “at scale” profile for stress-testing the coordinator and router. It is exercised in Layer 3 scripts (`scripts/run_benchmarking_layer3_scale.sh`) and can be added to coordination-nightly or a dedicated CI job (e.g. one episode per method at `corridor_heavy`) so forkers know the intended envelope. **`medium_stress_signed_bus`** (75 agents) is the default “hospital lab at scale” for selection policy and lab report.

**Known limits:** Large scales increase memory (agent state, episode log) and runtime. The pack and study runners do not currently cap episode length or agent count in code; policy-defined scale configs are the source of truth. For production-like or very long runs, consider persistence and checkpointing (below).

## Persistence and replay (design)

**Goal:** Support long or production-like runs by persisting episode logs incrementally, saving checkpoints at step N, and resuming from a checkpoint so runs can be audited and resumed after interruption.

**Design (current state):** Episode logs are written at the end of an episode (or at the end of a run) by the benchmark runner. There is no mid-episode checkpoint or append-only log stream to disk during a run.

**Proposed direction:**

1. **Append-only episode log:** Optionally append each step (or every K steps) to a run dir file (e.g. `episode_log.jsonl`) so that a crash leaves a partial log that can be verified up to the last written step. Requires the runner to open the file once and append lines; hashchain and receipt generation would operate on the written subset.
2. **Checkpoint at step N:** Save engine state (and optional coordinator state) to a checkpoint file (e.g. `checkpoint_step_N.json` or a binary blob) at configurable intervals. Resume would load the checkpoint, re-initialize the runner from that step, and continue. This requires a serializable state contract for the engine and any stateful coordination method.
3. **Replay from checkpoint:** A separate command or mode (e.g. `labtrust run-benchmark --resume-from <checkpoint_dir>`) would load the checkpoint and continue the run. Evidence bundle and verify-bundle (or verify-release) would need to accept a run that was produced in two segments (e.g. merge logs or verify the final segment only).

**Implementation status:** Design only. A minimal implementation could add (1) append-only episode log in the runner and (2) a single checkpoint-at-end-of-episode for multi-episode runs, with resume supporting “start from episode K” by re-running episodes 0..K-1 in a fast replay mode or by loading a saved episode log and continuing from episode K. No checkpoint/resume code is implemented in the current codebase.

## Observability

**Logging:** Application logging uses the standard `logging` module. For structured logging (e.g. run_id, step, agent_id), add context to log records in the runner and engine (e.g. `extra={"run_id": run_id, "step": step}`). This allows log aggregation and filtering by run or step without parsing free text.

**Metrics export:** There is no Prometheus or OpenTelemetry export in the current code. A future extension could expose counters or histograms (e.g. steps per episode, violations per run, throughput) via a small HTTP endpoint or a file that a sidecar could scrape. Metrics would be optional and off by default to keep the core deterministic and dependency-light.

**Run summary script:** The existing `labtrust summarize-results` and report builders (e.g. LAB_COORDINATION_REPORT.md, pack_gate.md) provide a human-readable summary of a run. A simple script that parses a run dir and prints one-line stats (episodes, total steps, violations, throughput) would help forkers inspect runs without opening JSON. This can be added as a small CLI or script (e.g. `labtrust run-summary --run <dir>`).

## See also

- [Benchmarking plan](benchmarking_plan.md) – Layer 1–3 and scale IDs.
- [Coordination studies](../coordination/coordination_studies.md) – study runner and matrix.
- [CI](../operations/ci.md) – coordination-nightly and optional at-scale job.
