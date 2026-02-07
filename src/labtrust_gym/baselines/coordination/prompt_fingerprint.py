"""
Prompt fingerprinting for coordination LLM methods.

Canonical rendering: sort keys, stable formatting, no timestamps, bounded policy slices.
Produces: prompt_template_id, prompt_sha256, allowed_actions_payload_sha256,
coordination_policy_fingerprint for results.json and EvidenceBundle manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Bounded sizes for canonical state slice (avoid dumping full policy tree)
MAX_AGENTS_SLICE = 32
MAX_DEVICES_SLICE = 24
MAX_SPECIMENS_SLICE = 64
MAX_POLICY_KEYS = 32
MAX_POLICY_VALUE_LEN = 256
MAX_LIST_LEN = 16


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_str(s: str) -> str:
    return _sha256_hex(s.encode("utf-8"))


def _canonical_state_slice(state_digest: dict[str, Any]) -> dict[str, Any]:
    """
    Bounded, deterministic slice of state_digest for prompt hashing.
    Sorts keys, caps list lengths, no timestamps, no unbounded strings.
    """
    out: dict[str, Any] = {}
    for key in sorted(state_digest.keys()):
        val = state_digest[key]
        if key == "step":
            out[key] = int(val) if val is not None else 0
        elif key == "per_agent":
            agents = val if isinstance(val, list) else []
            out[key] = [
                {k: v for k, v in sorted((a if isinstance(a, dict) else {}).items())}
                for a in agents[:MAX_AGENTS_SLICE]
            ]
        elif key == "per_device":
            devices = val if isinstance(val, list) else []
            out[key] = [
                {k: v for k, v in sorted((d if isinstance(d, dict) else {}).items())}
                for d in devices[:MAX_DEVICES_SLICE]
            ]
        elif key == "per_specimen":
            specs = val if isinstance(val, list) else []
            out[key] = [
                {k: v for k, v in sorted((s if isinstance(s, dict) else {}).items())}
                for s in specs[:MAX_SPECIMENS_SLICE]
            ]
        elif key == "comms_stats" and isinstance(val, dict):
            out[key] = {k: val[k] for k in sorted(val.keys())}
        elif key == "device_zone" and isinstance(val, dict):
            items = sorted(val.items())[:MAX_DEVICES_SLICE]
            out[key] = dict(items)
        else:
            if isinstance(val, (int, float, bool)) or val is None:
                out[key] = val
            elif isinstance(val, str):
                out[key] = val[:MAX_POLICY_VALUE_LEN]
            elif isinstance(val, list):
                out[key] = val[:MAX_LIST_LEN]
            elif isinstance(val, dict):
                out[key] = {k: val[k] for k in sorted(val.keys())[:MAX_POLICY_KEYS]}
            else:
                out[key] = str(val)[:MAX_POLICY_VALUE_LEN]
    return out


def _canonical_policy_slice(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Bounded slice of policy for fingerprint; sort keys, cap depth/size."""
    if not policy or not isinstance(policy, dict):
        return {}
    out: dict[str, Any] = {}
    for i, key in enumerate(sorted(policy.keys())):
        if i >= MAX_POLICY_KEYS:
            break
        val = policy[key]
        if isinstance(val, (int, float, bool)) or val is None:
            out[key] = val
        elif isinstance(val, str):
            out[key] = val[:MAX_POLICY_VALUE_LEN]
        elif isinstance(val, list):
            out[key] = val[:MAX_LIST_LEN]
        elif isinstance(val, dict):
            sub = {k: val[k] for k in sorted(val.keys())[:MAX_POLICY_KEYS]}
            out[key] = sub
        else:
            out[key] = str(val)[:MAX_POLICY_VALUE_LEN]
    return out


def prompt_template_id_for_method(method_id: str) -> str:
    """Stable template id per coordination method."""
    return f"coordination_{method_id}_v0.1"


def allowed_actions_payload_sha256(
    allowed_actions: list[str],
    state: dict[str, Any] | None = None,
    zone_ids: list[str] | None = None,
    device_ids: list[str] | None = None,
) -> str:
    """
    SHA-256 of canonical allowed_actions payload (deterministic JSON).
    Uses build_allowed_actions_payload then canonical JSON; same inputs => same hash.
    """
    from labtrust_gym.baselines.llm.allowed_actions_payload import (
        build_allowed_actions_payload,
        serialize_allowed_actions_payload,
    )

    payload = build_allowed_actions_payload(
        state=state or {},
        allowed_actions=list(allowed_actions) if allowed_actions else [],
        zone_ids=zone_ids,
        device_ids=device_ids,
    )
    canonical = serialize_allowed_actions_payload(payload)
    return _sha256_str(canonical)


