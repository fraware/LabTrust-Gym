"""
Coordination policy loaders: methods registry, method-risk matrix, study spec.

- load_coordination_methods(path) -> dict (method_id -> method entry).
- load_method_risk_matrix(path) -> dict (matrix metadata + cells list).
- load_coordination_study_spec(path) -> dict (study_id, scales, methods, risks,
  injections, etc.).

Deterministic: same file content yields same structure; no ambient randomness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


def load_coordination_methods(path: Path | str) -> dict[str, dict[str, Any]]:
    """
    Load coordination method registry from YAML.
    Returns dict method_id -> method entry. Path may be relative to cwd or absolute.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    root = data.get("coordination_methods")
    if root is None:
        raise PolicyLoadError(p, "missing top-level key 'coordination_methods'")
    raw_list = root.get("methods")
    if not isinstance(raw_list, list):
        raise PolicyLoadError(
            p,
            f"coordination_methods.methods must be a list, got {type(raw_list).__name__}",
        )
    out: dict[str, dict[str, Any]] = {}
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        method_id = entry.get("method_id")
        if method_id and isinstance(method_id, str):
            out[method_id] = dict(entry)
    return out


def load_method_risk_matrix(path: Path | str) -> dict[str, Any]:
    """
    Load method-risk matrix from YAML.
    Returns dict with matrix_id, version, cells (list).
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    root = data.get("method_risk_matrix")
    if root is None:
        raise PolicyLoadError(p, "missing top-level key 'method_risk_matrix'")
    cells = root.get("cells")
    if not isinstance(cells, list):
        raise PolicyLoadError(
            p,
            f"method_risk_matrix.cells must be a list, got {type(cells).__name__}",
        )
    return {
        "matrix_id": str(root.get("matrix_id", "")),
        "version": str(root.get("version", "0.1")),
        "cells": list(cells),
    }


def load_coordination_study_spec(path: Path | str) -> dict[str, Any]:
    """
    Load coordination study spec from YAML.
    Returns dict with study_id, seed_base, episodes_per_cell, and optional
    scales, methods, risks, injections.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    study_id = data.get("study_id")
    if study_id is None:
        raise PolicyLoadError(p, "missing top-level key 'study_id'")
    return dict(data)


def get_required_bench_cells(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return list of cells where required_bench is True.
    matrix from load_method_risk_matrix.
    """
    cells = matrix.get("cells") or []
    return [c for c in cells if isinstance(c, dict) and c.get("required_bench") is True]
