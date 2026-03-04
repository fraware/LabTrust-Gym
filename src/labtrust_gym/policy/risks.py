"""
Risk registry loader: policy/risks/risk_registry.v0.1.yaml.

- load_risk_registry(path) -> RiskRegistry (version + risks dict).
- get_risk(registry, risk_id) -> optional risk entry dict.
Deterministic: same file content yields same in-memory structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


@dataclass
class RiskRegistry:
    """Loaded risk registry: version and risk_id -> entry mapping."""

    version: str
    risks: dict[str, dict[str, Any]]


def load_risk_registry(path: Path | str) -> RiskRegistry:
    """
    Load risk registry from YAML. Returns RiskRegistry with risks keyed by
    risk_id. Path may be relative to cwd or absolute. Deterministic for same
    file content.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    root = data.get("risk_registry")
    if root is None:
        raise PolicyLoadError(p, "missing top-level key 'risk_registry'")
    version = str(root.get("version", "0.1"))
    raw_list = root.get("risks")
    if not isinstance(raw_list, list):
        raise PolicyLoadError(
            p,
            f"risk_registry.risks must be a list, got {type(raw_list).__name__}",
        )
    risks: dict[str, dict[str, Any]] = {}
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        risk_id = entry.get("risk_id")
        if risk_id and isinstance(risk_id, str):
            risks[risk_id] = dict(entry)
    return RiskRegistry(version=version, risks=risks)


def get_risk(registry: RiskRegistry, risk_id: str) -> dict[str, Any] | None:
    """Lookup risk by risk_id. Returns risk entry dict or None if not found."""
    return registry.risks.get(risk_id) if risk_id else None


@dataclass
class RiskCoverageRegistry:
    """
    Loaded risk coverage registry: version and risk_id -> coverage entry
    (injection_ids, attack_ids, or not_applicable_justification).
    """

    version: str
    coverage: dict[str, dict[str, Any]]


def load_risk_coverage_registry(path: Path | str) -> RiskCoverageRegistry:
    """
    Load risk coverage registry from YAML. Returns RiskCoverageRegistry
    with coverage keyed by risk_id. Each entry must have at least one of:
    injection_ids, attack_ids, not_applicable_justification.
    Path may be relative to cwd or absolute. Deterministic for same content.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    root = data.get("risk_coverage_registry")
    if root is None:
        raise PolicyLoadError(p, "missing top-level key 'risk_coverage_registry'")
    version = str(root.get("version", "0.1"))
    raw_list = root.get("coverage")
    if not isinstance(raw_list, list):
        raise PolicyLoadError(
            p,
            f"risk_coverage_registry.coverage must be a list, got {type(raw_list).__name__}",
        )
    coverage: dict[str, dict[str, Any]] = {}
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        risk_id = entry.get("risk_id")
        if risk_id and isinstance(risk_id, str):
            coverage[risk_id] = dict(entry)
    return RiskCoverageRegistry(version=version, coverage=coverage)
