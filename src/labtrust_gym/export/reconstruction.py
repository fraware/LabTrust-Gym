"""
PCS release reconstruction provenance (LTG-PR6 / LTG-07).

Unifies digests and identity fields so EvidenceBundle manifests, pack_manifest.json,
and RELEASE_MANIFEST.v0.1.json carry (or link to) the fields needed for independent
offline reconstruction and verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.orchestrator.replay import (
    canonical_episode_log_digest,
    evidence_digest,
)
from labtrust_gym.util.json_utils import canonical_json

# Stable environment binding for the default hospital_lab family (aligned with
# EnvironmentProfile.v1 seed profile versions, without requiring a full VA profile).
DEFAULT_ENVIRONMENT_FAMILY = "hospital_lab"
DEFAULT_ENVIRONMENT_VERSION = "0.2.0"
DEFAULT_OBSERVATION_SCHEMA_VERSION = "labtrust.obs.v0.2"
DEFAULT_ACTION_SCHEMA_VERSION = "labtrust.action_contract.v0.2"

RECONSTRUCTION_KEYS = (
    "policy_digest",
    "environment_digest",
    "agent_identity",
    "seed",
    "scenario_ids",
    "episode_log_digest",
    "evidence_digest",
    "risk_register_refs",
    "verification_results",
    "missing_evidence",
)


def compute_environment_digest(
    *,
    policy_digest: str | None = None,
    environment_family: str = DEFAULT_ENVIRONMENT_FAMILY,
    environment_version: str = DEFAULT_ENVIRONMENT_VERSION,
    observation_schema_version: str = DEFAULT_OBSERVATION_SCHEMA_VERSION,
    action_schema_version: str = DEFAULT_ACTION_SCHEMA_VERSION,
    tool_registry_fingerprint: str | None = None,
    rbac_policy_fingerprint: str | None = None,
) -> str:
    """
    SHA-256 digest binding environment family/version, observation/action schemas,
    and policy/tool/rbac fingerprints used for the run.
    """
    body = {
        "action_schema_version": action_schema_version,
        "environment_family": environment_family,
        "environment_version": environment_version,
        "observation_schema_version": observation_schema_version,
        "policy_digest": policy_digest or "",
        "rbac_policy_fingerprint": rbac_policy_fingerprint or "",
        "tool_registry_fingerprint": tool_registry_fingerprint or "",
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def extract_run_provenance(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize agent identity, seed, and scenario IDs from results.json-style metadata.

    Accepts either a full results.v0.2 object or a flat dict with the same keys.
    """
    if not run_meta or not isinstance(run_meta, dict):
        return {
            "agent_identity": None,
            "seed": None,
            "scenario_ids": [],
        }
    agent = run_meta.get("agent_identity")
    if agent is None:
        agent = run_meta.get("agent_baseline_id")
    seed = run_meta.get("seed")
    if seed is None:
        seed = run_meta.get("base_seed")
    if seed is None:
        seeds = run_meta.get("seeds")
        if isinstance(seeds, list) and seeds:
            seed = seeds[0]
    scenario_ids = run_meta.get("scenario_ids")
    if not isinstance(scenario_ids, list):
        scenario_ids = []
    else:
        scenario_ids = [str(s) for s in scenario_ids if s is not None]
    task = run_meta.get("task") or run_meta.get("scenario_id")
    if task and str(task) not in scenario_ids:
        scenario_ids = [str(task), *scenario_ids]
    return {
        "agent_identity": str(agent) if agent is not None else None,
        "seed": int(seed) if seed is not None else None,
        "scenario_ids": scenario_ids,
    }


def load_run_meta_from_dir(run_dir: Path) -> dict[str, Any]:
    """Load results.json from run_dir if present; return empty dict otherwise."""
    results_path = Path(run_dir) / "results.json"
    if not results_path.is_file():
        return {}
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_reconstruction_block(
    *,
    entries: list[dict[str, Any]] | None = None,
    policy_digest: str | None = None,
    agent_identity: str | None = None,
    seed: int | None = None,
    scenario_ids: list[str] | None = None,
    risk_register_refs: list[str] | None = None,
    verification_results: dict[str, Any] | None = None,
    missing_evidence: list[dict[str, Any]] | None = None,
    tool_registry_fingerprint: str | None = None,
    rbac_policy_fingerprint: str | None = None,
    environment_family: str = DEFAULT_ENVIRONMENT_FAMILY,
    environment_version: str = DEFAULT_ENVIRONMENT_VERSION,
    observation_schema_version: str = DEFAULT_OBSERVATION_SCHEMA_VERSION,
    action_schema_version: str = DEFAULT_ACTION_SCHEMA_VERSION,
    episode_log_digest: str | None = None,
    evidence_digest_value: str | None = None,
) -> dict[str, Any]:
    """
    Build the reconstruction provenance object for EvidenceBundle / pack / RELEASE_MANIFEST.

    Digests are computed from entries when not supplied explicitly.
    """
    entries = entries or []
    policy = policy_digest or ""
    env_digest = compute_environment_digest(
        policy_digest=policy,
        environment_family=environment_family,
        environment_version=environment_version,
        observation_schema_version=observation_schema_version,
        action_schema_version=action_schema_version,
        tool_registry_fingerprint=tool_registry_fingerprint,
        rbac_policy_fingerprint=rbac_policy_fingerprint,
    )
    ep_digest = episode_log_digest
    if ep_digest is None and entries:
        ep_digest = canonical_episode_log_digest(entries)
    ev_digest = evidence_digest_value
    if ev_digest is None and entries:
        ev_digest = evidence_digest(entries)
    return {
        "policy_digest": policy or None,
        "environment_digest": env_digest,
        "agent_identity": agent_identity,
        "seed": seed,
        "scenario_ids": list(scenario_ids or []),
        "episode_log_digest": ep_digest,
        "evidence_digest": ev_digest,
        "risk_register_refs": list(risk_register_refs or []),
        "verification_results": verification_results,
        "missing_evidence": list(missing_evidence or []),
    }


