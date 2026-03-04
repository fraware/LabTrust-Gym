"""
Deterministic plotting pipeline: converts study out_dir into data tables (CSV)
and paper-ready figures (PNG + SVG). Same inputs => identical CSV tables.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

# Matplotlib optional; use Agg for non-interactive
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

# Professional style: clean sans-serif, light grid, consistent palette
_PLOT_STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "#fafafa",
    "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0,
    "axes.grid": True,
    "axes.grid.which": "both",
    "grid.alpha": 0.28,
    "grid.color": "#cccccc",
    "axes.axisbelow": True,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial", "sans-serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "text.color": "#111111",
    "axes.labelcolor": "#111111",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
}
_PLOT_PALETTE = [
    "#2e7d32",
    "#1565c0",
    "#c62828",
    "#6a1b9a",
    "#ef6c00",
    "#00838f",
    "#7b1fa2",
    "#558b2f",
]

# Dark theme: dark background, light grid and text
_PLOT_STYLE_DARK = {
    "figure.facecolor": "#1e1e1e",
    "axes.facecolor": "#2d2d2d",
    "axes.edgecolor": "#b0b0b0",
    "axes.linewidth": 1.0,
    "axes.grid": True,
    "axes.grid.which": "both",
    "grid.alpha": 0.35,
    "grid.color": "#505050",
    "axes.axisbelow": True,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial", "sans-serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "text.color": "#e8e8e8",
    "axes.labelcolor": "#e8e8e8",
    "xtick.color": "#b0b0b0",
    "ytick.color": "#b0b0b0",
}
_PLOT_PALETTE_DARK = [
    "#81c784",
    "#64b5f6",
    "#e57373",
    "#ba68c8",
    "#ffb74d",
    "#4dd0e1",
    "#ce93d8",
    "#aed581",
]


# Set by _apply_plot_style so plot functions use the active theme
_CURRENT_PALETTE: list[str] = _PLOT_PALETTE.copy()
_CURRENT_EDGE = "#333333"  # light theme default; dark theme uses lighter edge


def _apply_plot_style(theme: str = "light") -> None:
    """Apply a consistent, publication-ready style. theme: 'light' or 'dark'."""
    global _CURRENT_PALETTE, _CURRENT_EDGE
    if not _HAS_MPL:
        return
    if theme == "dark":
        plt.rcParams.update(_PLOT_STYLE_DARK)
        _CURRENT_PALETTE = _PLOT_PALETTE_DARK.copy()
        _CURRENT_EDGE = "#b0b0b0"
    else:
        plt.rcParams.update(_PLOT_STYLE)
        _CURRENT_PALETTE = _PLOT_PALETTE.copy()
        _CURRENT_EDGE = "#333333"
    try:
        plt.rcParams["axes.prop_cycle"] = plt.cycler(color=_CURRENT_PALETTE)
    except Exception:
        pass


def _load_study_results(
    out_dir: Path,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Load condition_ids, condition_labels from manifest and results/cond_*/results.json."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {out_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    condition_ids = manifest.get("condition_ids") or []
    condition_labels: list[str] = manifest.get("condition_labels") or []
    if len(condition_labels) != len(condition_ids):
        condition_labels = list(condition_ids)
    results_list: list[dict[str, Any]] = []
    for cid in condition_ids:
        res_path = out_dir / "results" / cid / "results.json"
        if not res_path.exists():
            continue
        results_list.append(json.loads(res_path.read_text(encoding="utf-8")))
    return condition_ids, condition_labels, results_list


def _aggregate_per_condition(
    condition_ids: list[str],
    results_list: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build per-condition aggregates: throughput, p95_tat, violations, trust_cost."""
    agg: dict[str, dict[str, Any]] = {}
    for cid, results in zip(condition_ids, results_list):
        episodes = results.get("episodes") or []
        if not episodes:
            agg[cid] = {
                "throughput_mean": 0.0,
                "violations_total": 0,
                "p95_tat_mean": None,
                "trust_cost_mean": 0.0,
                "critical_compliance_mean": None,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
            }
            continue
        throughputs: list[int] = []
        violations_totals: list[int] = []
        p95_list: list[float | None] = []
        trust_costs: list[int] = []
        critical_rates: list[float | None] = []
        viol_by_inv: dict[str, int] = defaultdict(int)
        blocked_by_rc: dict[str, int] = defaultdict(int)

        for ep in episodes:
            m = ep.get("metrics") or {}
            throughputs.append(m.get("throughput", 0))
            vbi = m.get("violations_by_invariant_id") or {}
            viol_sum = sum(vbi.values())
            violations_totals.append(viol_sum)
            for k, v in vbi.items():
                viol_by_inv[k] += v
            p95_list.append(m.get("p95_turnaround_s"))
            tc = (m.get("tokens_consumed") or 0) + (m.get("tokens_minted") or 0)
            trust_costs.append(tc)
            critical_rates.append(m.get("critical_communication_compliance_rate"))
            for k, v in (m.get("blocked_by_reason_code") or {}).items():
                blocked_by_rc[k] += v

        n = len(episodes)
        p95_vals = [x for x in p95_list if x is not None]
        crit_vals = [x for x in critical_rates if x is not None]
        agg[cid] = {
            "throughput_mean": sum(throughputs) / n if n else 0.0,
            "violations_total": sum(violations_totals),
            "violations_mean_per_episode": (sum(violations_totals) / n if n else 0.0),
            "p95_tat_mean": sum(p95_vals) / len(p95_vals) if p95_vals else None,
            "trust_cost_mean": sum(trust_costs) / n if n else 0.0,
            "critical_compliance_mean": (sum(crit_vals) / len(crit_vals) if crit_vals else None),
            "violations_by_invariant_id": dict(viol_by_inv),
            "blocked_by_reason_code": dict(blocked_by_rc),
        }
    return agg


