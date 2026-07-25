"""Sealed training vs evaluation partitions for verifier-assurance holdouts.

This complements dual-oracle sealing (ADR-VA-001): oracle sealing hides
adjudications; partition sealing keeps eval/holdout episode content out of
public training packs so benchmark leakage cannot inflate leaderboard scores.

Simulation/research only — see docs/verifier_assurance/non_claims.md.
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from labtrust_gym.errors import PolicyLoadError
from labtrust_gym.policy.loader import load_json, validate_against_schema
from labtrust_gym.util.json_utils import canonical_json
from labtrust_gym.verifier_assurance.oracle.dual_oracle import deny_hidden_in_mapping

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "policy"
    / "schemas"
    / "verifier_assurance"
    / "HoldoutPartitionManifest.v1.schema.json"
)

# Eval-held exploit families for LTG-05 gaps (not in public train packs by default).
DEFAULT_EVAL_HOLDOUT_FAMILIES: tuple[str, ...] = (
    "sparse_reward_exploitation",
    "delayed_safety_failure",
    "proxy_metric_gaming",
    "selective_evidence_omission",
    "attack_transfer_across_seeds",
)

DEFAULT_TRAIN_FAMILIES: tuple[str, ...] = (
    "qc_bypass",
    "unauthorized_mutation",
    "premature_release",
    "forged_or_replayed_signature",
    "unacknowledged_critical",
    "invalid_delegation",
    "audit_manipulation",
    "invalid_intermediate_specimen_state",
)


class HoldoutPartitionError(RuntimeError):
    """Fail-closed holdout partition / leakage violation."""


def default_holdout_families() -> dict[str, tuple[str, ...]]:
    return {
        "train": DEFAULT_TRAIN_FAMILIES,
        "eval": DEFAULT_EVAL_HOLDOUT_FAMILIES,
    }


def split_train_eval(
    episode_ids: Sequence[str],
    *,
    train_ratio: float = 0.7,
    seed: int = 0,
) -> tuple[list[str], list[str]]:
    """Deterministic train/eval split. Eval set is never empty when input is non-empty."""
    if not 0.0 < train_ratio < 1.0:
        raise HoldoutPartitionError("train_ratio must be in (0, 1)")
    ids = list(episode_ids)
    if not ids:
        raise HoldoutPartitionError("episode_ids must be non-empty")
    if len(set(ids)) != len(ids):
        raise HoldoutPartitionError("episode_ids must be unique")
    # Stable shuffle via seeded Fisher–Yates on indices
    order = list(range(len(ids)))
    rng = _seeded_rng(seed)
    for i in range(len(order) - 1, 0, -1):
        j = rng(i + 1)
        order[i], order[j] = order[j], order[i]
    shuffled = [ids[i] for i in order]
    cut = max(1, min(len(shuffled) - 1, int(len(shuffled) * train_ratio)))
    if len(shuffled) == 1:
        return [], shuffled
    return shuffled[:cut], shuffled[cut:]


def _seeded_rng(seed: int):
    state = seed & 0xFFFFFFFF

    def _next(n: int) -> int:
        nonlocal state
        # LCG; deterministic across platforms for CI fixtures
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state % n

    return _next


def compute_partition_digest(manifest: Mapping[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "partition_digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def seal_eval_holdout(
    eval_episode_ids: Sequence[str],
    *,
    campaign_id: str,
    salt: bytes | None = None,
) -> dict[str, Any]:
    """Commit to the sealed eval episode set without revealing membership content."""
    ids = sorted(set(eval_episode_ids))
    if not ids:
        raise HoldoutPartitionError("eval episode set must be non-empty")
    salt_b = salt if salt is not None else secrets.token_bytes(32)
    payload = canonical_json({"eval_episode_ids": ids, "campaign_id": campaign_id})
    commitment = hashlib.sha256(
        (payload + "||" + salt_b.hex() + "||" + campaign_id).encode("utf-8")
    ).hexdigest()
    return {
        "eval_set_commitment": commitment,
        "algorithm": "sha256",
        "salt_hex": salt_b.hex(),
        "revealed": False,
    }


def verify_eval_commitment(
    commitments: Mapping[str, Any],
    *,
    eval_episode_ids: Sequence[str],
    campaign_id: str,
) -> bool:
    """Verify a revealed (or locally known) eval commitment against episode IDs."""
    salt_hex = commitments.get("salt_hex")
    if not isinstance(salt_hex, str) or not salt_hex:
        raise HoldoutPartitionError("commitments.salt_hex required for verification")
    expected = seal_eval_holdout(
        eval_episode_ids,
        campaign_id=campaign_id,
        salt=bytes.fromhex(salt_hex),
    )
    return expected["eval_set_commitment"] == commitments.get("eval_set_commitment")


def assert_disjoint_partitions(train_ids: Sequence[str], eval_ids: Sequence[str]) -> None:
    overlap = set(train_ids) & set(eval_ids)
    if overlap:
        raise HoldoutPartitionError(f"train/eval overlap: {sorted(overlap)}")


def validate_partition_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_against_schema(dict(manifest), load_json(_SCHEMA_PATH), path=_SCHEMA_PATH)
    except PolicyLoadError as exc:
        raise HoldoutPartitionError(str(exc)) from exc
    out = copy.deepcopy(dict(manifest))
    train_ids = list(out["train"]["episode_ids"])
    eval_ids = list(out["eval"]["episode_ids"])
    assert_disjoint_partitions(train_ids, eval_ids)
    if not out["eval"].get("sealed") is True:
        raise HoldoutPartitionError("eval.sealed must be true")
    policy = out["public_pack_policy"]
    if not (
        policy.get("exclude_eval_episode_content") is True
        and policy.get("allow_eval_commitments_only") is True
        and policy.get("forbid_eval_ids_in_train_artifacts") is True
    ):
        raise HoldoutPartitionError("public_pack_policy must enforce sealed holdout defaults")
    if "commitments" in out:
        if not verify_eval_commitment(
            out["commitments"],
            eval_episode_ids=eval_ids,
            campaign_id=str(out["campaign_id"]),
        ):
            raise HoldoutPartitionError("eval_set_commitment mismatch")
    digest = compute_partition_digest(out)
    declared = out.get("partition_digest")
    if declared is not None and declared != digest:
        raise HoldoutPartitionError("partition_digest mismatch")
    out["partition_digest"] = digest
    deny_hidden_in_mapping(out, path="HoldoutPartitionManifest")
    return out


def build_partition_manifest(
    *,
    partition_id: str,
    campaign_id: str,
    train_episode_ids: Sequence[str],
    eval_episode_ids: Sequence[str],
    train_families: Sequence[str] | None = None,
    eval_families: Sequence[str] | None = None,
    rng_seed: int | None = 0,
    salt: bytes | None = None,
    partition_version: str = "1",
) -> dict[str, Any]:
    """Build and validate a sealed train/eval holdout partition manifest."""
    families = default_holdout_families()
    train_ids = list(train_episode_ids)
    eval_ids = list(eval_episode_ids)
    assert_disjoint_partitions(train_ids, eval_ids)
    commitments = seal_eval_holdout(eval_ids, campaign_id=campaign_id, salt=salt)
    manifest = {
        "schema_id": "HoldoutPartitionManifest.v1",
        "partition_id": partition_id,
        "campaign_id": campaign_id,
        "partition_version": partition_version,
        "rng_seed": rng_seed,
        "train": {
            "episode_ids": train_ids,
            "exploit_families": list(train_families or families["train"]),
        },
        "eval": {
            "episode_ids": eval_ids,
            "exploit_families": list(eval_families or families["eval"]),
            "sealed": True,
        },
        "commitments": commitments,
        "public_pack_policy": {
            "exclude_eval_episode_content": True,
            "allow_eval_commitments_only": True,
            "forbid_eval_ids_in_train_artifacts": True,
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return validate_partition_manifest(manifest)


def load_partition_manifest(path: Path | str) -> dict[str, Any]:
    doc = load_json(Path(path))
    return validate_partition_manifest(doc)


def filter_public_pack_records(
    records: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    *,
    episode_id_keys: Sequence[str] = ("episode_id", "id"),
) -> list[dict[str, Any]]:
    """
    Strip eval holdout episode content from records destined for a public pack.

    Eval commitments (commitment-only docs without episode payloads) may remain
    when they do not embed eval episode IDs as content keys.
    """
    validated = validate_partition_manifest(manifest)
    eval_ids = set(validated["eval"]["episode_ids"])
    public: list[dict[str, Any]] = []
    for rec in records:
        episode_id = None
        for key in episode_id_keys:
            if key in rec:
                episode_id = str(rec[key])
                break
        if episode_id is not None and episode_id in eval_ids:
            # Allow commitment-only stubs (no trajectory / adjudication body).
            if rec.get("commitment_only") is True and "adjudication" not in rec:
                stub = {
                    "episode_id": episode_id,
                    "commitment_only": True,
                    "commitment": rec.get("commitment"),
                    "partition": "eval_holdout",
                    "claim_boundary": CLAIM_BOUNDARY,
                }
                deny_hidden_in_mapping(stub, path="public_holdout_stub")
                public.append(stub)
                continue
            # Full eval content excluded from public packs.
            continue
        item = copy.deepcopy(dict(rec))
        deny_hidden_in_mapping(item, path="public_pack_record")
        public.append(item)
    return public


def assert_no_holdout_leakage(
    artifact: Any,
    manifest: Mapping[str, Any],
    *,
    path: str = "root",
    allow_commitment_stubs: bool = True,
) -> None:
    """
    Fail closed if sealed eval episode IDs appear in public train/pack artifacts.

    Commitment-only stubs that explicitly declare ``commitment_only`` and
    ``partition=eval_holdout`` are permitted when ``allow_commitment_stubs``.
    Private partition manifests (schema HoldoutPartitionManifest.v1) are not
    public packs and are skipped when detected as the artifact root.
    """
    validated = validate_partition_manifest(manifest)
    if not validated["public_pack_policy"]["forbid_eval_ids_in_train_artifacts"]:
        raise HoldoutPartitionError("manifest does not forbid eval leakage")
    if isinstance(artifact, Mapping) and artifact.get("schema_id") == "HoldoutPartitionManifest.v1":
        # The sealed private manifest itself may list eval IDs; that is not leakage.
        return
    eval_ids = set(validated["eval"]["episode_ids"])
    _scan_for_eval_ids(
        artifact,
        eval_ids=eval_ids,
        path=path,
        allow_commitment_stubs=allow_commitment_stubs,
    )


def _scan_for_eval_ids(
    obj: Any,
    *,
    eval_ids: set[str],
    path: str,
    allow_commitment_stubs: bool,
    _in_commitment_stub: bool = False,
) -> None:
    if isinstance(obj, Mapping):
        is_stub = (
            allow_commitment_stubs
            and obj.get("commitment_only") is True
            and obj.get("partition") == "eval_holdout"
        )
        for k, v in obj.items():
            key = str(k)
            if (
                key in ("episode_id", "id")
                and str(v) in eval_ids
                and not (is_stub or _in_commitment_stub)
            ):
                raise HoldoutPartitionError(f"eval holdout id leaked at {path}.{key}={v}")
            if (
                isinstance(v, str)
                and v in eval_ids
                and key
                not in (
                    "eval_set_commitment",
                    "partition_id",
                    "campaign_id",
                    "commitment",
                )
                and not (is_stub or _in_commitment_stub)
            ):
                raise HoldoutPartitionError(f"eval holdout id leaked at {path}.{key}={v}")
            _scan_for_eval_ids(
                v,
                eval_ids=eval_ids,
                path=f"{path}.{key}",
                allow_commitment_stubs=allow_commitment_stubs,
                _in_commitment_stub=is_stub or _in_commitment_stub,
            )
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            if isinstance(v, str) and v in eval_ids and not _in_commitment_stub:
                raise HoldoutPartitionError(f"eval holdout id leaked at {path}[{i}]={v}")
            _scan_for_eval_ids(
                v,
                eval_ids=eval_ids,
                path=f"{path}[{i}]",
                allow_commitment_stubs=allow_commitment_stubs,
                _in_commitment_stub=_in_commitment_stub,
            )


def write_partition_manifest(path: Path | str, manifest: Mapping[str, Any]) -> str:
    """Write a validated partition manifest; returns sha256 of bytes written."""
    validated = validate_partition_manifest(manifest)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(validated, indent=2, sort_keys=True) + "\n"
    data = text.encode("utf-8")
    out.write_bytes(data)
    return hashlib.sha256(data).hexdigest()
