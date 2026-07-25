# Sealed Train/Eval Holdouts (LTG-PR4 / VA-15)

Verifier assurance uses **two** sealing layers:

| Layer | What is sealed | Mechanism |
|-------|----------------|-----------|
| Dual oracle (ADR-VA-001) | Hidden adjudications / ground-truth labels | Commitments until campaign freeze; process isolation |
| Train/eval partitions (this doc) | Benchmark holdout episode **content** | `HoldoutPartitionManifest.v1`; eval IDs excluded from public packs |

Sealing `V_hidden` alone does **not** prevent training on evaluation scenarios. Partition holdouts exist so public packs and training corpora cannot absorb sealed eval episodes and inflate scores via leakage.

**Claim boundary:** simulation/research only. See [non_claims.md](non_claims.md).

## Manifest

Schema: `policy/schemas/verifier_assurance/HoldoutPartitionManifest.v1.schema.json`

Offline fixture: `benchmarks/verifier_assurance/fixtures/holdout_partition.hospital_lab.v1.json`

Required policy (fail-closed):

- `exclude_eval_episode_content: true`
- `allow_eval_commitments_only: true`
- `forbid_eval_ids_in_train_artifacts: true`
- `eval.sealed: true`

Eval membership is committed as:

```text
eval_set_commitment = SHA256(canonical_json({eval_episode_ids, campaign_id}) || salt || campaign_id)
```

Public packs may carry the commitment (and optional commitment-only stubs) but must not embed eval episode trajectories or adjudications.

## Tooling

| Entry | Module |
|-------|--------|
| Build / validate / seal | `labtrust_gym.verifier_assurance.holdouts.partition` |
| Leakage scan | `assert_no_holdout_leakage` |
| Public pack filter | `filter_public_pack_records` |
| Deterministic split | `split_train_eval` |
| VA-15 studies | `labtrust_gym.verifier_assurance.studies.holdout_exploits` |

## Default family split

**Train (public-ok / VA-10 style):** QC bypass, unauthorized mutation, premature release, forged signature, unacknowledged critical, invalid delegation, audit manipulation, invalid intermediate specimen state.

**Eval holdouts (VA-15):** sparse reward exploitation; delayed safety failure; proxy metric gaming; selective evidence omission; attack transfer across seeds.

## How a public pack stays clean

1. Build a partition with disjoint `train.episode_ids` / `eval.episode_ids`.
2. Seal eval membership (`seal_eval_holdout` / `build_partition_manifest`).
3. Keep full eval trajectories in a private/trusted store only.
4. For public export, run `filter_public_pack_records` (train content + commitment-only eval stubs).
5. Run `assert_no_holdout_leakage` on the public artifact tree before release.

Fail-closed: any eval episode ID appearing outside an explicit commitment stub raises `HoldoutPartitionError`.

## Studies (VA-15)

`run_holdout_exploit_study` recovers ≥4 holdout families where public accept/reward diverges from sealed hidden reject.

`run_partitioned_holdout_campaign` wraps that study with a sealed partition and a leakage-checked public pack view.

## Non-claims

Holdouts do not claim:

- Production clinical safety
- That sealed partitions stop all adaptive data mining outside this repository’s pack discipline
- That transfer-across-seeds results generalize to live adversaries or proprietary models
