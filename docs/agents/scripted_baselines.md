# Scripted baselines

Scripted baselines are deterministic, hand-coded reference policies used for benchmarks and regression. They are **not** state-of-the-art control; the repo's SOTA is the OR kernel (rolling-horizon scheduler), LLM coordination methods, and MARL PPO. Scripted agents provide a stable, reproducible baseline to compare against.

## Purpose

Scripted baselines define the "default when not using LLM or MARL": they are the policies that drive the scheduler (ops), runners, and (when implemented) QC and supervisor in the PettingZoo env. They are used for:

- **Reproducibility:** Same seed and same action sequence yield identical trajectories; no API or training.
- **Comparison:** LLM, MARL, and coordination methods are compared against scripted behaviour (throughput, violations, blocks).
- **Regression:** Official baseline results and CI rely on deterministic scripted runs.

## When they are used

- **Default for `run-benchmark`** when no `--llm-backend` and no coordination method is set.
- **quick-eval**, **run-official-pack** (scripted runs), and as the "scripted" side of coordination comparisons.
- All four roles (ops, runners, QC, supervisor) have a scripted default: ScriptedOpsAgent, ScriptedRunnerAgent, ScriptedQcAgent, and ScriptedSupervisorAgent. A coordination method or task config can override them.

## What they are

| Agent | Role | Policy (deterministic) |
|-------|------|------------------------|
| **ScriptedOpsAgent** | Scheduler (ops_0) | STAT first, then EDF on stability deadline; release first releasable result; conservative stability/temperature; door tick when threshold exceeded; on QC fail, route to alternate device or hold. |
| **ScriptedRunnerAgent** | Runners (runner_0, runner_1, …) | Workflow: reception → centrifuge → aliquot → analyzer queue → START_RUN; MOVE, OPEN_DOOR, TICK; never open restricted door without token; respect frozen zones; transport phases (DISPATCH_TRANSPORT, TRANSPORT_TICK, CHAIN_OF_CUSTODY_SIGN, RECEIVE_TRANSPORT) when required. |
| **ScriptedQcAgent** | QC (qc_0) | If releasable_result_ids non-empty, RELEASE_RESULT for the first; else NOOP. |
| **ScriptedSupervisorAgent** | Supervisor (supervisor_0) | If override_eligible_result_ids non-empty and token_count_override > 0, RELEASE_RESULT_OVERRIDE for the first; else NOOP. |

Implementation: `src/labtrust_gym/baselines/scripted_ops.py`, `scripted_runner.py`, `scripted_qc.py`, `scripted_supervisor.py`.

## How they differ from SOTA

| Control | Description |
|---------|-------------|
| **kernel_scheduler_or** | Rolling-horizon OR scheduler + WHCA routing; reference for weighted tardiness and fairness. |
| **LLM (per-agent or coordination)** | LLM backends produce actions from observations; coordination methods use LLM for proposals/bids/repair. |
| **MARL (PPO)** | Single-agent (ops_0) or multi-agent shared policy; trained with stable-baselines3. |
| **Scripted** | Fixed rules, no learning, no API; used for reproducibility and as the baseline to beat. |

See [State of the art status and limits](../reference/state_of_the_art_and_limits.md) and [Coordination benchmark card](../coordination/coordination_benchmark_card.md) for baselines used in SOTA comparison.

## Configuration

Scripted ops and runner agents load configuration from `policy/scripted/` when present: `scripted_ops_policy.v0.1.yaml`, `scripted_runner_policy.v0.1.yaml`. Missing or empty policy files leave behaviour unchanged (in-code defaults). See [Scripted baseline policy](../contracts/scripted_baseline_contract.md).

## Explainability

Scripted agents emit **reason_code** and **rationale** in `action_info` for each action, aligned with `policy/reason_codes/reason_code_registry.v0.1.yaml`. This keeps logs and audits consistent with LLM/MARL. The runner forwards these into the engine when present.

## See also

- [PettingZoo API](pettingzoo_api.md) — Agent set, observation/action contract, relationship to LLMs.
- [Simulation, LLMs, and agentic systems](../architecture/simulation_llm_agentic.md) — Who owns the env; scripted vs coordination policies.