def _build_global_aggregates(
    agg_per_cond: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Global: violations_by_invariant_id (sum), blocked_by_reason_code (sum), top-10 blocked."""
    violations_by_inv: dict[str, int] = defaultdict(int)
    blocked_by_rc: dict[str, int] = defaultdict(int)
    for cond in agg_per_cond.values():
        for k, v in (cond.get("violations_by_invariant_id") or {}).items():
            violations_by_inv[k] += v
        for k, v in (cond.get("blocked_by_reason_code") or {}).items():
            blocked_by_rc[k] += v
    top10_blocked = sorted(blocked_by_rc.items(), key=lambda x: -x[1])[:10]
    return {
        "violations_by_invariant_id": dict(violations_by_inv),
        "blocked_by_reason_code": dict(blocked_by_rc),
        "blocked_top10": top10_blocked,
    }


def write_data_tables(
    out_dir: Path,
    condition_ids: list[str],
    agg_per_cond: dict[str, dict[str, Any]],
    global_agg: dict[str, Any],
) -> Path:
    """Write CSV tables to out_dir/figures/data_tables/. Returns data_tables dir."""
    tables_dir = out_dir / "figures" / "data_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # throughput_vs_violations.csv: condition_id, throughput_mean, violations_total
    with (tables_dir / "throughput_vs_violations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["condition_id", "throughput_mean", "violations_total"])
        for cid in condition_ids:
            row = agg_per_cond.get(cid) or {}
            w.writerow(
                [
                    cid,
                    row.get("throughput_mean", 0),
                    row.get("violations_total", 0),
                ]
            )

    # trust_cost_vs_p95_tat.csv: condition_id, trust_cost_mean, p95_tat_mean
    with (tables_dir / "trust_cost_vs_p95_tat.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["condition_id", "trust_cost_mean", "p95_tat_mean"])
        for cid in condition_ids:
            row = agg_per_cond.get(cid) or {}
            p95 = row.get("p95_tat_mean")
            w.writerow(
                [
                    cid,
                    row.get("trust_cost_mean", 0),
                    p95 if p95 is not None else "",
                ]
            )

    # violations_by_invariant_id.csv: invariant_id, count
    with (tables_dir / "violations_by_invariant_id.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["invariant_id", "count"])
        for inv_id, count in sorted(global_agg["violations_by_invariant_id"].items()):
            w.writerow([inv_id, count])

    # blocked_by_reason_code_top10.csv: reason_code, count
    with (tables_dir / "blocked_by_reason_code_top10.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reason_code", "count"])
        for rc, count in global_agg["blocked_top10"]:
            w.writerow([rc, count])

    # critical_compliance_by_condition.csv: condition_id, critical_compliance_mean
    with (tables_dir / "critical_compliance_by_condition.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["condition_id", "critical_compliance_mean"])
        for cid in condition_ids:
            row = agg_per_cond.get(cid) or {}
            cc = row.get("critical_compliance_mean")
            w.writerow([cid, cc if cc is not None else ""])

    return tables_dir


def write_summary_table(
    out_dir: Path,
    condition_ids: list[str],
    condition_labels: list[str],
    agg_per_cond: dict[str, dict[str, Any]],
) -> Path:
    """Write summary.csv and paper_table.md for paper-ready tables. Returns TABLES dir."""
    tables_dir = out_dir / "figures" / "data_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    labels = condition_labels if len(condition_labels) == len(condition_ids) else condition_ids

    # summary.csv: condition_id, condition_label, throughput_mean, violations_total, trust_cost_mean, p95_tat_mean
    with (tables_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "condition_id",
                "condition_label",
                "throughput_mean",
                "violations_total",
                "trust_cost_mean",
                "p95_tat_mean",
            ]
        )
        for cid, label in zip(condition_ids, labels):
            row = agg_per_cond.get(cid) or {}
            p95 = row.get("p95_tat_mean")
            w.writerow(
                [
                    cid,
                    label,
                    row.get("throughput_mean", 0),
                    row.get("violations_total", 0),
                    row.get("trust_cost_mean", 0),
                    p95 if p95 is not None else "",
                ]
            )

    # paper_table.md: markdown table used in docs/paper_ready.md
    md_path = out_dir / "figures" / "data_tables" / "paper_table.md"
    lines = [
        "| condition_id | condition_label | throughput_mean | violations_total | trust_cost_mean | p95_tat_mean |",
        "|--------------|-----------------|-----------------|------------------|-----------------|--------------|",
    ]
    for cid, label in zip(condition_ids, labels):
        row = agg_per_cond.get(cid) or {}
        p95 = row.get("p95_tat_mean")
        p95_str = f"{p95:.1f}" if p95 is not None else "—"
        lines.append(
            f"| {cid} | {label} | {row.get('throughput_mean', 0):.2f} | "
            f"{row.get('violations_total', 0)} | {row.get('trust_cost_mean', 0):.2f} | {p95_str} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tables_dir


def _run_context_subtitle(n_conditions: int, n_episodes: int, task: str) -> str:
    """Build a one-line run context for plot subtitles and reports."""
    return f"{task}: {n_conditions} conditions, {n_episodes} episode(s) per condition"


def _plot_throughput_vs_violations(
    condition_ids: list[str],
    agg_per_cond: dict[str, dict[str, Any]],
    fig_dir: Path,
    condition_labels: list[str] | None = None,
    subtitle: str | None = None,
) -> None:
    xs = [agg_per_cond.get(cid, {}).get("violations_total", 0) for cid in condition_ids]
    ys = [agg_per_cond.get(cid, {}).get("throughput_mean", 0) for cid in condition_ids]
    labels = condition_labels if condition_labels and len(condition_labels) == len(condition_ids) else condition_ids
    plt.figure(figsize=(5.5, 4.2))
    plt.scatter(
        xs,
        ys,
        c=_CURRENT_PALETTE[0],
        s=72,
        alpha=0.85,
        edgecolors=_CURRENT_EDGE,
        linewidths=0.8,
        zorder=2,
    )
    for i, lab in enumerate(labels):
        plt.annotate(
            lab,
            (xs[i], ys[i]),
            fontsize=8,
            alpha=0.9,
            xytext=(4, 4),
            textcoords="offset points",
        )
    plt.xlabel("Violations (total)")
    plt.ylabel("Throughput (mean)")
    title = "Pareto: Throughput vs violations"
    if subtitle:
        title += f"\n{subtitle}"
    plt.title(title, fontsize=10)
    if all(y == 0 for y in ys) and all(x == 0 for x in xs):
        plt.figtext(
            0.5,
            0.02,
            "No variation: all points at (0,0). No releases recorded in this run.",
            ha="center",
            fontsize=7,
            style="italic",
        )
    plt.tight_layout()
    plt.savefig(fig_dir / "throughput_vs_violations.png", dpi=150)
    plt.savefig(fig_dir / "throughput_vs_violations.svg")
    plt.close()


def _plot_trust_cost_vs_p95_tat(
    condition_ids: list[str],
    agg_per_cond: dict[str, dict[str, Any]],
    fig_dir: Path,
    condition_labels: list[str] | None = None,
    subtitle: str | None = None,
) -> None:
    xs = []
    ys = []
    for cid in condition_ids:
        row = agg_per_cond.get(cid) or {}
        p95 = row.get("p95_tat_mean")
        if p95 is not None:
            xs.append(p95)
            ys.append(row.get("trust_cost_mean", 0))
        else:
            xs.append(0.0)
            ys.append(row.get("trust_cost_mean", 0))
    labels = condition_labels if condition_labels and len(condition_labels) == len(condition_ids) else condition_ids
    plt.figure(figsize=(5.5, 4.2))
    plt.scatter(
        xs,
        ys,
        c=_CURRENT_PALETTE[1],
        s=72,
        alpha=0.85,
        edgecolors=_CURRENT_EDGE,
        linewidths=0.8,
        zorder=2,
    )
    for i, lab in enumerate(labels):
        plt.annotate(
            lab,
            (xs[i], ys[i]),
            fontsize=8,
            alpha=0.9,
            xytext=(4, 4),
            textcoords="offset points",
        )
    plt.xlabel("p95 TAT (s)")
    plt.ylabel("Trust cost (tokens consumed + minted, mean)")
    title = "Pareto: Trust cost vs p95 TAT"
    if subtitle:
        title += f"\n{subtitle}"
    plt.title(title, fontsize=10)
    if all(y == 0 for y in ys):
        plt.figtext(
            0.5,
            0.02,
            "No trust cost or p95 TAT recorded (no completed runs).",
            ha="center",
            fontsize=7,
            style="italic",
        )
    plt.tight_layout()
    plt.savefig(fig_dir / "trust_cost_vs_p95_tat.png", dpi=150)
    plt.savefig(fig_dir / "trust_cost_vs_p95_tat.svg")
    plt.close()


def _plot_violations_by_invariant_id(
    global_agg: dict[str, Any],
    fig_dir: Path,
    subtitle: str | None = None,
) -> None:
    vbi = global_agg.get("violations_by_invariant_id") or {}
    inv_ids = sorted(vbi.keys())
    counts = [vbi[k] for k in inv_ids]
    if not inv_ids:
        inv_ids = ["(none)"]
        counts = [0]
    plt.figure(figsize=(8, 4.2))
    plt.bar(
        range(len(inv_ids)),
        counts,
        tick_label=inv_ids,
        color=_CURRENT_PALETTE[2],
        edgecolor=_CURRENT_EDGE,
        linewidth=0.6,
    )
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Count")
    title = "Violations by invariant_id"
    if subtitle:
        title += f"\n{subtitle}"
    plt.title(title, fontsize=10)
    if not counts or all(c == 0 for c in counts):
        plt.figtext(
            0.5,
            0.02,
            "No invariant violations recorded in this run.",
            ha="center",
            fontsize=7,
            style="italic",
        )
    plt.tight_layout()
    plt.savefig(fig_dir / "violations_by_invariant_id.png", dpi=150)
    plt.savefig(fig_dir / "violations_by_invariant_id.svg")
    plt.close()


def _plot_blocked_top10(
    global_agg: dict[str, Any],
    fig_dir: Path,
    subtitle: str | None = None,
) -> None:
    top10 = global_agg.get("blocked_top10") or []
    labels = [x[0] for x in top10]
    counts = [x[1] for x in top10]
    if not labels:
        labels = ["(none)"]
        counts = [0]
    plt.figure(figsize=(8, 4.2))
    plt.bar(
        range(len(labels)),
        counts,
        tick_label=labels,
        color=_CURRENT_PALETTE[3],
        edgecolor=_CURRENT_EDGE,
        linewidth=0.6,
    )
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Count")
    title = "Blocked by reason_code (top 10)"
    if subtitle:
        title += f"\n{subtitle}"
    plt.title(title, fontsize=10)
    if not counts or all(c == 0 for c in counts):
        plt.figtext(
            0.5,
            0.02,
            "No blocked actions recorded.",
            ha="center",
            fontsize=7,
            style="italic",
        )
    plt.tight_layout()
    plt.savefig(fig_dir / "blocked_by_reason_code_top10.png", dpi=150)
    plt.savefig(fig_dir / "blocked_by_reason_code_top10.svg")
    plt.close()


def _plot_critical_compliance_by_condition(
    condition_ids: list[str],
    agg_per_cond: dict[str, dict[str, Any]],
    fig_dir: Path,
    subtitle: str | None = None,
) -> None:
    vals = []
    for cid in condition_ids:
        cc = agg_per_cond.get(cid) or {}
        v = cc.get("critical_compliance_mean")
        vals.append(v if v is not None else 0.0)
    plt.figure(figsize=(6, 4.2))
    plt.bar(
        range(len(condition_ids)),
        vals,
        tick_label=condition_ids,
        color=_CURRENT_PALETTE[4],
        edgecolor=_CURRENT_EDGE,
        linewidth=0.6,
    )
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Critical compliance rate")
    title = "Critical compliance rate by condition"
    if subtitle:
        title += f"\n{subtitle}"
    plt.title(title, fontsize=10)
    if all(v == 0.0 for v in vals):
        plt.figtext(
            0.5,
            0.02,
            "No critical communication in this run or rate not computed.",
            ha="center",
            fontsize=7,
            style="italic",
        )
    plt.tight_layout()
    plt.savefig(fig_dir / "critical_compliance_by_condition.png", dpi=150)
    plt.savefig(fig_dir / "critical_compliance_by_condition.svg")
    plt.close()


def _plot_throughput_box_by_condition(
    condition_ids: list[str],
    results_list: list[dict[str, Any]],
    fig_dir: Path,
    condition_labels: list[str] | None = None,
    subtitle: str | None = None,
) -> None:
    """Box plot: distribution of per-episode throughput per condition."""
    data_by_cond: list[list[float]] = []
    for results in results_list:
        vals: list[float] = []
        for ep in results.get("episodes") or []:
            m = ep.get("metrics") or {}
            vals.append(float(m.get("throughput", 0)))
        data_by_cond.append(vals if vals else [0.0])
    labels = condition_labels if condition_labels and len(condition_labels) == len(condition_ids) else condition_ids
    fig, ax = plt.subplots(figsize=(max(6, len(condition_ids) * 0.8), 4.2))
    bp = ax.boxplot(
        data_by_cond,
        tick_labels=labels,
        patch_artist=True,
        notch=False,
        showmeans=True,
    )
    for patch in bp["boxes"]:
        patch.set_facecolor(_CURRENT_PALETTE[0])
        patch.set_alpha(0.7)
        patch.set_edgecolor(_CURRENT_EDGE)
    ax.set_ylabel("Throughput (per episode)")
    title = "Throughput distribution by condition"
    if subtitle:
        title += f"\n{subtitle}"
    ax.set_title(title, fontsize=10)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(fig_dir / "throughput_box_by_condition.png", dpi=150)
    plt.savefig(fig_dir / "throughput_box_by_condition.svg")
    plt.close()


def _plot_metrics_overview(
    condition_ids: list[str],
    agg_per_cond: dict[str, dict[str, Any]],
    fig_dir: Path,
    condition_labels: list[str] | None = None,
    subtitle: str | None = None,
) -> None:
    """Three horizontal bar charts: throughput mean, violations total, p95 TAT mean."""
    labels = condition_labels if condition_labels and len(condition_labels) == len(condition_ids) else condition_ids
    n = len(condition_ids)
    y_pos = list(range(n))
    thr = [agg_per_cond.get(cid, {}).get("throughput_mean", 0) for cid in condition_ids]
    viol = [agg_per_cond.get(cid, {}).get("violations_total", 0) for cid in condition_ids]
    p95_raw = [agg_per_cond.get(cid, {}).get("p95_tat_mean") for cid in condition_ids]
    p95 = [x if x is not None else 0.0 for x in p95_raw]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(12, max(4.2, n * 0.35)), sharey=True)
    ax1.barh(y_pos, thr, color=_CURRENT_PALETTE[0], edgecolor=_CURRENT_EDGE, height=0.7)
    ax1.set_xlabel("Throughput (mean)")
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(labels, fontsize=8)
    ax1.set_title("Throughput")
    ax1.invert_yaxis()

    ax2.barh(y_pos, viol, color=_CURRENT_PALETTE[2], edgecolor=_CURRENT_EDGE, height=0.7)
    ax2.set_xlabel("Violations (total)")
    ax2.set_title("Violations")
    ax2.invert_yaxis()

    ax3.barh(y_pos, p95, color=_CURRENT_PALETTE[1], edgecolor=_CURRENT_EDGE, height=0.7)
    ax3.set_xlabel("p95 TAT (s)")
    ax3.set_title("p95 turnaround")
    ax3.invert_yaxis()

    title = "Metrics overview by condition"
    if subtitle:
        title += f"\n{subtitle}"
    fig.suptitle(title, fontsize=10, y=1.02)
    plt.tight_layout()
    plt.savefig(fig_dir / "metrics_overview.png", dpi=150)
    plt.savefig(fig_dir / "metrics_overview.svg")
    plt.close()


def _load_pack_summary(out_dir: Path) -> list[dict[str, Any]] | None:
    """Load pack_summary.csv if present (coordination security pack). Returns list of row dicts or None."""
    csv_path = out_dir / "pack_summary.csv"
    if not csv_path.exists():
        return None
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(dict(r))
    return rows if rows else None


def _parse_pack_gate_md(gate_path: Path) -> dict[tuple[str, str, str], str]:
    """Parse pack_gate.md table; return (scale_id, method_id, injection_id) -> verdict."""
    out: dict[tuple[str, str, str], str] = {}
    text = gate_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("|") or line.startswith("|--"):
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 4 and parts[0] != "scale_id":
            scale_id = parts[0]
            method_id = parts[1]
            injection_id = parts[2]
            verdict = parts[3].upper()
            if verdict in ("PASS", "FAIL", "NOT_SUPPORTED", "SKIP"):
                out[(scale_id, method_id, injection_id)] = (
                    "not_supported" if verdict == "NOT_SUPPORTED" else "skip" if verdict == "SKIP" else verdict.lower()
                )
    return out


def _write_pack_gate_summary_table(
    rows: list[dict[str, Any]],
    verdict_map: dict[tuple[str, str, str], str],
    fig_dir: Path,
) -> None:
    """Write pack gate summary (method x injection verdict counts or table) to figures/data_tables/."""
    data_tables = fig_dir / "data_tables"
    data_tables.mkdir(parents=True, exist_ok=True)
    # Compact table: method_id, injection_id, verdict (one row per scale/method/injection)
    lines = [
        "# Coordination pack gate summary",
        "",
        "| method_id | injection_id | scale_id | verdict |",
        "|-----------|--------------|----------|--------|",
    ]
    for r in rows:
        scale_id = r.get("scale_id", "")
        method_id = r.get("method_id", "")
        injection_id = r.get("injection_id", "")
        verdict = verdict_map.get((scale_id, method_id, injection_id), "unknown")
        lines.append(f"| {method_id} | {injection_id} | {scale_id} | {verdict} |")
    lines.append("")
    (data_tables / "pack_gate_summary.md").write_text("\n".join(lines), encoding="utf-8")


def _plot_pack_gate_heatmap(
    rows: list[dict[str, Any]],
    verdict_map: dict[tuple[str, str, str], str],
    fig_dir: Path,
) -> None:
    """Heatmap: method_id x injection_id, color by verdict (PASS=green, FAIL=red, not_supported=gray)."""
    if not rows:
        return
    methods = sorted({r.get("method_id", "") for r in rows})
    injections = sorted({r.get("injection_id", "") for r in rows})
    if not methods or not injections:
        return
    # Aggregate verdict: FAIL > not_supported > skip > PASS (skip = optional/skipped)
    order = {"fail": 3, "not_supported": 2, "skip": 1, "pass": 0, "unknown": 1}
    agg: dict[tuple[str, str], str] = {}
    for r in rows:
        scale_id = r.get("scale_id", "")
        method_id = r.get("method_id", "")
        injection_id = r.get("injection_id", "")
        v = verdict_map.get((scale_id, method_id, injection_id), "unknown")
        key = (method_id, injection_id)
        if key not in agg or order.get(v, 0) > order.get(agg[key], 0):
            agg[key] = v
    import numpy as np

    # Color: 0=PASS, 1=SKIP/not_supported, 2=FAIL
    color_val = {"pass": 0, "skip": 1, "not_supported": 1, "fail": 2}
    data = np.zeros((len(methods), len(injections)))
    for i, m in enumerate(methods):
        for j, inj in enumerate(injections):
            v = agg.get((m, inj), "unknown")
            data[i, j] = color_val.get(v, 1)
    fig, ax = plt.subplots(figsize=(max(5, len(injections) * 0.55), max(3.5, len(methods) * 0.45)))
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=0, vmax=2)
    cbar = plt.colorbar(im, ax=ax, ticks=[0, 1, 2], shrink=0.8)
    cbar.set_label("Verdict", fontsize=10)
    cbar.ax.set_yticklabels(["PASS", "SKIP / N/A", "FAIL"])
    ax.set_xticks(range(len(injections)))
    ax.set_xticklabels(injections, rotation=45, ha="right")
    ax.set_yticks(range(len(methods)))
    ax.set_yticklabels(methods)
    ax.set_xlabel("Injection")
    ax.set_ylabel("Method")
    ax.set_title("Coordination pack gate: method x injection")
    plt.tight_layout()
    plt.savefig(fig_dir / "pack_gate_heatmap.png", dpi=150)
    plt.savefig(fig_dir / "pack_gate_heatmap.svg")
    plt.close()


def _load_coordination_summary(out_dir: Path) -> list[dict[str, Any]] | None:
    """Load summary_coord.csv if present (coordination study). Returns list of row dicts or None."""
    csv_path = out_dir / "summary" / "summary_coord.csv"
    if not csv_path.exists():
        return None
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            for k in list(r.keys()):
                v = r[k]
                if v == "" and k in (
                    "perf.p95_tat",
                    "sec.attack_success_rate",
                    "sec.detection_latency_steps",
                    "sec.containment_time_steps",
                    "robustness.resilience_score",
                ):
                    r[k] = None
                elif k in ("perf.throughput", "safety.violations_total"):
                    try:
                        r[k] = float(v) if "." in str(v) else int(v)
                    except (ValueError, TypeError):
                        pass
                elif k in (
                    "perf.p95_tat",
                    "sec.attack_success_rate",
                    "sec.detection_latency_steps",
                    "sec.containment_time_steps",
                    "robustness.resilience_score",
                ):
                    try:
                        r[k] = float(v) if v else None
                    except (ValueError, TypeError):
                        r[k] = None
            rows.append(r)
    return rows if rows else None


def _plot_resilience_vs_p95_tat(rows: list[dict[str, Any]], fig_dir: Path) -> None:
    """Scatter: resilience_score vs p95_tat (matplotlib default colors)."""
    xs: list[float] = []
    ys: list[float] = []
    labels: list[str] = []
    for r in rows:
        p95 = r.get("perf.p95_tat")
        res = r.get("robustness.resilience_score")
        if p95 is not None and res is not None:
            xs.append(float(p95))
            ys.append(float(res))
            labels.append(f"{r.get('method_id', '')}/{r.get('injection_id', '')}")
    if not xs:
        return
    plt.figure(figsize=(6, 4.2))
    plt.scatter(
        xs,
        ys,
        c=_CURRENT_PALETTE[0],
        s=64,
        alpha=0.85,
        edgecolors=_CURRENT_EDGE,
        linewidths=0.7,
        zorder=2,
    )
    for i, lab in enumerate(labels):
        plt.annotate(
            lab,
            (xs[i], ys[i]),
            fontsize=7,
            alpha=0.9,
            xytext=(3, 3),
            textcoords="offset points",
        )
    plt.xlabel("p95 TAT (s)")
    plt.ylabel("Resilience score")
    plt.title("Resilience score vs p95 turnaround time")
    plt.tight_layout()
    plt.savefig(fig_dir / "resilience_vs_p95_tat.png", dpi=150)
    plt.savefig(fig_dir / "resilience_vs_p95_tat.svg")
    plt.close()


def _plot_attack_success_rate_bar(rows: list[dict[str, Any]], fig_dir: Path) -> None:
    """Bar: attack_success_rate by method and injection (matplotlib default colors)."""
    # Build (method_id, injection_id) -> rate
    keys: list[tuple[str, str]] = []
    rates: list[float] = []
    seen = set()
    for r in rows:
        mid = r.get("method_id", "")
        iid = r.get("injection_id", "")
        key = (mid, iid)
        if key in seen:
            continue
        seen.add(key)
        rate = r.get("sec.attack_success_rate")
        if rate is not None:
            keys.append(key)
            rates.append(float(rate))
        else:
            keys.append(key)
            rates.append(0.0)
    if not keys:
        return
    x_labels = [f"{m}\n{i}" for m, i in keys]
    plt.figure(figsize=(max(8, len(keys) * 0.5), 4.2))
    plt.bar(
        range(len(rates)),
        rates,
        tick_label=x_labels,
        color=_CURRENT_PALETTE[5],
        edgecolor=_CURRENT_EDGE,
        linewidth=0.6,
    )
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Attack success rate")
    plt.title("Attack success rate by method and injection")
    plt.tight_layout()
    plt.savefig(fig_dir / "attack_success_rate_by_method_injection.png", dpi=150)
    plt.savefig(fig_dir / "attack_success_rate_by_method_injection.svg")
    plt.close()


def _write_run_report(
    out_dir: Path,
    fig_dir: Path,
    manifest: dict[str, Any],
    condition_ids: list[str],
    results_list: list[dict[str, Any]],
    agg_per_cond: dict[str, dict[str, Any]],
    global_agg: dict[str, Any],
) -> None:
    """Write figures/RUN_REPORT.md explaining the run, metrics, and how to interpret plots."""
    task = manifest.get("task", "unknown")
    episodes = int(manifest.get("episodes", 0))
    n_conditions = len(condition_ids)
    total_episodes = sum(len(r.get("episodes") or []) for r in results_list)

    throughputs = [agg_per_cond.get(cid, {}).get("throughput_mean", 0) for cid in condition_ids]
    violations_totals = [agg_per_cond.get(cid, {}).get("violations_total", 0) for cid in condition_ids]
    all_zero_throughput = all(t == 0 for t in throughputs)
    all_zero_violations = all(v == 0 for v in violations_totals)

    lines = [
        "# Run report: figures and data tables",
        "",
        "## Run context",
        f"- **Task**: {task}",
        f"- **Conditions**: {n_conditions} ({', '.join(condition_ids)})",
        f"- **Episodes per condition**: {episodes}",
        f"- **Total episodes**: {total_episodes}",
        f"- **Output directory**: `{out_dir.resolve()}`",
        "",
        "## Metric definitions",
        "- **throughput_mean**: Mean number of specimens released (RELEASE_RESULT) per episode. Higher is better.",
        "- **violations_total**: Sum of invariant violations across episodes (by invariant_id). Lower is better.",
        "- **p95_tat_mean**: Mean 95th percentile turnaround time (accept to release) in seconds. Lower is better when comparing conditions.",
        "- **trust_cost_mean**: Mean (tokens_consumed + tokens_minted) per episode. Proxy for trust/override usage.",
        "- **critical_compliance_mean**: Fraction of critical results with required notify/ack. Higher is better.",
        "- **blocked_by_reason_code**: Count of actions blocked by policy (e.g. RBAC, QC_FAIL_ACTIVE).",
        "",
        "## Figures",
        "- `throughput_vs_violations.png` / `.svg`: Pareto view; prefer high throughput, low violations.",
        "- `trust_cost_vs_p95_tat.png` / `.svg`: Trust cost vs turnaround; trade-off by condition.",
        "- `violations_by_invariant_id.png` / `.svg`: Which invariants were violated (aggregate).",
        "- `blocked_by_reason_code_top10.png` / `.svg`: Top reason codes for blocked actions.",
        "- `critical_compliance_by_condition.png` / `.svg`: Critical communication compliance per condition.",
        "- `throughput_box_by_condition.png` / `.svg`: Per-episode throughput distribution by condition.",
        "- `metrics_overview.png` / `.svg`: Dashboard: throughput, violations, p95 TAT by condition.",
        "",
        "## Data tables (figures/data_tables/)",
        "- `summary.csv`, `paper_table.md`: Per-condition aggregates (paper-ready).",
        "- `throughput_vs_violations.csv`, `trust_cost_vs_p95_tat.csv`: Underlying data for scatter plots.",
        "- `violations_by_invariant_id.csv`, `blocked_by_reason_code_top10.csv`: Underlying data for bar charts.",
        "",
        "## Data summary",
    ]
    if all_zero_throughput:
        lines.extend(
            [
                "- **Throughput**: All conditions had 0 releases. No RELEASE_RESULT was recorded in any episode.",
                "  This usually means: (1) scripted baseline did not complete any run (e.g. reagent stockout, zone violations),",
                "  or (2) episodes were too short, or (3) specimens were not accepted/queued. Check `policy_root` and",
                "  `reagent_initial_stock` in initial_state, and that specimens start as accepted for study tasks.",
                "",
            ]
        )
    else:
        lines.append(f"- **Throughput**: Min={min(throughputs):.2f}, Max={max(throughputs):.2f} (mean per condition).")
        lines.append("")
    if all_zero_violations:
        lines.append("- **Violations**: No invariant violations recorded.")
    else:
        total_v = sum(violations_totals)
        lines.append(
            f"- **Violations**: Total={total_v} across conditions; see violations_by_invariant_id for breakdown."
        )
    lines.append("")

    report_path = fig_dir / "RUN_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _write_run_summary(out_dir: Path, manifest: dict[str, Any]) -> None:
    """Write out_dir/RUN_SUMMARY.md: what was run, where results and figures live, and next steps."""
    task = manifest.get("task", "unknown")
    episodes = int(manifest.get("episodes", 0))
    condition_ids = manifest.get("condition_ids") or []
    spec_path = manifest.get("study_spec_path", "")
    git_hash = manifest.get("git_commit_hash", "")

    lines = [
        "# Run summary",
        "",
        "## What was run",
        f"- **Task**: {task}",
        f"- **Episodes per condition**: {episodes}",
        f"- **Conditions**: {len(condition_ids)}",
    ]
    if spec_path:
        lines.append(f"- **Study spec**: `{spec_path}`")
    if git_hash:
        lines.append(f"- **Git commit**: `{git_hash}`")
    lines.extend(
        [
            "",
            "## Output layout",
            "| Path | Description |",
            "|------|-------------|",
            "| `manifest.json` | Run metadata, condition_ids, seeds, git hash |",
            "| `results/<cond_id>/results.json` | Per-condition benchmark results (episodes, metrics) |",
            "| `logs/<cond_id>/episodes.jsonl` | Episode logs when logging enabled |",
            "| `figures/` | PNG/SVG plots and `figures/data_tables/` (CSV, paper_table.md) |",
            "| `figures/RUN_REPORT.md` | Metric definitions and how to interpret the figures |",
            "",
            "## Next steps",
            "1. Inspect `figures/RUN_REPORT.md` for metric definitions and data summary.",
            "2. Open `figures/data_tables/summary.csv` or `paper_table.md` for per-condition aggregates.",
            '3. If all throughputs are zero, see the "Data summary" section in `figures/RUN_REPORT.md` for troubleshooting.',
            "",
        ]
    )
    summary_path = out_dir / "RUN_SUMMARY.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def make_plots(out_dir: Path, theme: str = "light") -> Path:
    """
    Read study out_dir, write data tables (CSV), summary table (summary.csv + paper_table.md),
    and figures (PNG + SVG) to out_dir/figures/ and out_dir/figures/data_tables/.
    theme: 'light' (default) or 'dark' for figure style.
    Pareto scatter plots and summary table used in docs/paper_ready.md.
    If summary/summary_coord.csv exists (coordination study), also produce
    resilience vs p95_tat and attack_success_rate bar. If pack_summary.csv exists
    (coordination security pack), produce pack_gate_summary.md and pack_gate_heatmap.
    Same inputs => identical CSV files (determinism).
    """
    if not _HAS_MPL:
        raise ImportError("matplotlib required for make_plots; pip install matplotlib")
    _apply_plot_style(theme=theme)
    out_dir = Path(out_dir)
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    pack_rows: list[dict[str, Any]] | None = _load_pack_summary(out_dir)
    if pack_rows is not None:
        gate_path = out_dir / "pack_gate.md"
        verdict_map = _parse_pack_gate_md(gate_path) if gate_path.exists() else {}
        _write_pack_gate_summary_table(pack_rows, verdict_map, fig_dir)
        _plot_pack_gate_heatmap(pack_rows, verdict_map, fig_dir)

    manifest: dict[str, Any] = {}
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    coord_rows = _load_coordination_summary(out_dir)
    if coord_rows is not None:
        _plot_resilience_vs_p95_tat(coord_rows, fig_dir)
        _plot_attack_success_rate_bar(coord_rows, fig_dir)
        if not manifest_path.exists():
            return fig_dir

    condition_ids, condition_labels, results_list = _load_study_results(out_dir)
    if not condition_ids or not results_list:
        if coord_rows is None and pack_rows is not None:
            return fig_dir
        if coord_rows is None:
            raise ValueError(f"No condition results found in {out_dir}")
        return fig_dir
    if len(condition_labels) != len(condition_ids):
        condition_labels = list(condition_ids)

    agg_per_cond = _aggregate_per_condition(condition_ids, results_list)
    global_agg = _build_global_aggregates(agg_per_cond)

    write_data_tables(out_dir, condition_ids, agg_per_cond, global_agg)
    write_summary_table(out_dir, condition_ids, condition_labels, agg_per_cond)

    task = manifest.get("task", "unknown")
    episodes = int(manifest.get("episodes", 0))
    subtitle = _run_context_subtitle(len(condition_ids), episodes, task)

    _plot_throughput_vs_violations(
        condition_ids,
        agg_per_cond,
        fig_dir,
        condition_labels=condition_labels,
        subtitle=subtitle,
    )
    _plot_trust_cost_vs_p95_tat(
        condition_ids,
        agg_per_cond,
        fig_dir,
        condition_labels=condition_labels,
        subtitle=subtitle,
    )
    _plot_violations_by_invariant_id(global_agg, fig_dir, subtitle=subtitle)
    _plot_blocked_top10(global_agg, fig_dir, subtitle=subtitle)
    _plot_critical_compliance_by_condition(
        condition_ids,
        agg_per_cond,
        fig_dir,
        subtitle=subtitle,
    )
    _plot_throughput_box_by_condition(
        condition_ids,
        results_list,
        fig_dir,
        condition_labels=condition_labels,
        subtitle=subtitle,
    )
    _plot_metrics_overview(
        condition_ids,
        agg_per_cond,
        fig_dir,
        condition_labels=condition_labels,
        subtitle=subtitle,
    )

    if coord_rows is not None:
        _plot_resilience_vs_p95_tat(coord_rows, fig_dir)
        _plot_attack_success_rate_bar(coord_rows, fig_dir)

    _write_run_report(
        out_dir,
        fig_dir,
        manifest,
        condition_ids,
        results_list,
        agg_per_cond,
        global_agg,
    )
    _write_run_summary(out_dir, manifest)

    return fig_dir


def get_data_table_paths(out_dir: Path) -> list[Path]:
    """Return expected CSV and table paths in figures/data_tables/ (paper-ready)."""
    base = out_dir / "figures" / "data_tables"
    return [
        base / "summary.csv",
        base / "paper_table.md",
        base / "throughput_vs_violations.csv",
        base / "trust_cost_vs_p95_tat.csv",
        base / "violations_by_invariant_id.csv",
        base / "blocked_by_reason_code_top10.csv",
        base / "critical_compliance_by_condition.csv",
    ]