def missing_evidence_from_risk_register(bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract status=missing evidence declarations from a risk register bundle."""
    if not bundle or not isinstance(bundle, dict):
        return []
    out: list[dict[str, Any]] = []
    for item in bundle.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "missing":
            out.append(
                {
                    "risk_id": item.get("risk_id"),
                    "status": "missing",
                    "expected_sources": item.get("expected_sources") or [],
                }
            )
    return out


def aggregate_release_reconstruction(
    *,
    bundle_reconstructions: list[dict[str, Any]],
    risk_register_path: str | None = None,
    missing_evidence: list[dict[str, Any]] | None = None,
    verify_report_refs: list[str] | None = None,
    pack_reconstruction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Aggregate per-bundle reconstruction blocks into a release-level reconstruction object.
    """
    policy_digests: list[str] = []
    env_digests: list[str] = []
    agents: list[str] = []
    seeds: list[int] = []
    scenarios: list[str] = []
    episode_digests: list[str] = []
    evidence_digests: list[str] = []

    for block in bundle_reconstructions:
        if not isinstance(block, dict):
            continue
        pd = block.get("policy_digest")
        if pd and pd not in policy_digests:
            policy_digests.append(str(pd))
        ed = block.get("environment_digest")
        if ed and ed not in env_digests:
            env_digests.append(str(ed))
        ai = block.get("agent_identity")
        if ai and str(ai) not in agents:
            agents.append(str(ai))
        seed = block.get("seed")
        if seed is not None and int(seed) not in seeds:
            seeds.append(int(seed))
        for sid in block.get("scenario_ids") or []:
            if sid is not None and str(sid) not in scenarios:
                scenarios.append(str(sid))
        ep = block.get("episode_log_digest")
        if ep and ep not in episode_digests:
            episode_digests.append(str(ep))
        ev = block.get("evidence_digest")
        if ev and ev not in evidence_digests:
            evidence_digests.append(str(ev))

    if pack_reconstruction:
        pd = pack_reconstruction.get("policy_digest")
        if pd and pd not in policy_digests:
            policy_digests.append(str(pd))
        ed = pack_reconstruction.get("environment_digest")
        if ed and ed not in env_digests:
            env_digests.append(str(ed))
        for ai in pack_reconstruction.get("agent_identities") or []:
            if ai and str(ai) not in agents:
                agents.append(str(ai))
        seed = pack_reconstruction.get("seed")
        if seed is not None and int(seed) not in seeds:
            seeds.append(int(seed))
        for sid in pack_reconstruction.get("scenario_ids") or []:
            if sid is not None and str(sid) not in scenarios:
                scenarios.append(str(sid))

    risk_refs: list[str] = []
    if risk_register_path:
        risk_refs.append(risk_register_path)

    verification_results: dict[str, Any] = {
        "status": "offline_verifiable",
        "commands": [
            "labtrust verify-release --release-dir <dir> --strict-fingerprints",
            "labtrust verify-bundle --bundle <EvidenceBundle.v0.1>",
        ],
        "report_refs": list(verify_report_refs or []),
    }

    return {
        "policy_digest": policy_digests[0] if len(policy_digests) == 1 else None,
        "policy_digests": policy_digests,
        "environment_digest": env_digests[0] if len(env_digests) == 1 else None,
        "environment_digests": env_digests,
        "agent_identity": agents[0] if len(agents) == 1 else None,
        "agent_identities": agents,
        "seed": seeds[0] if len(seeds) == 1 else None,
        "seeds": seeds,
        "scenario_ids": scenarios,
        "episode_log_digests": episode_digests,
        "evidence_digests": evidence_digests,
        "risk_register_refs": risk_refs,
        "verification_results": verification_results,
        "missing_evidence": list(missing_evidence or []),
    }


def build_pack_reconstruction(
    *,
    seed_base: int,
    tasks: list[str],
    baselines: dict[str, Any] | list[str] | None,
    policy_digest: str | None = None,
    tool_registry_fingerprint: str | None = None,
    rbac_policy_fingerprint: str | None = None,
    risk_register_refs: list[str] | None = None,
    missing_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build reconstruction block for official pack_manifest.json."""
    agent_identities: list[str] = []
    if isinstance(baselines, dict):
        for v in baselines.values():
            if v is not None and str(v) not in agent_identities:
                agent_identities.append(str(v))
    elif isinstance(baselines, list):
        for v in baselines:
            if v is not None and str(v) not in agent_identities:
                agent_identities.append(str(v))
    env_digest = compute_environment_digest(
        policy_digest=policy_digest,
        tool_registry_fingerprint=tool_registry_fingerprint,
        rbac_policy_fingerprint=rbac_policy_fingerprint,
    )
    return {
        "policy_digest": policy_digest,
        "environment_digest": env_digest,
        "agent_identity": agent_identities[0] if len(agent_identities) == 1 else None,
        "agent_identities": agent_identities,
        "seed": seed_base,
        "scenario_ids": list(tasks),
        "episode_log_digests": [],
        "evidence_digests": [],
        "risk_register_refs": list(risk_register_refs or []),
        "verification_results": {
            "status": "offline_verifiable",
            "commands": [
                "labtrust verify-release --release-dir <dir>",
                "labtrust verify-bundle --bundle <EvidenceBundle.v0.1>",
            ],
            "report_refs": [],
        },
        "missing_evidence": list(missing_evidence or []),
    }