def coordination_policy_fingerprint_from_repo(repo_root: Path) -> str:
    """
    Fingerprint of policy/coordination_identity_policy.v0.1.yaml (same as verify-bundle).
    When file is missing, returns hash of placeholder.
    """
    path = Path(repo_root) / "policy" / "coordination_identity_policy.v0.1.yaml"
    if not path.is_file():
        return _sha256_hex(b"no-coordination-identity-policy")
    from labtrust_gym.policy.loader import load_yaml

    data = load_yaml(path)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_prompt_representation(
    prompt_template_id: str,
    state_digest: dict[str, Any],
    allowed_actions_payload_canonical: str,
    policy_slice: dict[str, Any] | None = None,
) -> str:
    """
    Deterministic string: template_id + canonical state + payload + optional policy slice.
    No timestamps; sort keys; bounded size.
    """
    state_slice = _canonical_state_slice(state_digest)
    state_str = json.dumps(state_slice, sort_keys=True, separators=(",", ":"))
    policy_str = ""
    if policy_slice:
        policy_str = json.dumps(policy_slice, sort_keys=True, separators=(",", ":"))
    return "\n".join([
        prompt_template_id,
        state_str,
        allowed_actions_payload_canonical,
        policy_str,
    ])


def compute_prompt_fingerprints(
    method_id: str,
    state_digest: dict[str, Any],
    allowed_actions: list[str],
    policy: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    *,
    include_inputs_for_verify: bool = True,
) -> dict[str, Any]:
    """
    Compute prompt_template_id, prompt_sha256, allowed_actions_payload_sha256,
    coordination_policy_fingerprint for coordination LLM runs.

    Same seed + same policy => same hashes. Changing policy file changes
    coordination_policy_fingerprint; changing allowed_actions or state_digest
    changes allowed_actions_payload_sha256 and prompt_sha256.

    When include_inputs_for_verify is True, the returned dict also includes
    prompt_fingerprint_inputs: { state_digest_slice, allowed_actions_payload_canonical,
    policy_slice } for verify-bundle to recompute prompt_sha256.
    """
    from labtrust_gym.baselines.llm.allowed_actions_payload import (
        build_allowed_actions_payload,
        serialize_allowed_actions_payload,
    )
    from labtrust_gym.config import get_repo_root

    policy = policy or {}
    root = Path(repo_root) if repo_root else get_repo_root()
    root = root or Path.cwd()

    template_id = prompt_template_id_for_method(method_id)
    payload = build_allowed_actions_payload(
        state=state_digest,
        allowed_actions=list(allowed_actions) if allowed_actions else [],
    )
    payload_canonical = serialize_allowed_actions_payload(payload)
    allowed_actions_payload_sha256_val = _sha256_str(payload_canonical)

    policy_slice = _canonical_policy_slice(policy)
    state_slice = _canonical_state_slice(state_digest)
    prompt_repr = canonical_prompt_representation(
        template_id,
        state_digest,
        payload_canonical,
        policy_slice if policy_slice else None,
    )
    prompt_sha256_val = _sha256_str(prompt_repr)

    coord_fp = coordination_policy_fingerprint_from_repo(root)

    out: dict[str, Any] = {
        "prompt_template_id": template_id,
        "prompt_sha256": prompt_sha256_val,
        "allowed_actions_payload_sha256": allowed_actions_payload_sha256_val,
        "coordination_policy_fingerprint": coord_fp,
    }
    if include_inputs_for_verify:
        out["prompt_fingerprint_inputs"] = {
            "prompt_template_id": template_id,
            "state_digest_slice": state_slice,
            "allowed_actions_payload_canonical": payload_canonical,
            "policy_slice": policy_slice,
        }
    return out


def recompute_prompt_sha256_from_inputs(
    prompt_template_id: str,
    state_digest_slice: dict[str, Any],
    allowed_actions_payload_canonical: str,
    policy_slice: dict[str, Any] | None = None,
) -> str:
    """
    Recompute prompt_sha256 from stored canonical inputs (for verify-bundle).
    Deterministic: same inputs => same hash.
    """
    prompt_repr = canonical_prompt_representation(
        prompt_template_id,
        state_digest_slice,
        allowed_actions_payload_canonical,
        policy_slice,
    )
    return _sha256_str(prompt_repr)
