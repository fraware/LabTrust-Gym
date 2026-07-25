# Verifier Assurance Architecture Notes

Implements LT-VA-00..15 inside LabTrust-Gym. Large multi-host orchestration remains out of scope (`verifier-assurance-lab`).

**Non-claims:** simulation/research only; no production clinical assurance. See [non_claims.md](non_claims.md) and EnvironmentProfile `known_fidelity_limits`.

## Package map

| Area | Path |
|------|------|
| Environment profile | `src/labtrust_gym/verifier_assurance/environment_profile.py` |
| Dual oracle | `src/labtrust_gym/verifier_assurance/oracle/dual_oracle.py` |
| Sealed durable worker | `src/labtrust_gym/verifier_assurance/oracle/sealed_worker.py` |
| Offline PPO vs `V_public` | `src/labtrust_gym/verifier_assurance/training/offline_ppo.py` |
| Public verifier Gymnasium env | `src/labtrust_gym/verifier_assurance/training/public_verifier_env.py` |
| Reward composition | `src/labtrust_gym/verifier_assurance/reward/composition.py` |
| Snapshot/restore | `src/labtrust_gym/verifier_assurance/snapshot/` |
| Fork/branch | `src/labtrust_gym/verifier_assurance/fork/` |
| Mutations | `src/labtrust_gym/verifier_assurance/mutations/` |
| Causal graph | `src/labtrust_gym/verifier_assurance/causal/graph.py` |
| Campaign export | `src/labtrust_gym/verifier_assurance/campaign/export.py` |
| Reconstruction CLI | `src/labtrust_gym/verifier_assurance/campaign/reconstruct.py` |
| Attack handles | `src/labtrust_gym/verifier_assurance/attacks/` |
| Studies VA-10..13 / VA-15 | `src/labtrust_gym/verifier_assurance/studies/` |
| Holdout partitions (VA-15) | `src/labtrust_gym/verifier_assurance/holdouts/` |
| Calibration + release (VA-14) | `src/labtrust_gym/verifier_assurance/calibration/` |

## Dual oracle and process boundary

Per [ADR-VA-001](../adr/ADR-VA-001-dual-oracle-architecture.md):

| Mode | Use | Behavior |
|------|-----|----------|
| In-process façade | CI / unit tests | Hard API denial; leakage suite fails closed |
| One-shot subprocess | Contract smoke | Fresh interpreter; sealed JSON; never imports policy/attacker modules |
| Durable sealed worker | Release-grade campaigns | Length-prefixed sealed IPC (`DurableSealedHiddenWorker`); commitments only until freeze; freeze token stays on trusted parent |

Public packs carry `commitment = H(hidden_adjudication || salt || campaign_id)` only. Active hidden labels must not appear in observations, logs, env vars, exception text, or public IPC frames before freeze.

## Sealed train/eval holdouts (VA-15)

Complementary to dual-oracle sealing: `HoldoutPartitionManifest.v1` commits to disjoint train vs eval episode sets and forbids eval episode content in public packs. See [holdouts.md](holdouts.md).

## Schemas

- LabTrust-local: `policy/schemas/verifier_assurance/*.v1.schema.json` (includes `HoldoutPartitionManifest.v1`)
- PCS portable: `policy/schemas/pcs/RewardEvidenceEnvelope.v1.schema.json`

## Training fidelity (VA-13)

Default CI/release path uses offline-deterministic **numpy clipped-PPO** against a Gymnasium `PublicVerifierEnv` whose reward is `V_public` accept/reject. Frozen checkpoint IDs/digests are recorded. Optional `sb3_ppo` is gated behind `stable-baselines3` (`pip install -e ".[marl]"`). This is blood-sciences exploit-family optimization against the public verifier profile — not a claim of production RL robustness.

## Authorization and PF-Core (VA-11)

Grant semantics map onto existing token dual-approval objects ([ADR-VA-003](../adr/ADR-VA-003-grant-semantics.md)). The PF-Core / OVK adapter:

- Uses an injected checker in tests, or real `pf_core` when importable
- Falls back to `LocalFakePFCoreChecker` for offline CI completeness (`allow_local_fake=True` default)
- Returns `indeterminate` when the checker is unavailable or predicates are unknown — **never** fabricated acceptance

## Causal graph (VA-07 / VA-12)

Optional causal fields attach to audit events with hash-chain preservation. The graph is a **declared experimental causal model** for research attribution; it does not assign legal responsibility ([non_claims.md](non_claims.md)).

## Reconstruction

Validate a clean-checkout release pack (checksums + required tree):

```text
python -m labtrust_gym.verifier_assurance.campaign.reconstruct --pack benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1
```

Programmatic equivalent: `labtrust_gym.verifier_assurance.campaign.export.reconstruct_campaign(pack_dir)`.

## Fail-closed rule

Unknown schemas, missing artifacts, unavailable checkers, or leakage suspicion yield error or `indeterminate` — never acceptance presented as assurance.
