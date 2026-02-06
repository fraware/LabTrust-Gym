"""
Tests for tool registry gate (B010): unknown tool_id BLOCKED, hash validation, EvidenceBundle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.auth.authorize import (
    is_tool_allowed,
    rbac_policy_fingerprint,
)
from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.tools.registry import (
    TOOL_NOT_ALLOWED_FOR_ROLE,
    TOOL_NOT_IN_REGISTRY,
    check_tool_allowed,
    combined_policy_fingerprint,
    get_tool_entry,
    load_tool_registry,
    tool_registry_fingerprint,
    validate_registry_hashes,
)


def _minimal_initial_state(tool_registry: dict) -> dict:
    """Minimal initial_state so CoreEnv reset and step (tool gate) run."""
    return {
        "effective_policy": {},
        "agents": [{"agent_id": "A_OPS_0", "zone_id": "Z_MAIN"}],
        "zone_layout": {
            "zones": [{"zone_id": "Z_MAIN"}],
            "graph_edges": [],
            "doors": [],
            "device_placement": {},
        },
        "specimens": [],
        "tokens": [],
        "audit_fault_injection": None,
        "tool_registry": tool_registry,
    }


def test_unknown_tool_id_blocked_with_reason_code(tmp_path: Path) -> None:
    """Any tool call with unknown tool_id is BLOCKED with deterministic blocked_reason_code."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                    "capabilities": ["read_lims"],
                    "risk_class": "low",
                },
            ],
        },
    }
    initial_state = _minimal_initial_state(registry)
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    # Event with unknown tool_id must be BLOCKED with TOOL_NOT_IN_REGISTRY.
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {},
        "tool_id": "unknown_tool_xyz",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_NOT_IN_REGISTRY


def test_registered_tool_id_allowed(tmp_path: Path) -> None:
    """Event with tool_id in registry and valid args passes tool gate and arg validation."""
    from labtrust_gym.config import get_repo_root

    repo_root = Path(get_repo_root())
    registry = load_tool_registry(repo_root)
    if not registry.get("tool_registry", {}).get("tools"):
        pytest.skip("policy/tool_registry.v0.1.yaml has no tools")
    initial_state = _minimal_initial_state(registry)
    initial_state["policy_root"] = repo_root
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 0,
        "agent_id": "A_OPS_0",
        "action_type": "TICK",
        "args": {"accession_id": "ACC001"},
        "tool_id": "read_lims_v1",
    }
    result = env.step(event)
    assert result.get("blocked_reason_code") != TOOL_NOT_IN_REGISTRY
    assert result.get("blocked_reason_code") != TOOL_NOT_ALLOWED_FOR_ROLE
    assert result.get("blocked_reason_code") not in (
        "TOOL_ARG_SCHEMA_FAIL",
        "TOOL_ARG_RANGE_FAIL",
    )


def test_tool_not_allowed_for_role_when_allow_list_restricts() -> None:
    """When allowed_tools is set and tool_id not in list, BLOCKED with TOOL_NOT_ALLOWED_FOR_ROLE."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                },
                {
                    "tool_id": "write_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                },
            ],
        },
    }
    allowed, reason = check_tool_allowed(
        "write_lims_v1",
        registry,
        allowed_tools=["read_lims_v1"],
    )
    assert allowed is False
    assert reason == TOOL_NOT_ALLOWED_FOR_ROLE

    allowed2, reason2 = check_tool_allowed(
        "read_lims_v1",
        registry,
        allowed_tools=["read_lims_v1"],
    )
    assert allowed2 is True
    assert reason2 is None


def test_tool_excluded_for_role_rbac_blocked() -> None:
    """RBAC allowed_tool_ids: if tool_id not in list -> BLOCKED with TOOL_NOT_ALLOWED_FOR_ROLE."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                },
                {
                    "tool_id": "write_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                },
            ],
        },
    }
    rbac_policy = {
        "version": "0.1",
        "roles": {
            "ROLE_READ_ONLY": {
                "allowed_actions": ["TICK"],
                "allowed_tool_ids": ["read_lims_v1"],
            },
        },
        "agents": {"A_OPS_0": "ROLE_READ_ONLY"},
        "action_constraints": {},
    }
    initial_state = _minimal_initial_state(registry)
    initial_state["effective_policy"] = {"rbac_policy": rbac_policy}
    env = CoreEnv()
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 10,
        "agent_id": "A_OPS_0",
        "action_type": "INVOKE_TOOL",
        "args": {},
        "tool_id": "write_lims_v1",
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == TOOL_NOT_ALLOWED_FOR_ROLE

    allowed, reason = is_tool_allowed(
        "ROLE_READ_ONLY",
        "read_lims_v1",
        registry,
        rbac_policy,
        {},
    )
    assert allowed is True
    assert reason is None
    allowed2, reason2 = is_tool_allowed(
        "ROLE_READ_ONLY",
        "write_lims_v1",
        registry,
        rbac_policy,
        {},
    )
    assert allowed2 is False
    assert reason2 == TOOL_NOT_ALLOWED_FOR_ROLE


