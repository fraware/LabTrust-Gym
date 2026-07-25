"""
LTG-PR7 / LTG-08: pinned public release for external agent and adapter gates.

The pin binds integrations to the frozen official baselines pack under
``benchmarks/baselines_official/v0.2`` and the committed VA release pack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root

PIN_REL_PATH = Path("benchmarks") / "external_integrations" / "pinned_release.v1.json"
PIN_SCHEMA_ID = "ExternalIntegrationPin.v1"


def load_pinned_release(repo_root: Path | None = None) -> dict[str, Any]:
    """Load and validate the ExternalIntegrationPin.v1 manifest."""
    root = Path(repo_root) if repo_root is not None else get_repo_root()
    path = root / PIN_REL_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Pinned release manifest missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Pinned release must be a JSON object: {path}")
    if data.get("schema_id") != PIN_SCHEMA_ID:
        raise ValueError(f"Expected schema_id={PIN_SCHEMA_ID!r}, got {data.get('schema_id')!r}")
    if not data.get("no_live_llm", False):
        raise ValueError("Pinned release must set no_live_llm=true for default CI path")
    for key in ("baselines_pack", "va_release_pack", "smoke", "pin_id"):
        if key not in data:
            raise ValueError(f"Pinned release missing required key: {key}")
    return data


def baselines_pack_dir(pin: dict[str, Any], repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else get_repo_root()
    return root / str(pin["baselines_pack"]["path"])


def va_release_pack_dir(pin: dict[str, Any], repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else get_repo_root()
    return root / str(pin["va_release_pack"]["path"])


def load_baselines_metadata(pin: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    """Load frozen baselines metadata.json and check pin digests."""
    root = Path(repo_root) if repo_root is not None else get_repo_root()
    pack = pin["baselines_pack"]
    meta_path = baselines_pack_dir(pin, root) / str(pack["metadata_file"])
    if not meta_path.is_file():
        raise FileNotFoundError(f"Baselines metadata missing: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise ValueError(f"Invalid baselines metadata: {meta_path}")
    expected_fp = str(pack["policy_fingerprint"])
    actual_fp = str(meta.get("policy_fingerprint") or "")
    if actual_fp != expected_fp:
        raise ValueError(
            f"Pin policy_fingerprint mismatch: pin={expected_fp!r} metadata={actual_fp!r}"
        )
    git_prefix = str(pack.get("git_sha_prefix") or "")
    git_sha = str(meta.get("git_sha") or "")
    if git_prefix and not git_sha.startswith(git_prefix):
        raise ValueError(f"Pin git_sha_prefix {git_prefix!r} does not match metadata git_sha {git_sha!r}")
    return meta


def load_pinned_baseline_results(pin: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    """Load the frozen throughput_sla scripted_ops results JSON for the pin."""
    root = Path(repo_root) if repo_root is not None else get_repo_root()
    pack = pin["baselines_pack"]
    results_path = baselines_pack_dir(pin, root) / str(pack["results_file"])
    if not results_path.is_file():
        raise FileNotFoundError(f"Pinned baseline results missing: {results_path}")
    data = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid pinned baseline results: {results_path}")
    return data


def assert_pin_artifacts_present(pin: dict[str, Any], repo_root: Path | None = None) -> None:
    """Fail closed if the frozen packs referenced by the pin are absent."""
    root = Path(repo_root) if repo_root is not None else get_repo_root()
    load_baselines_metadata(pin, root)
    results = load_pinned_baseline_results(pin, root)
    pack = pin["baselines_pack"]
    if results.get("task") != pack["task"]:
        raise ValueError(f"Pinned results task {results.get('task')!r} != pin task {pack['task']!r}")
    if results.get("agent_baseline_id") != pack["agent_baseline_id"]:
        raise ValueError(
            f"Pinned results agent_baseline_id {results.get('agent_baseline_id')!r} "
            f"!= pin {pack['agent_baseline_id']!r}"
        )
    if int(results.get("base_seed") or -1) != int(pack["seed"]):
        raise ValueError(f"Pinned results base_seed {results.get('base_seed')!r} != pin seed {pack['seed']!r}")
    va_dir = va_release_pack_dir(pin, root)
    if not (va_dir / "release_manifest.json").is_file():
        raise FileNotFoundError(f"VA release pack missing release_manifest.json: {va_dir}")


def pin_policy_digest(pin: dict[str, Any]) -> str:
    return str(pin["baselines_pack"]["policy_fingerprint"])


def write_integration_evidence(
    out_dir: Path,
    *,
    pin: dict[str, Any],
    agent_identity: str,
    seed: int,
    scenario_ids: list[str],
    integration_id: str,
) -> Path:
    """
    Write a minimal EvidenceBundle bound to the pin and verify reconstruction digests.

    Uses synthetic episode-log entries carrying pin identity (smoke-level; not a full
    reproduce of the frozen 80-step baseline trajectory).
    """
    from labtrust_gym.export.receipts import build_receipts_from_log, write_evidence_bundle
    from labtrust_gym.export.verify import verify_bundle

    root = get_repo_root()
    policy_digest = pin_policy_digest(pin)
    entries = [
        {
            "t_s": 100,
            "agent_id": "ops_0",
            "action_type": "TICK",
            "args": {},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h0", "length": 1, "last_event_hash": "e0"},
            "seed": seed,
            "scenario_id": scenario_ids[0] if scenario_ids else pin["baselines_pack"]["task"],
            "agent_baseline_id": agent_identity,
            "integration_id": integration_id,
            "pin_id": pin["pin_id"],
        }
    ]
    receipts = build_receipts_from_log(entries)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint=policy_digest,
        partner_id=None,
        agent_identity=agent_identity,
        seed=seed,
        scenario_ids=scenario_ids,
    )
    passed, report, errors = verify_bundle(bundle_dir, policy_root=root, allow_extra_files=False)
    if not passed:
        raise AssertionError(f"verify_bundle failed for {integration_id}: {report}\n{errors}")
    return bundle_dir
