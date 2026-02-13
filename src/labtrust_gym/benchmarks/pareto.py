"""
Multi-objective Pareto evaluation v0.1: nondominated sets, bootstrap CIs, canonical outputs.

Stable Pareto front: throughput vs p95 TAT vs violations vs security success rate.
Per-method confidence intervals via deterministic bootstrap (seeded resampling).
Does not modify results.v0.2; PARETO/ outputs are separate (v0.3 extension stats).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

# Canonical objectives: (key, direction). key "security_success" is derived as 1 - sec.attack_success_rate.
DEFAULT_OBJECTIVES: list[tuple[str, str]] = [
    ("perf.throughput", "max"),
    ("perf.p95_tat", "min"),
    ("safety.violations_total", "min"),
    ("security_success", "max"),
]

# Cost-aware front: same as default plus minimize cost.total_tokens (and optionally cost.estimated_cost_usd).
COST_AWARE_OBJECTIVES: list[tuple[str, str]] = [
    ("perf.throughput", "max"),
    ("perf.p95_tat", "min"),
    ("safety.violations_total", "min"),
    ("security_success", "max"),
    ("cost.total_tokens", "min"),
]


def _objective_value(row: dict[str, Any], key: str) -> float | None:
    """Resolve objective value; security_success = 1 - sec.attack_success_rate."""
    if key == "security_success":
        rate = row.get("sec.attack_success_rate")
        if rate is None:
            return 1.0
        return 1.0 - float(rate)
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pareto_dominates(
    a: dict[str, Any],
    b: dict[str, Any],
    objectives: list[tuple[str, str]],
) -> bool:
    """
    True if a dominates b: for each objective (key, direction), a is no worse;
    at least one strictly better. direction "min" => lower better, "max" => higher better.
    """
    at_least_one_better = False
    for key, direction in objectives:
        va = _objective_value(a, key)
        vb = _objective_value(b, key)
        if va is None or vb is None:
            continue
        if direction == "min":
            if va > vb:
                return False
            if va < vb:
                at_least_one_better = True
        else:
            if va < vb:
                return False
            if va > vb:
                at_least_one_better = True
    return at_least_one_better


def compute_nondominated_per_scale(
    summary_rows: list[dict[str, Any]],
    objectives: list[tuple[str, str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Compute nondominated (Pareto) set per scale_id.
    Returns dict: scale_id -> list of row dicts on the front (no other row dominates them).
    """
    objectives = objectives or DEFAULT_OBJECTIVES
    scale_ids = sorted({r.get("scale_id", "") for r in summary_rows})
    out: dict[str, list[dict[str, Any]]] = {}
    for scale_id in scale_ids:
        subset = [r for r in summary_rows if r.get("scale_id") == scale_id]
        front = []
        for r in subset:
            dominated = False
            for other in subset:
                if other is r:
                    continue
                if _pareto_dominates(other, r, objectives):
                    dominated = True
                    break
            if not dominated:
                front.append(r)
        out[scale_id] = front
    return out


def bootstrap_ci(
    values: list[float],
    seed: int,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """
    Deterministic bootstrap CI for the mean.
    Returns (ci_low, mean, ci_high). Same seed => same result.
    """
    if not values:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    mean_obs = sum(values) / n
    bootstrap_means: list[float] = []
    for _ in range(n_bootstrap):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)
    bootstrap_means.sort()
    alpha = 1.0 - confidence
    low_idx = int(alpha / 2 * n_bootstrap)
    high_idx = int((1 - alpha / 2) * n_bootstrap)
    low_idx = max(0, min(low_idx, len(bootstrap_means) - 1))
    high_idx = max(0, min(high_idx, len(bootstrap_means) - 1))
    return (
        bootstrap_means[low_idx],
        mean_obs,
        bootstrap_means[high_idx],
    )