def test_registry_entry_mismatched_hash_fails_validation() -> None:
    """Any registry entry with mismatched hash fails validate_registry_hashes."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                    "sha256": "abc123def456",
                },
            ],
        },
    }
    errors = validate_registry_hashes(
        registry,
        expected_hashes={"read_lims_v1": "different_expected_hash"},
    )
    assert len(errors) == 1
    assert "does not match expected" in errors[0]

    errors_match = validate_registry_hashes(
        registry,
        expected_hashes={"read_lims_v1": "abc123def456"},
    )
    assert len(errors_match) == 0


def test_tool_registry_fingerprint_stable() -> None:
    """Same registry content yields same fingerprint; different content yields different."""
    reg1 = {
        "tool_registry": {
            "version": "0.1",
            "tools": [{"tool_id": "a", "publisher": "p", "version": "1"}],
        }
    }
    fp1 = tool_registry_fingerprint(reg1)
    fp2 = tool_registry_fingerprint(reg1)
    assert fp1 == fp2
    reg2 = {
        "tool_registry": {
            "version": "0.1",
            "tools": [{"tool_id": "b", "publisher": "p", "version": "1"}],
        }
    }
    fp3 = tool_registry_fingerprint(reg2)
    assert fp3 != fp1


def test_combined_policy_fingerprint_includes_tool_registry() -> None:
    """combined_policy_fingerprint incorporates tool registry digest."""
    policy_fp = "a" * 64
    tool_fp = "b" * 64
    combined = combined_policy_fingerprint(policy_fp, tool_fp)
    assert combined != policy_fp
    assert len(combined) == 64
    assert combined == combined_policy_fingerprint(policy_fp, tool_fp)


def test_evidence_bundle_includes_tool_registry_digest_and_verification_checks(
    tmp_path: Path,
) -> None:
    """EvidenceBundle includes tool_registry digest; verification report checks it."""
    from labtrust_gym.export.receipts import write_evidence_bundle
    from labtrust_gym.export.verify import verify_bundle

    receipts = [
        {
            "version": "0.1",
            "entity_type": "specimen",
            "specimen_id": "S1",
            "result_id": None,
            "accession_ids": [],
            "panel_id": None,
            "device_ids": [],
            "timestamps": {},
            "decision": "RELEASED",
            "reason_codes": [],
            "tokens": {"minted": [], "consumed": [], "revoked": []},
            "critical_comm_records": {"attempts": [], "ack_summary": []},
            "invariant_summary": {
                "violated_ids": [],
                "first_violation_ts": None,
                "final_status": "PASS",
            },
            "enforcement_summary": {
                "throttle": [],
                "kill_switch": [],
                "freeze_zone": [],
                "forensic_freeze": [],
            },
            "hashchain": {"head_hash": "", "last_event_hash": "", "length": 0},
        },
    ]
    entries = [
        {
            "t_s": 0,
            "agent_id": "A_OPS_0",
            "action_type": "TICK",
            "status": "ACCEPTED",
            "blocked_reason_code": None,
            "emits": [],
            "violations": [],
            "token_consumed": [],
            "hashchain_head": "h1",
            "hashchain": {"head_hash": "h1", "length": 1, "last_event_hash": "e1"},
        },
    ]
    tool_fp = "c" * 64
    policy_fp = "d" * 64
    out = tmp_path / "bundle"
    out.mkdir()
    write_evidence_bundle(
        out,
        receipts,
        entries,
        policy_fingerprint=policy_fp,
        partner_id=None,
        policy_root=None,
        tool_registry_fingerprint=tool_fp,
    )
    manifest_path = out / "EvidenceBundle.v0.1" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("tool_registry_fingerprint") == tool_fp
    # policy_fingerprint is combined (not raw policy_fp) when tool_registry_fingerprint set
    assert manifest.get("policy_fingerprint") != policy_fp
    assert len(manifest["policy_fingerprint"]) == 64

    # If policy_root has no tool_registry, verification reports error for tool_registry_fingerprint.
    passed, report, errors = verify_bundle(
        out / "EvidenceBundle.v0.1",
        policy_root=tmp_path,
        allow_extra_files=True,
    )
    assert "tool_registry_fingerprint" in manifest
    if not passed and errors:
        assert any("tool_registry" in e or "tool_registry_fingerprint" in e for e in errors)


def test_get_tool_entry() -> None:
    """get_tool_entry returns entry for tool_id or None."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "publisher": "labtrust",
                    "version": "0.1.0",
                },
            ],
        },
    }
    assert get_tool_entry(registry, "read_lims_v1") is not None
    assert get_tool_entry(registry, "read_lims_v1")["tool_id"] == "read_lims_v1"
    assert get_tool_entry(registry, "nonexistent") is None


