"""
Tests for tool registry SBOM/provenance validation (validate_registry_sbom and validate-policy integration).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.tools.registry import (
    validate_registry_sbom,
)


def test_validate_registry_sbom_require_sbom_missing() -> None:
    """When require_sbom is True and a tool has no sbom_ref, validate_registry_sbom returns errors."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "require_sbom": True,
            "tools": [
                {"tool_id": "t1", "publisher": "p", "version": "0.1"},
            ],
        },
    }
    errors = validate_registry_sbom(registry, policy_root=None, require_sbom=True)
    assert len(errors) >= 1
    assert "sbom_ref" in errors[0] or "t1" in errors[0]


def test_validate_registry_sbom_with_sbom_ref_no_policy_root() -> None:
    """When sbom_ref is present and policy_root is None, no path check; require_sbom=False -> no error."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {"tool_id": "t1", "sbom_ref": "http://example.com/sbom.json"},
            ],
        },
    }
    errors = validate_registry_sbom(registry, policy_root=None, require_sbom=False)
    assert errors == []


def test_validate_registry_sbom_require_sbom_all_have_ref() -> None:
    """When require_sbom is True and every tool has sbom_ref, no errors (path not checked if no policy_root)."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {"tool_id": "t1", "sbom_ref": "https://example.com/sbom.json"},
            ],
        },
    }
    errors = validate_registry_sbom(registry, policy_root=None, require_sbom=True)
    assert errors == []


def test_validate_policy_strict_tool_provenance_adds_sbom_errors(tmp_path: Path) -> None:
    """validate_policy with strict_tool_provenance=True and registry without sbom_ref yields SBOM errors."""
    from labtrust_gym.policy.validate import validate_policy

    registry_no_sbom = {
        "tool_registry": {"version": "0.1", "tools": [{"tool_id": "t1", "publisher": "p"}]},
    }
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "labtrust_gym.tools.registry.load_tool_registry",
            lambda root: registry_no_sbom if root is not None else {},
        )
        errors = validate_policy(tmp_path, partner_id=None, strict_tool_provenance=True)
    assert any("sbom_ref" in e or "SBOM" in e or "provenance" in e for e in errors)