def compute_per_method_ci(
    summary_rows: list[dict[str, Any]],
    seed: int,
    metric_keys: list[str] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """
    Per-method bootstrap CIs for selected metrics.
    Returns dict: method_id -> metric_key -> {mean, ci_low, ci_high}.
    """
    metric_keys = metric_keys or [
        "perf.throughput",
        "perf.p95_tat",
        "safety.violations_total",
        "robustness.resilience_score",
        "security_success",
    ]
    method_cells: dict[str, list[dict[str, Any]]] = {}
    for r in summary_rows:
        mid = r.get("method_id", "")
        if mid:
            method_cells.setdefault(mid, []).append(r)

    out: dict[str, dict[str, dict[str, float]]] = {}
    for method_id, rows in method_cells.items():
        out[method_id] = {}
        for key in metric_keys:
            values = []
            for row in rows:
                if key == "security_success":
                    rate = row.get("sec.attack_success_rate")
                    if rate is not None:
                        values.append(1.0 - float(rate))
                    else:
                        values.append(1.0)
                else:
                    v = row.get(key)
                    if v is not None:
                        try:
                            values.append(float(v))
                        except (TypeError, ValueError):
                            pass
            if values:
                method_seed = seed + sum(ord(c) for c in method_id) % (2**31)
                ci_low, mean, ci_high = bootstrap_ci(values, method_seed)
                out[method_id][key] = {
                    "mean": round(mean, 4),
                    "ci_low": round(ci_low, 4),
                    "ci_high": round(ci_high, 4),
                }
    return out


def build_pareto_artifact(
    summary_rows: list[dict[str, Any]],
    seed: int,
    objectives: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Build artifact for pareto.json: fronts per scale, per_method_ci, version.
    """
    objectives = objectives or DEFAULT_OBJECTIVES
    fronts = compute_nondominated_per_scale(summary_rows, objectives)
    per_method_ci = compute_per_method_ci(summary_rows, seed)

    # Serialize front rows as minimal dicts (method_id, scale_id, injection_id + objective metrics)
    def _row_summary(r: dict[str, Any]) -> dict[str, Any]:
        out_row: dict[str, Any] = {
            "method_id": r.get("method_id"),
            "scale_id": r.get("scale_id"),
            "injection_id": r.get("injection_id"),
        }
        for key, _ in objectives:
            if key == "security_success":
                out_row["security_success"] = _objective_value(r, key)
            else:
                out_row[key] = r.get(key)
        return out_row

    fronts_serializable: dict[str, list[dict[str, Any]]] = {}
    for scale_id, rows in fronts.items():
        fronts_serializable[scale_id] = [_row_summary(r) for r in rows]

    return {
        "version": "0.3",
        "pareto_version": "0.1",
        "seed": seed,
        "objectives": objectives,
        "fronts_per_scale": fronts_serializable,
        "per_method_ci": per_method_ci,
    }


def write_pareto_json(out_path: Path, data: dict[str, Any]) -> None:
    """Write pareto.json (deterministic key order)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def write_pareto_md(
    out_path: Path,
    data: dict[str, Any],
    summary_rows: list[dict[str, Any]],
    cost_data: dict[str, Any] | None = None,
) -> None:
    """
    Write pareto.md: interpretation guide, fronts per scale, per-method CIs.
    If cost_data is provided, append a "Cost-aware Pareto front" section.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    objectives = data.get("objectives") or []
    obj_rows = [f"| {key} | {dirn} |" for key, dirn in objectives]
    obj_table = (
        "| Objective | Direction |\n|------------|----------|\n"
        + ("\n".join(obj_rows) if obj_rows else "| — | — |")
    )
    lines = [
        "# Pareto evaluation (multi-objective)",
        "",
        "Nondominated solutions per scale and cost-aware front. Confidence intervals: 95% bootstrap (deterministic seed).",
        "",
        "## Objectives (quick reference)",
        "",
        obj_table,
        "",
        "---",
        "",
        "## Nondominated front per scale",
        "",
    ]
    fronts = data.get("fronts_per_scale") or {}
    for scale_id in sorted(fronts.keys()):
        lines.append(f"### {scale_id}")
        lines.append("")
        for row in fronts[scale_id]:
            method = row.get("method_id", "")
            inj = row.get("injection_id", "")
            thr = row.get("perf.throughput")
            p95 = row.get("perf.p95_tat")
            viol = row.get("safety.violations_total")
            sec = row.get("security_success")
            thr_s = f"{thr:.2f}" if thr is not None else "—"
            p95_s = f"{p95:.1f}" if p95 is not None else "—"
            sec_s = f"{sec:.2f}" if sec is not None else "—"
            lines.append(
                f"- **{method}** / {inj}: throughput={thr_s}, p95_tat={p95_s}, "
                f"violations={viol}, security_success={sec_s}"
            )
        lines.append("")

    if cost_data:
        lines.append("---")
        lines.append("")
        lines.append("## Cost-aware Pareto front")
        lines.append("")
        lines.append(
            "Objectives: same as above plus cost.total_tokens (min). "
            "Separate section so the main front is unchanged."
        )
        lines.append("")
        cost_fronts = cost_data.get("fronts_per_scale") or {}
        for scale_id in sorted(cost_fronts.keys()):
            lines.append(f"### {scale_id} (cost-aware)")
            lines.append("")
            for row in cost_fronts[scale_id]:
                method = row.get("method_id", "")
                inj = row.get("injection_id", "")
                thr = row.get("perf.throughput")
                p95 = row.get("perf.p95_tat")
                viol = row.get("safety.violations_total")
                sec = row.get("security_success")
                cost_tok = row.get("cost.total_tokens")
                thr_s = f"{thr:.2f}" if thr is not None else "—"
                p95_s = f"{p95:.1f}" if p95 is not None else "—"
                sec_s = f"{sec:.2f}" if sec is not None else "—"
                cost_s = f"{int(cost_tok)}" if cost_tok is not None else "—"
                lines.append(
                    f"- **{method}** / {inj}: throughput={thr_s}, p95_tat={p95_s}, "
                    f"violations={viol}, security_success={sec_s}, cost.total_tokens={cost_s}"
                )
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Per-method 95% bootstrap CI")
    lines.append("")
    ci = data.get("per_method_ci") or {}
    for method_id in sorted(ci.keys()):
        lines.append(f"### {method_id}")
        lines.append("")
        for metric, stats in sorted(ci[method_id].items()):
            m = stats.get("mean")
            lo = stats.get("ci_low")
            hi = stats.get("ci_high")
            if m is not None and lo is not None and hi is not None:
                lines.append(f"- {metric}: mean={m:.4f} [{lo:.4f}, {hi:.4f}]")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_frontier_svg(
    out_path: Path,
    summary_rows: list[dict[str, Any]],
    fronts_per_scale: dict[str, list[dict[str, Any]]],
    objectives: list[tuple[str, str]] | None = None,
    theme: str = "light",
) -> None:
    """
    Write canonical frontier plot: throughput vs p95_tat, frontier points highlighted.
    theme: 'light' (default) or 'dark'.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    objectives = objectives or DEFAULT_OBJECTIVES
    out_path.parent.mkdir(parents=True, exist_ok=True)

    front_set: set[tuple[str, str, str]] = set()
    for scale_id, rows in fronts_per_scale.items():
        for r in rows:
            key = (
                r.get("method_id") or "",
                r.get("scale_id") or "",
                r.get("injection_id") or "",
            )
            front_set.add(key)

    xs: list[float] = []
    ys: list[float] = []
    labels: list[str] = []
    is_front: list[bool] = []
    for r in summary_rows:
        p95 = _objective_value(r, "perf.p95_tat")
        thr = _objective_value(r, "perf.throughput")
        if p95 is None or thr is None:
            continue
        xs.append(p95)
        ys.append(thr)
        key = (r.get("method_id"), r.get("scale_id"), r.get("injection_id"))
        is_front.append(key in front_set)
        labels.append(f"{r.get('method_id', '')}/{r.get('injection_id', '')}")

    if not xs:
        return
    if theme == "dark":
        style = {
            "figure.facecolor": "#1e1e1e",
            "axes.facecolor": "#2d2d2d",
            "axes.edgecolor": "#b0b0b0",
            "axes.grid": True,
            "grid.alpha": 0.35,
            "grid.color": "#505050",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "text.color": "#e8e8e8",
            "axes.labelcolor": "#e8e8e8",
            "xtick.color": "#b0b0b0",
            "ytick.color": "#b0b0b0",
        }
        dominated_c, dominated_e = "#606060", "#808080"
        front_c, front_e = "#81c784", "#4caf50"
        legend_edge = "#505050"
    else:
        style = {
            "figure.facecolor": "white",
            "axes.facecolor": "#fafafa",
            "axes.grid": True,
            "grid.alpha": 0.28,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
        dominated_c, dominated_e = "#bdbdbd", "#757575"
        front_c, front_e = "#2e7d32", "#1b5e20"
        legend_edge = "#e0e0e0"
    plt.rcParams.update(style)
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    ax.scatter(
        [x for x, f in zip(xs, is_front) if not f],
        [y for y, f in zip(ys, is_front) if not f],
        c=dominated_c,
        s=36,
        alpha=0.8,
        edgecolors=dominated_e,
        linewidths=0.5,
        label="Dominated",
        zorder=1,
    )
    ax.scatter(
        [x for x, f in zip(xs, is_front) if f],
        [y for y, f in zip(ys, is_front) if f],
        c=front_c,
        s=80,
        marker="s",
        edgecolors=front_e,
        linewidths=1.0,
        label="Pareto front",
        zorder=2,
    )
    ax.set_xlabel("p95 TAT (s)")
    ax.set_ylabel("Throughput")
    ax.set_title("Pareto: Throughput vs p95 TAT")
    ax.legend(loc="best", frameon=True, fancybox=False, edgecolor=legend_edge)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_pareto_artifacts(
    pareto_dir: Path,
    summary_rows: list[dict[str, Any]],
    seed: int,
    spec: dict[str, Any] | None = None,
    objectives: list[tuple[str, str]] | None = None,
    theme: str = "light",
) -> None:
    """
    Write PARETO/pareto.json, PARETO/pareto.md, PARETO/frontier.svg.
    Also writes PARETO/pareto_cost.json and adds a Cost-aware Pareto front section to pareto.md.
    theme: 'light' (default) or 'dark' for frontier.svg. Deterministic given summary_rows and seed.
    """
    pareto_dir = Path(pareto_dir)
    obj = objectives or DEFAULT_OBJECTIVES
    data = build_pareto_artifact(summary_rows, seed, obj)
    write_pareto_json(pareto_dir / "pareto.json", data)
    cost_data = build_pareto_artifact(summary_rows, seed, COST_AWARE_OBJECTIVES)
    write_pareto_json(pareto_dir / "pareto_cost.json", cost_data)
    write_pareto_md(pareto_dir / "pareto.md", data, summary_rows, cost_data=cost_data)
    fronts = compute_nondominated_per_scale(summary_rows, obj)
    write_frontier_svg(
        pareto_dir / "frontier.svg",
        summary_rows,
        fronts,
        obj,
        theme=theme,
    )
