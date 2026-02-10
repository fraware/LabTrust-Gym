"""
Decomposed resilience scoring for coordination studies.

Computes resilience_score from policy-defined components (perf, safety, security,
coordination) with configurable weights, normalization ranges, and missing-metric behavior.
Deterministic: same cell_metrics and policy yield same score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import load_yaml


def load_resilience_scoring_policy(path: Path | None = None) -> dict[str, Any]:
    """
    Load resilience scoring policy from YAML. If path is None, load default
    policy/coordination/resilience_scoring.v0.1.yaml relative to repo root.
    """
    if path is not None:
        p = Path(path)
    else:
        from labtrust_gym.config import get_repo_root

        p = (
            Path(get_repo_root())
            / "policy"
            / "coordination"
            / "resilience_scoring.v0.1.yaml"
        )
    if not p.is_absolute():
        p = Path.cwd() / p
    data = load_yaml(p)
    if "weights" not in data or "components" not in data:
        raise ValueError(
            f"Invalid resilience scoring policy: missing weights or components in {p}"
        )
    return dict(data)


def _normalize(
    value: float,
    range_min: float,
    range_max: float,
    direction: str,
    saturation: list[float] | None = None,
) -> float:
    """
    Map value into [0, 1] using linear interpolation over [range_min, range_max].
    direction "higher_better" => more is better; "lower_better" => less is better.
    saturation [s0, s1] clamps output to [s0, s1]; default [0, 1].
    """
    if range_max <= range_min:
        return 0.5
    sat = saturation or [0.0, 1.0]
    s0, s1 = sat[0], sat[1]
    raw = (value - range_min) / (range_max - range_min)
    raw = max(0.0, min(1.0, raw))
    if direction == "lower_better":
        raw = 1.0 - raw
    out = s0 + raw * (s1 - s0)
    return float(max(s0, min(s1, out)))


def compute_components(
    cell_metrics: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, float]:
    """
    Compute per-component scores from cell_metrics using policy normalization.

    Returns dict with keys component_perf, component_safety, component_security,
    component_coordination (each in [0, 1]). Also includes raw component scores
    for any sub-metrics that were present.
    """
    missing_behavior = policy.get("missing_metric_behavior", "omit")
    components_cfg = policy.get("components") or {}
    policy.get("weights") or {}
    out: dict[str, float] = {}

    for comp_name in ("perf", "safety", "security", "coordination"):
        comp_cfg = components_cfg.get(comp_name)
        if not comp_cfg or not isinstance(comp_cfg, dict):
            out[f"component_{comp_name}"] = 0.5
            continue
        sub_metrics = comp_cfg.get("sub_metrics") or {}
        scores: list[float] = []
        for _sub_name, sub_cfg in sub_metrics.items():
            if not isinstance(sub_cfg, dict):
                continue
            cell_key = sub_cfg.get("cell_key")
            if not cell_key:
                continue
            value = cell_metrics.get(cell_key)
            if value is None:
                if missing_behavior == "zero":
                    scores.append(0.0)
                elif missing_behavior == "one":
                    scores.append(1.0)
                # omit: do not append
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            direction = sub_cfg.get("direction", "higher_better")
            r = sub_cfg.get("range")
            if not r or len(r) < 2:
                continue
            range_min, range_max = float(r[0]), float(r[1])
            saturation = sub_cfg.get("saturation")
            if isinstance(saturation, list) and len(saturation) >= 2:
                sat = [float(saturation[0]), float(saturation[1])]
            else:
                sat = None
            s = _normalize(v, range_min, range_max, direction, sat)
            scores.append(s)
        if scores:
            out[f"component_{comp_name}"] = round(sum(scores) / len(scores), 4)
        else:
            out[f"component_{comp_name}"] = 0.5
    return out


def compute_resilience_score(
    components: dict[str, float],
    weights: dict[str, float],
) -> float:
    """
    Weighted sum of component scores. Component keys: component_perf, component_safety,
    component_security, component_coordination. Weights keys: perf, safety, security,
    coordination. Result clamped to [0, 1].
    """
    w_perf = float(weights.get("perf", 0.25))
    w_safety = float(weights.get("safety", 0.25))
    w_security = float(weights.get("security", 0.25))
    w_coord = float(weights.get("coordination", 0.25))
    score = (
        w_perf * components.get("component_perf", 0.5)
        + w_safety * components.get("component_safety", 0.5)
        + w_security * components.get("component_security", 0.5)
        + w_coord * components.get("component_coordination", 0.5)
    )
    return round(max(0.0, min(1.0, score)), 4)


def enrich_pack_rows_with_resilience(
    rows: list[dict[str, Any]],
    policy: dict[str, Any] | None = None,
    policy_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Compute robustness.resilience_score for each row from policy-defined components
    (perf, safety, security, coordination). Used when pack_summary.csv does not
    contain resilience_score (e.g. deterministic pack run). Mutates rows in place
    and returns the same list.
    """
    if policy is None:
        if policy_path is not None:
            policy = load_resilience_scoring_policy(policy_path)
        else:
            policy = load_resilience_scoring_policy()
    weights = policy.get("weights") or {}
    for r in rows:
        components = compute_components(r, policy)
        score = compute_resilience_score(components, weights)
        r["robustness.resilience_score"] = score
    return rows