def test_load_tool_registry_from_repo(repo_root: Path) -> None:
    """Load tool registry from repo policy path (when policy file exists)."""
    reg_path = repo_root / "policy" / "tool_registry.v0.1.yaml"
    reg = load_tool_registry(repo_root)
    if reg_path.exists():
        assert "tool_registry" in reg
        assert isinstance(reg["tool_registry"].get("tools"), list)
        fp = tool_registry_fingerprint(reg)
        assert len(fp) == 64
    else:
        assert reg == {} or "tool_registry" in reg


def test_evidence_bundle_verify_recomputes_rbac_and_tool_fingerprints(repo_root: Path, tmp_path: Path) -> None:
    """Verify bundle recomputes RBAC and tool registry fingerprints from policy_root."""
    from labtrust_gym.engine.rbac import load_rbac_policy
    from labtrust_gym.export.receipts import write_evidence_bundle
    from labtrust_gym.export.verify import verify_bundle

    rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    reg = load_tool_registry(repo_root)
    rbac_policy = load_rbac_policy(rbac_path)
    if not rbac_policy.get("roles") or not reg.get("tool_registry", {}).get("tools"):
        pytest.skip("repo policy rbac and tool_registry required")
    rbac_fp = rbac_policy_fingerprint(rbac_policy)
    tool_fp = tool_registry_fingerprint(reg)
    receipts = []
    entries = [
        {
            "t_s": 0,
            "agent_id": "A_OPS_0",
            "action_type": "TICK",
            "status": "ACCEPTED",
            "blocked_reason_code": None,
            "emits": [],
            "violations": [],
            "token_consumed": [],
            "hashchain_head": "",
            "hashchain": {"head_hash": "", "length": 1, "last_event_hash": ""},
            "policy_fingerprint": "a" * 64,
            "tool_registry_fingerprint": tool_fp,
            "rbac_policy_fingerprint": rbac_fp,
        }
    ]
    out = tmp_path / "bundle"
    out.mkdir()
    write_evidence_bundle(
        out,
        receipts,
        entries,
        policy_fingerprint="a" * 64,
        tool_registry_fingerprint=tool_fp,
        rbac_policy_fingerprint=rbac_fp,
    )
    manifest_path = out / "EvidenceBundle.v0.1" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("rbac_policy_fingerprint") == rbac_fp
    assert manifest.get("tool_registry_fingerprint") == tool_fp
    passed, report, errors = verify_bundle(
        out / "EvidenceBundle.v0.1",
        policy_root=repo_root,
        allow_extra_files=True,
    )
    assert passed, f"verify_bundle failed: {errors}"


@pytest.fixture
def repo_root() -> Path:
    """Repo root for policy paths (tests may run from repo root)."""
    return Path(__file__).resolve().parent.parent
