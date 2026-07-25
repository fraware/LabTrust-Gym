"""Sealed train/eval partition tooling for verifier-assurance holdouts."""

from labtrust_gym.verifier_assurance.holdouts.partition import (
    HoldoutPartitionError,
    assert_disjoint_partitions,
    assert_no_holdout_leakage,
    build_partition_manifest,
    compute_partition_digest,
    default_holdout_families,
    filter_public_pack_records,
    load_partition_manifest,
    seal_eval_holdout,
    split_train_eval,
    validate_partition_manifest,
    verify_eval_commitment,
    write_partition_manifest,
)

__all__ = [
    "HoldoutPartitionError",
    "assert_disjoint_partitions",
    "assert_no_holdout_leakage",
    "build_partition_manifest",
    "compute_partition_digest",
    "default_holdout_families",
    "filter_public_pack_records",
    "load_partition_manifest",
    "seal_eval_holdout",
    "split_train_eval",
    "validate_partition_manifest",
    "verify_eval_commitment",
    "write_partition_manifest",
]
