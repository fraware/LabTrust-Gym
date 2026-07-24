# Verifier Assurance Baseline Freeze (LT-VA-00)

**Status:** frozen for LT-VA-00..14  
**Claim boundary:** LabTrust-Gym is a blood-sciences **simulation and research** testbed. This freeze does **not** assert production clinical assurance, regulatory clearance, or clinical validation.

## Base commit and toolchain

| Field | Value |
|-------|-------|
| Base commit | `1d9f2fa0b853975cb4a215f7a32eb3015356c3cd` |
| Commit subject | Polish documentation for public release. |
| Package version | `0.2.0` (`pyproject.toml`) |
| Requires Python | `>=3.11` |
| Freeze-time interpreter | Python 3.13.11 (Anaconda, win32) |
| Target lint version | `py311` (ruff/mypy config) |

## Baseline commands

Primary gates used at freeze time (from repo Makefile / CI conventions):

```text
make verify
pytest -q
# PCS gates (when pcs-core is installed):
pytest -q tests/pcs
```

Focused VA suite:

```text
pytest -q tests/verifier_assurance
```

## Pre-VA capability snapshot (at freeze)

Historical state **before** LT-VA implementation landed on this baseline:

| Capability | State at freeze | Notes |
|------------|-----------------|-------|
| Dual oracle | Absent | Golden runner + PCS export only; no `V_public` / `V_hidden` |
| Reward decomposition | Absent | Scalar hooks only in `pz_parallel.py` |
| Full snapshot/restore | Partial | `CoreEnv.get_state` / `set_state` = `now_ts` + `rng_state` only |
| Fork/branch | Absent | — |
| Declarative VA mutations | Absent | Risk injectors + security suite exist separately |
| Causal event graph | Linear only | `prev_hash` audit chain; no parent/principal/grant edges |
| VA campaign PCS pack | Absent | Official pack + PCS bench ingest exist for QC-release |
| PF-Core / OVK | Absent | CertifyEdge + PF handoff artifacts exist |

## Post-hardening capability status (current)

After LT-VA-00..14 and SOTA hardening on top of the freeze:

| Capability | Status | Notes |
|------------|--------|-------|
| Dual oracle | Present | In-process, one-shot, and durable sealed IPC modes |
| Reward decomposition | Present | Compatibility shim preserves legacy numeric benchmark behavior |
| Snapshot / fork / mutations | Present | Canonical snapshot, branch, declarative mutation profiles |
| Causal event graph | Present | Optional causal fields; experimental model, not legal attribution |
| Campaign PCS pack | Present | `benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1/` |
| Offline PPO vs `V_public` | Present | Default `numpy_ppo`; optional gated `sb3_ppo` |
| PF-Core adapter | Present | Real checker or `LocalFakePFCoreChecker`; unavailable → `indeterminate` |

See [architecture.md](architecture.md) for package paths and reconstruction CLI.

## Current reward hooks (legacy path; preserved by VA-03 shim)

Source: `src/labtrust_gym/envs/pz_parallel.py` (reward block).

- `schedule_reward`: added to the agent that successfully `QUEUE_RUN`s
- `throughput_reward`: broadcast when a result is released
- `violation_penalty`: subtracted per violation count for all agents
- `blocked_penalty`: subtracted per blocked action for all agents

Legacy numeric behavior for official benchmarks must be preserved by the VA-03 compatibility shim. VA campaigns additionally emit PCS `RewardEvidenceEnvelope.v1` evidence.

## Oracle / verifier behavior (current)

- **Golden runner** (`runner/golden_runner.py`): scenario oracle for golden suite acceptance/rejection (unchanged).
- **PCS verifier handoff**: QC-release export and partner handoff artifacts remain the production-facing PCS path.
- **VA dual oracle**: `V_public` supplies optimization reward; `V_hidden` seals commitments until campaign freeze ([ADR-VA-001](../adr/ADR-VA-001-dual-oracle-architecture.md)).

## Explicit non-claims

- No claim that LabTrust-Gym verifies real clinical laboratory software for production use.
- No claim of clinical outcome validity for blood-sciences workflows.
- No claim that VA campaigns replace partner security audits or regulatory submissions.
- No claim that offline PPO / SB3 training against `V_public` transfers to production verifiers.
