# Verifier Assurance (LT-VA)

LabTrust-Gym Verifier Assurance turns the blood-sciences simulation into a **stateful, optimization-aware verifier-assurance testbed**.

**Scope of this repository:** local interfaces, offline deterministic campaigns, PCS export/reconstruction, dual-oracle isolation, and preregistered studies VA-10..14. Large multi-host campaign orchestration belongs in `verifier-assurance-lab`.

**Claim boundary:** simulation and research only. See [non_claims.md](non_claims.md).

## Document map

| Document | Purpose |
|----------|---------|
| [Architecture](architecture.md) | Package map, dual oracle, offline PPO, sealed IPC, reconstruction CLI |
| [Baseline freeze (LT-VA-00)](baseline_freeze.md) | Frozen base commit, toolchain, pre-VA snapshot, post-hardening status |
| [Experiment preregistration](experiment_preregistration.md) | VA-10..13 primary metrics and acceptance contributions |
| [Non-claims](non_claims.md) | Explicit what LT-VA does **not** claim |
| [ADR-VA-001](../adr/ADR-VA-001-dual-oracle-architecture.md) | `V_public` / `V_hidden` boundary modes |
| [ADR-VA-002](../adr/ADR-VA-002-claim-boundaries.md) | Non-clinical claim boundaries |
| [ADR-VA-003](../adr/ADR-VA-003-grant-semantics.md) | Grant → token dual-approval mapping; PF-Core adapter |
| [Threat model extension](../architecture/threat_model.md#verifier-assurance-extension-lt-va) | Optimization-induced failure, leakage, auth surfaces |
| [Partner calibration (VA-14)](../risk-and-security/partner_calibration.md#verifier-assurance-aggregate-adapter-lt-va-14) | De-identified aggregates only |

## Capabilities (hardened)

| Area | Implementation |
|------|----------------|
| Dual oracle | `V_public` vs sealed `V_hidden` ([ADR-VA-001](../adr/ADR-VA-001-dual-oracle-architecture.md)) |
| Process boundary | In-process façade (CI), one-shot subprocess, durable sealed IPC worker |
| Reward | Decomposed components + PCS `RewardEvidenceEnvelope.v1` |
| State | Canonical snapshot / fork / mutation / causal graph |
| Campaigns | PCS export + clean-checkout reconstruction |
| Training (VA-13) | Offline-deterministic numpy clipped-PPO vs `V_public`; optional gated `sb3_ppo` |
| Authorization (VA-11) | GrantRecord → token dual-approval; `LocalFakePFCoreChecker` / external PF-Core, fail-closed `indeterminate` |
| Studies | Preregistered VA-10..13; aggregate calibration adapter VA-14 |

## How to run

### Tests

```text
pytest -q tests/verifier_assurance
```

### Reconstruct a frozen release pack

```text
python -m labtrust_gym.verifier_assurance.campaign.reconstruct --pack benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1
```

Exit code `0` when checksums and required tree validate; JSON summary is printed to stdout.

### Key Python entry points

| Entry | Module |
|-------|--------|
| Environment profile | `labtrust_gym.verifier_assurance.environment_profile` |
| Dual oracle | `labtrust_gym.verifier_assurance.oracle.dual_oracle` |
| Sealed durable worker | `labtrust_gym.verifier_assurance.oracle.sealed_worker` |
| Offline PPO | `labtrust_gym.verifier_assurance.training.offline_ppo` |
| Public verifier env | `labtrust_gym.verifier_assurance.training.public_verifier_env` |
| Campaign export / reconstruct | `labtrust_gym.verifier_assurance.campaign.export` / `.reconstruct` |
| Studies VA-10..13 | `labtrust_gym.verifier_assurance.studies.*` |
| Aggregate calibration | `labtrust_gym.verifier_assurance.calibration.aggregate` |

## Frozen artifacts (keep)

| Path | Role |
|------|------|
| `benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1/` | Public release pack (commitments only; no active hidden labels) |
| `policy/schemas/verifier_assurance/` | LabTrust-local VA schemas |
| `policy/schemas/pcs/RewardEvidenceEnvelope.v1.schema.json` | Portable PCS reward evidence |
| `src/labtrust_gym/verifier_assurance/` | Feature implementation |
| `tests/verifier_assurance/` | Regression suite |

Do not commit `_tmp_*` scratch dumps, local campaign outs, or private adjudication reveal packs into public paths.

## Release notes (VA)

| Milestone | Contents |
|-----------|----------|
| LT-VA-00 | Baseline freeze, ADRs, non-claims, threat-model extension, preregistration |
| LT-VA-01..09 | Environment profile, dual oracle + sealed IPC, reward composition, snapshot/fork/mutations, causal graph, campaign PCS export, attack access classes |
| LT-VA-10..14 | Outcome/process, authorization (+ PF-Core adapter), responsibility attribution, verifier co-evolution (offline PPO), aggregate calibration |
| Hardening | Durable sealed worker, leakage fail-closed, numpy PPO default for CI, `LocalFakePFCoreChecker` when PF-Core unavailable (`indeterminate`, never fabricated acceptance) |
