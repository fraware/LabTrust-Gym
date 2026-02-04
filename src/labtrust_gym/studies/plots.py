"""
Deterministic plotting pipeline: converts study out_dir into data tables (CSV)
and paper-ready figures (PNG + SVG). Same inputs => identical CSV tables.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Matplotlib optional; use Agg for non-interactive
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


def _load_study_results(
    out_dir: Path,
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    """Load condition_ids, condition_labels from manifest and results/cond_*/results.json."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {out_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    condition_ids = manifest.get("condition_ids") or []
    condition_labels: List[str] = manifest.get("condition_labels") or []
    if len(condition_labels) != len(condition_ids):
        condition_labels = list(condition_ids)
    results_list: List[Dict[str, Any]] = []
    for cid in condition_ids:
        res_path = out_dir / "results" / cid / "results.json"
        if not res_path.exists():
            continue
        results_list.append(json.loads(res_path.read_text(encoding="utf-8")))
    return condition_ids, condition_labels, results_list


def _aggregate_per_condition(
    condition_ids: List[str],
    results_list: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build per-condition aggregates: throughput, p95_tat, violations, trust_cost."""
    agg: Dict[str, Dict[str, Any]] = {}
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
        throughputs: List[int] = []
        violations_totals: List[int] = []
        p95_list: List[Optional[float]] = []
        trust_costs: List[int] = []
        critical_rates: List[Optional[float]] = []
        viol_by_inv: Dict[str, int] = defaultdict(int)
        blocked_by_rc: Dict[str, int] = defaultdict(int)

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
            "critical_compliance_mean": (
                sum(crit_vals) / len(crit_vals) if crit_vals else None
            ),
            "violations_by_invariant_id": dict(viol_by_inv),
            "blocked_by_reason_code": dict(blocked_by_rc),
        }
    return agg


def _build_global_aggregates(
    agg_per_cond: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Global: violations_by_invariant_id (sum), blocked_by_reason_code (sum), top-10 blocked."""
    violations_by_inv: Dict[str, int] = defaultdict(int)
    blocked_by_rc: Dict[str, int] = defaultdict(int)
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
    condition_ids: List[str],
    agg_per_cond: Dict[str, Dict[str, Any]],
    global_agg: Dict[str, Any],
) -> Path:
    """Write CSV tables to out_dir/figures/data_tables/. Returns data_tables dir."""
    tables_dir = out_dir / "figures" / "data_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # throughput_vs_violations.csv: condition_id, throughput_mean, violations_total
    with (tables_dir / "throughput_vs_violations.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
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
    with (tables_dir / "trust_cost_vs_p95_tat.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
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
    with (tables_dir / "violations_by_invariant_id.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f)
        w.writerow(["invariant_id", "count"])
        for inv_id, count in sorted(global_agg["violations_by_invariant_id"].items()):
            w.writerow([inv_id, count])

    # blocked_by_reason_code_top10.csv: reason_code, count
    with (tables_dir / "blocked_by_reason_code_top10.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f)
        w.writerow(["reason_code", "count"])
        for rc, count in global_agg["blocked_top10"]:
            w.writerow([rc, count])

    # critical_compliance_by_condition.csv: condition_id, critical_compliance_mean
    with (tables_dir / "critical_compliance_by_condition.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f)
        w.writerow(["condition_id", "critical_compliance_mean"])
        for cid in condition_ids:
            row = agg_per_cond.get(cid) or {}
            cc = row.get("critical_compliance_mean")
            w.writerow([cid, cc if cc is not None else ""])

    return tables_dir


def write_summary_table(
    out_dir: Path,
    condition_ids: List[str],
    condition_labels: List[str],
    agg_per_cond: Dict[str, Dict[str, Any]],
) -> Path:
    """Write summary.csv and paper_table.md for paper-ready tables. Returns TABLES dir."""
    tables_dir = out_dir / "figures" / "data_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    labels = (
        condition_labels
        if len(condition_labels) == len(condition_ids)
        else condition_ids
    )

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


def _plot_throughput_vs_violations(
    condition_ids: List[str],
    agg_per_cond: Dict[str, Dict[str, Any]],
    fig_dir: Path,
    condition_labels: Optional[List[str]] = None,
) -> None:
    xs = [agg_per_cond.get(cid, {}).get("violations_total", 0) for cid in condition_ids]
    ys = [agg_per_cond.get(cid, {}).get("throughput_mean", 0) for cid in condition_ids]
    labels = (
        condition_labels
        if condition_labels and len(condition_labels) == len(condition_ids)
        else condition_ids
    )
    plt.figure(figsize=(5, 4))
    plt.scatter(xs, ys)
    for i, lab in enumerate(labels):
        plt.annotate(lab, (xs[i], ys[i]), fontsize=8, alpha=0.8)
    plt.xlabel("Violations (total)")
    plt.ylabel("Throughput (mean)")
    plt.title("Pareto: Throughput vs violations")
    plt.tight_layout()
    plt.savefig(fig_dir / "throughput_vs_violations.png", dpi=150)
    plt.savefig(fig_dir / "throughput_vs_violations.svg")
    plt.close()


def _plot_trust_cost_vs_p95_tat(
    condition_ids: List[str],
    agg_per_cond: Dict[str, Dict[str, Any]],
    fig_dir: Path,
    condition_labels: Optional[List[str]] = None,
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
    labels = (
        condition_labels
        if condition_labels and len(condition_labels) == len(condition_ids)
        else condition_ids
    )
    plt.figure(figsize=(5, 4))
    plt.scatter(xs, ys)
    for i, lab in enumerate(labels):
        plt.annotate(lab, (xs[i], ys[i]), fontsize=8, alpha=0.8)
    plt.xlabel("p95 TAT (s)")
    plt.ylabel("Trust cost (tokens consumed + minted, mean)")
    plt.title("Pareto: Trust cost vs p95 TAT")
    plt.tight_layout()
    plt.savefig(fig_dir / "trust_cost_vs_p95_tat.png", dpi=150)
    plt.savefig(fig_dir / "trust_cost_vs_p95_tat.svg")
    plt.close()


def _plot_violations_by_invariant_id(
    global_agg: Dict[str, Any],
    fig_dir: Path,
) -> None:
    vbi = global_agg.get("violations_by_invariant_id") or {}
    inv_ids = sorted(vbi.keys())
    counts = [vbi[k] for k in inv_ids]
    if not inv_ids:
        inv_ids = ["(none)"]
        counts = [0]
    plt.figure(figsize=(8, 4))
    plt.bar(range(len(inv_ids)), counts, tick_label=inv_ids)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Count")
    plt.title("Violations by invariant_id")
    plt.tight_layout()
    plt.savefig(fig_dir / "violations_by_invariant_id.png", dpi=150)
    plt.savefig(fig_dir / "violations_by_invariant_id.svg")
    plt.close()


def _plot_blocked_top10(
    global_agg: Dict[str, Any],
    fig_dir: Path,
) -> None:
    top10 = global_agg.get("blocked_top10") or []
    labels = [x[0] for x in top10]
    counts = [x[1] for x in top10]
    if not labels:
        labels = ["(none)"]
        counts = [0]
    plt.figure(figsize=(8, 4))
    plt.bar(range(len(labels)), counts, tick_label=labels)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Count")
    plt.title("Blocked by reason_code (top 10)")
    plt.tight_layout()
    plt.savefig(fig_dir / "blocked_by_reason_code_top10.png", dpi=150)
    plt.savefig(fig_dir / "blocked_by_reason_code_top10.svg")
    plt.close()


def _plot_critical_compliance_by_condition(
    condition_ids: List[str],
    agg_per_cond: Dict[str, Dict[str, Any]],
    fig_dir: Path,
) -> None:
    vals = []
    for cid in condition_ids:
        cc = agg_per_cond.get(cid) or {}
        v = cc.get("critical_compliance_mean")
        vals.append(v if v is not None else 0.0)
    plt.figure(figsize=(6, 4))
    plt.bar(range(len(condition_ids)), vals, tick_label=condition_ids)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Critical compliance rate")
    plt.title("Critical compliance rate by condition")
    plt.tight_layout()
    plt.savefig(fig_dir / "critical_compliance_by_condition.png", dpi=150)
    plt.savefig(fig_dir / "critical_compliance_by_condition.svg")
    plt.close()


def _load_coordination_summary(out_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """Load summary_coord.csv if present (coordination study). Returns list of row dicts or None."""
    csv_path = out_dir / "summary" / "summary_coord.csv"
    if not csv_path.exists():
        return None
    rows: List[Dict[str, Any]] = []
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


def _plot_resilience_vs_p95_tat(rows: List[Dict[str, Any]], fig_dir: Path) -> None:
    """Scatter: resilience_score vs p95_tat (matplotlib default colors)."""
    xs: List[float] = []
    ys: List[float] = []
    labels: List[str] = []
    for r in rows:
        p95 = r.get("perf.p95_tat")
        res = r.get("robustness.resilience_score")
        if p95 is not None and res is not None:
            xs.append(float(p95))
            ys.append(float(res))
            labels.append(f"{r.get('method_id', '')}/{r.get('injection_id', '')}")
    if not xs:
        return
    plt.figure(figsize=(6, 4))
    plt.scatter(xs, ys)
    for i, lab in enumerate(labels):
        plt.annotate(lab, (xs[i], ys[i]), fontsize=7, alpha=0.8)
    plt.xlabel("p95 TAT (s)")
    plt.ylabel("Resilience score")
    plt.title("Resilience score vs p95 turnaround time")
    plt.tight_layout()
    plt.savefig(fig_dir / "resilience_vs_p95_tat.png", dpi=150)
    plt.savefig(fig_dir / "resilience_vs_p95_tat.svg")
    plt.close()


def _plot_attack_success_rate_bar(rows: List[Dict[str, Any]], fig_dir: Path) -> None:
    """Bar: attack_success_rate by method and injection (matplotlib default colors)."""
    # Build (method_id, injection_id) -> rate
    keys: List[Tuple[str, str]] = []
    rates: List[float] = []
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
    plt.figure(figsize=(max(8, len(keys) * 0.5), 4))
    plt.bar(range(len(rates)), rates, tick_label=x_labels)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Attack success rate")
    plt.title("Attack success rate by method and injection")
    plt.tight_layout()
    plt.savefig(fig_dir / "attack_success_rate_by_method_injection.png", dpi=150)
    plt.savefig(fig_dir / "attack_success_rate_by_method_injection.svg")
    plt.close()


def make_plots(out_dir: Path) -> Path:
    """
    Read study out_dir, write data tables (CSV), summary table (summary.csv + paper_table.md),
    and figures (PNG + SVG) to out_dir/figures/ and out_dir/figures/data_tables/.
    Pareto scatter plots and summary table used in docs/paper_ready.md.
    If summary/summary_coord.csv exists (coordination study), also produce
    resilience vs p95_tat and attack_success_rate bar. Same inputs => identical
    CSV files (determinism).
    """
    if not _HAS_MPL:
        raise ImportError("matplotlib required for make_plots; pip install matplotlib")
    out_dir = Path(out_dir)
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    coord_rows = _load_coordination_summary(out_dir)
    if coord_rows is not None:
        _plot_resilience_vs_p95_tat(coord_rows, fig_dir)
        _plot_attack_success_rate_bar(coord_rows, fig_dir)
        if not (out_dir / "manifest.json").exists():
            return fig_dir

    condition_ids, condition_labels, results_list = _load_study_results(out_dir)
    if not condition_ids or not results_list:
        if coord_rows is None:
            raise ValueError(f"No condition results found in {out_dir}")
        return fig_dir
    if len(condition_labels) != len(condition_ids):
        condition_labels = list(condition_ids)

    agg_per_cond = _aggregate_per_condition(condition_ids, results_list)
    global_agg = _build_global_aggregates(agg_per_cond)

    write_data_tables(out_dir, condition_ids, agg_per_cond, global_agg)
    write_summary_table(out_dir, condition_ids, condition_labels, agg_per_cond)

    _plot_throughput_vs_violations(
        condition_ids, agg_per_cond, fig_dir, condition_labels=condition_labels
    )
    _plot_trust_cost_vs_p95_tat(
        condition_ids, agg_per_cond, fig_dir, condition_labels=condition_labels
    )
    _plot_violations_by_invariant_id(global_agg, fig_dir)
    _plot_blocked_top10(global_agg, fig_dir)
    _plot_critical_compliance_by_condition(condition_ids, agg_per_cond, fig_dir)

    if coord_rows is not None:
        _plot_resilience_vs_p95_tat(coord_rows, fig_dir)
        _plot_attack_success_rate_bar(coord_rows, fig_dir)

    return fig_dir


def get_data_table_paths(out_dir: Path) -> List[Path]:
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
