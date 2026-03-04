"""
Coordination policy loaders: method registry, method-risk matrix, study spec.

Loads the coordination method registry (method_id -> method entry), the
method-risk matrix (metadata and cells), and the coordination study spec
(study_id, scales, methods, risks, injections). All reads are deterministic:
same file content yields the same structure. Used by benchmarks and studies
to resolve method variants and LLM-based method IDs (LLM = large language model).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


def load_coordination_methods(path: Path | str) -> dict[str, dict[str, Any]]:
    """
    Load coordination method registry from YAML.
    Returns dict method_id -> method entry.
    Path may be relative to cwd or absolute.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    root = data.get("coordination_methods")
    if root is None:
        raise PolicyLoadError(p, "missing top-level 'coordination_methods'")
    raw_list = root.get("methods")
    if not isinstance(raw_list, list):
        raise PolicyLoadError(
            p,
            f"coordination_methods.methods must be list, got {type(raw_list).__name__}",
        )
    out: dict[str, dict[str, Any]] = {}
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        method_id = entry.get("method_id")
        if method_id and isinstance(method_id, str):
            out[method_id] = dict(entry)
    return out


def list_llm_coordination_method_ids(path: Path | str) -> list[str]:
    """
    Return method_ids that are LLM-based coordination methods (for comparison).
    Uses llm_based if present, else coordination_class == "llm".
    Path may be relative to cwd or absolute.
    """
    registry = load_coordination_methods(path)
    out: list[str] = []
    for method_id, entry in registry.items():
        llm_based = entry.get("llm_based")
        if llm_based is True:
            out.append(method_id)
        elif llm_based is None:
            if entry.get("coordination_class") == "llm":
                out.append(method_id)
    return sorted(out)


def list_scale_capable_method_ids(path: Path | str) -> list[str]:
    """
    Return method_ids that are scale-capable: at N > N_max the runner may
    populate scripted_agents_map with one LLMAgentWithShield per agent.

    Uses scale_capable: true in the method entry. For backward compatibility,
    if no method in the registry has scale_capable set to True, returns
    the legacy set ["llm_constrained", "llm_central_planner"].
    Path may be relative to cwd or absolute.
    """
    registry = load_coordination_methods(path)
    out: list[str] = []
    for method_id, entry in registry.items():
        if entry.get("scale_capable") is True:
            out.append(method_id)
    if not out:
        return sorted(["llm_constrained", "llm_central_planner"])
    return sorted(out)


def resolve_method_variant(
    method_id: str,
    methods_registry: dict[str, dict[str, Any]],
) -> tuple[str, str | None]:
    """
    Resolve a method_id to its base method and optional defense profile.
    If the entry has base_method, returns (base_method_id, defense_profile).
    Otherwise returns (method_id, None).
    """
    entry = methods_registry.get(method_id) if methods_registry else None
    if not entry:
        return (method_id, None)
    base = entry.get("base_method")
    if not base or not isinstance(base, str):
        return (method_id, None)
    profile = entry.get("defense_profile")
    if profile is not None and not isinstance(profile, str):
        profile = None
    return (base, profile)


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
        raise PolicyLoadError(p, "missing top-level 'method_risk_matrix'")
    cells = root.get("cells")
    if not isinstance(cells, list):
        raise PolicyLoadError(
            p,
            f"method_risk_matrix.cells must be list, got {type(cells).__name__}",
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


def load_submission_shapes(
    path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, str]:
    """Load coordination_submission_shapes.v0.1.yaml; return method_id -> action|bid|vote."""
    if path is None and repo_root is None:
        return {}
    if path is None:
        root = Path(repo_root) if isinstance(repo_root, str) else repo_root
        path = root / "policy" / "coordination" / "coordination_submission_shapes.v0.1.yaml"
    p = Path(path)
    if not p.is_absolute() and repo_root is not None:
        root = Path(repo_root) if isinstance(repo_root, str) else repo_root
        p = root / p
    if not p.is_file():
        return {}
    data = load_yaml(p)
    shapes = data.get("submission_shapes")
    if not isinstance(shapes, dict):
        return {}
    return {k: str(v).strip().lower() for k, v in shapes.items() if v}


def get_submission_shape(
    method_id: str,
    shapes: dict[str, str] | None = None,
    methods_registry: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Return submission shape for method_id: action, bid, or vote (default action)."""
    if shapes is None:
        shapes = {}
    shape = shapes.get(method_id) if shapes else None
    if shape in ("action", "bid", "vote"):
        return shape
    if methods_registry:
        base, _ = resolve_method_variant(method_id, methods_registry)
        if base != method_id and shapes:
            shape = shapes.get(base)
            if shape in ("action", "bid", "vote"):
                return shape
    return "action"


def adapt_submission(
    shape: str,
    action_index: int,
    action_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert (action_index, action_info) from agent.act() into the submission shape
    expected by combine_submissions for the given method shape (action, bid, vote).
    """
    shape = (shape or "action").strip().lower()
    if shape == "action":
        return {"action_index": action_index, **(action_info or {})}
    if shape == "bid":
        bid = dict(action_info or {})
        for k in (
            "action_type",
            "reason_code",
            "token_refs",
            "rationale",
            "confidence",
            "safety_notes",
            "action_index",
        ):
            bid.pop(k, None)
        bid.setdefault("cost", 0)
        return {"bid": bid}
    if shape == "vote":
        vote_val = (action_info or {}).get("vote", action_index)
        return {"vote": vote_val}
    return {"action_index": action_index, **(action_info or {})}


def load_risk_to_injection_map(path: Path | str | None = None) -> dict[str, list[str]]:
    """
    Load risk_to_injection_map from YAML. Returns dict risk_id -> list of injection_ids.
    Path optional; when None, returns {}. Used by coverage preflight; fallback is risk_registry.
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.is_file():
        return {}
    data = load_yaml(p)
    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        return {}
    out: dict[str, list[str]] = {}
    for entry in mappings:
        if not isinstance(entry, dict):
            continue
        risk_id = entry.get("risk_id")
        ids_raw = entry.get("injection_ids")
        if risk_id and isinstance(risk_id, str):
            out[risk_id] = (
                [str(x) for x in ids_raw if x] if isinstance(ids_raw, list) else ([str(ids_raw)] if ids_raw else [])
            )
    return out


def injection_id_to_risk_id_map(
    map_path: Path | str | None = None,
) -> dict[str, str]:
    """
    Build injection_id -> risk_id from risk_to_injection map (first risk that lists
    the injection). Used when a single risk_id per row is needed (backward compat).
    """
    risk_to_inj = load_risk_to_injection_map(map_path)
    out: dict[str, str] = {}
    for risk_id, injection_ids in risk_to_inj.items():
        for iid in injection_ids:
            if iid and iid not in out:
                out[iid] = risk_id
    return out


def injection_id_to_risk_ids_map(
    map_path: Path | str | None = None,
) -> dict[str, list[str]]:
    """
    Build injection_id -> list of risk_ids that this injection covers (from
    risk_to_injection map). Used by study runner so one cell can produce
    multiple summary rows (one per risk_id) for coverage gate.
    """
    risk_to_inj = load_risk_to_injection_map(map_path)
    out: dict[str, list[str]] = {}
    for risk_id, injection_ids in risk_to_inj.items():
        for iid in injection_ids:
            if iid:
                out.setdefault(iid, []).append(risk_id)
    return out
