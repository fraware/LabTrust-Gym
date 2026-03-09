"""
Coordination result aggregation: leaderboard and method-class comparison.

Reads summary_coord.csv from a coordination study run, aggregates per method
and per method class (centralized, ripple, evolving, auctions, kernel_schedulers,
LLM, etc.), and writes SOTA (state of the art) leaderboard and method-class
comparison tables (CSV and markdown).
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

# Keys aggregated by sum in the full leaderboard; all other numerics use mean.
FULL_TABLE_SUM_KEYS: frozenset[str] = frozenset({"cost.total_tokens", "cost.estimated_cost_usd"})

# Numeric CSV columns parsed for main and full leaderboard (excludes identifiers).
SUMMARY_ROW_NUMERIC_KEYS: tuple[str, ...] = (
    "perf.throughput",
    "perf.p95_tat",
    "perf.on_time_rate",
    "safety.violations_total",
    "safety.blocks_total",
    "safety.critical_communication_compliance_rate",
    "robustness.resilience_score",
    "sec.attack_success_rate",
    "sec.detection_latency_steps",
    "sec.containment_time_steps",
    "sec.stealth_success_rate",
    "sec.time_to_attribution_steps",
    "comm.msg_count",
    "comm.p95_latency_ms",
    "comm.drop_rate",
    "coordination.stale_action_rate",
    "proposal_valid_rate",
    "blocked_rate",
    "repair_rate",
    "tokens_per_step",
    "p95_llm_latency_ms",
    "cost.total_tokens",
    "cost.estimated_cost_usd",
    "llm.error_rate",
    "llm.invalid_output_rate",
)

# Display classes for method-class comparison (centralized vs ripple vs evolving vs auctions vs kernel).
COMPARISON_CLASS_BY_METHOD: dict[str, str] = {
    "kernel_centralized_edf": "kernel_schedulers",
    "kernel_whca": "kernel_schedulers",
    "kernel_scheduler_or": "kernel_schedulers",
    "kernel_scheduler_or_whca": "kernel_schedulers",
    "centralized_planner": "centralized",
    "hierarchical_hub_rr": "centralized",
    "hierarchical_hub_local": "centralized",
    "ripple_effect": "ripple",
    "group_evolving_experience_sharing": "evolving",
    "group_evolving_study": "evolving",
    "market_auction": "auctions",
    "llm_auction_bidder": "auctions",
    "llm_auction_bidder_shielded": "auctions",
    "llm_auction_bidder_with_safe_fallback": "auctions",
    "gossip_consensus": "decentralized",
    "swarm_reactive": "swarm",
    "llm_central_planner": "llm",
    "llm_hierarchical_allocator": "llm",
    "llm_gossip_summarizer": "llm",
    "llm_repair_over_kernel_whca": "llm",
    "llm_local_decider_signed_bus": "llm",
    "llm_detector_throttle_advisor": "llm",
    "llm_central_planner_shielded": "llm",
    "llm_hierarchical_allocator_shielded": "llm",
    "llm_central_planner_with_safe_fallback": "llm",
    "llm_hierarchical_allocator_with_safe_fallback": "llm",
    "marl_ppo": "learning",
    "llm_constrained": "llm",
}


def _comparison_class(method_id: str, registry: dict[str, dict[str, Any]] | None) -> str:
    """Map method_id to comparison class for method-class table."""
    if method_id in COMPARISON_CLASS_BY_METHOD:
        return COMPARISON_CLASS_BY_METHOD[method_id]
    if registry and method_id in registry:
        cls = (registry[method_id] or {}).get("coordination_class") or ""
        if cls == "centralized":
            return "kernel_schedulers" if method_id.startswith("kernel_") else "centralized"
        if cls == "hierarchical":
            return "centralized"
        if cls == "market":
            return "auctions"
        if cls == "decentralized":
            if "ripple" in method_id:
                return "ripple"
            if "group_evolving" in method_id or "evolving" in method_id:
                return "evolving"
            return "decentralized"
        if cls:
            return cls
    if method_id.startswith("kernel_"):
        return "kernel_schedulers"
    if method_id.startswith("hierarchical_"):
        return "centralized"
    if "auction" in method_id:
        return "auctions"
    if "ripple" in method_id:
        return "ripple"
    if "group_evolving" in method_id or "evolving" in method_id:
        return "evolving"
    return "other"


def _find_summary_csv(in_dir: Path) -> Path | None:
    """Return path to summary_coord.csv or pack_summary.csv under in_dir, or None."""
    for sub in ("summary/summary_coord.csv", "summary_coord.csv", "pack_summary.csv"):
        p = in_dir / sub
        if p.is_file():
            return p
    return None


def _parse_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def load_summary_rows(csv_path: Path) -> list[dict[str, Any]]:
    """Load summary_coord.csv or pack_summary.csv; parse numeric fields for main and full tables."""
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            row = dict(r)
            for k in SUMMARY_ROW_NUMERIC_KEYS:
                if k not in row:
                    continue
                val = _parse_float(row.get(k))
                if val is not None and k == "safety.violations_total":
                    row[k] = int(val)
                else:
                    row[k] = val
            rows.append(row)
    return rows


def _stdev_or_none(vals: list[float]) -> float | None:
    """Sample std dev when n>=2, else None."""
    if len(vals) < 2:
        return None
    try:
        return statistics.stdev(vals)
    except statistics.StatisticsError:
        return None


def build_sota_leaderboard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-method aggregates: throughput, violations, blocks, resilience, p95_tat, on_time_rate, critical_compliance, attack_success_rate, stealth_success_rate; optional std for throughput and resilience."""
    by_method: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        mid = (r.get("method_id") or "").strip()
        if not mid:
            continue
        by_method.setdefault(mid, []).append(r)

    out: list[dict[str, Any]] = []
    for method_id in sorted(by_method.keys()):
        group = by_method[method_id]
        tp = [_parse_float(r.get("perf.throughput")) for r in group]
        viol = [_parse_float(r.get("safety.violations_total")) for r in group]
        blocks = [_parse_float(r.get("safety.blocks_total")) for r in group]
        res = [_parse_float(r.get("robustness.resilience_score")) for r in group]
        p95 = [_parse_float(r.get("perf.p95_tat")) for r in group]
        on_time = [_parse_float(r.get("perf.on_time_rate")) for r in group]
        crit_comp = [_parse_float(r.get("safety.critical_communication_compliance_rate")) for r in group]
        attack_succ = [_parse_float(r.get("sec.attack_success_rate")) for r in group]
        stealth = [_parse_float(r.get("sec.stealth_success_rate")) for r in group]
        tp_vals = [x for x in tp if x is not None]
        viol_vals = [x for x in viol if x is not None]
        blocks_vals = [x for x in blocks if x is not None]
        res_vals = [x for x in res if x is not None]
        p95_vals = [x for x in p95 if x is not None]
        on_time_vals = [x for x in on_time if x is not None]
        crit_comp_vals = [x for x in crit_comp if x is not None]
        attack_succ_vals = [x for x in attack_succ if x is not None]
        stealth_vals = [x for x in stealth if x is not None]
        out.append(
            {
                "method_id": method_id,
                "throughput_mean": sum(tp_vals) / len(tp_vals) if tp_vals else None,
                "throughput_std": _stdev_or_none(tp_vals),
                "violations_mean": (sum(viol_vals) / len(viol_vals) if viol_vals else None),
                "blocks_mean": (sum(blocks_vals) / len(blocks_vals) if blocks_vals else None),
                "resilience_score_mean": (sum(res_vals) / len(res_vals) if res_vals else None),
                "resilience_score_std": _stdev_or_none(res_vals),
                "p95_tat_mean": sum(p95_vals) / len(p95_vals) if p95_vals else None,
                "on_time_rate_mean": sum(on_time_vals) / len(on_time_vals) if on_time_vals else None,
                "critical_compliance_mean": sum(crit_comp_vals) / len(crit_comp_vals) if crit_comp_vals else None,
                "attack_success_rate_mean": (
                    sum(attack_succ_vals) / len(attack_succ_vals) if attack_succ_vals else None
                ),
                "stealth_success_rate_mean": (sum(stealth_vals) / len(stealth_vals) if stealth_vals else None),
                "n_cells": len(group),
            }
        )
    return out


def build_sota_leaderboard_by_phase(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-method and per-application_phase aggregates (when application_phase is present)."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        mid = (r.get("method_id") or "").strip()
        phase = (r.get("application_phase") or "").strip() or "full"
        if not mid:
            continue
        by_key.setdefault((mid, phase), []).append(r)

    out: list[dict[str, Any]] = []
    for method_id, application_phase in sorted(by_key.keys()):
        group = by_key[(method_id, application_phase)]
        tp = [_parse_float(r.get("perf.throughput")) for r in group]
        viol = [_parse_float(r.get("safety.violations_total")) for r in group]
        blocks = [_parse_float(r.get("safety.blocks_total")) for r in group]
        res = [_parse_float(r.get("robustness.resilience_score")) for r in group]
        p95 = [_parse_float(r.get("perf.p95_tat")) for r in group]
        on_time = [_parse_float(r.get("perf.on_time_rate")) for r in group]
        crit_comp = [_parse_float(r.get("safety.critical_communication_compliance_rate")) for r in group]
        attack_succ = [_parse_float(r.get("sec.attack_success_rate")) for r in group]
        stealth = [_parse_float(r.get("sec.stealth_success_rate")) for r in group]
        tp_vals = [x for x in tp if x is not None]
        viol_vals = [x for x in viol if x is not None]
        blocks_vals = [x for x in blocks if x is not None]
        res_vals = [x for x in res if x is not None]
        p95_vals = [x for x in p95 if x is not None]
        on_time_vals = [x for x in on_time if x is not None]
        crit_comp_vals = [x for x in crit_comp if x is not None]
        attack_succ_vals = [x for x in attack_succ if x is not None]
        stealth_vals = [x for x in stealth if x is not None]
        out.append(
            {
                "method_id": method_id,
                "application_phase": application_phase,
                "throughput_mean": sum(tp_vals) / len(tp_vals) if tp_vals else None,
                "throughput_std": _stdev_or_none(tp_vals),
                "violations_mean": (sum(viol_vals) / len(viol_vals) if viol_vals else None),
                "blocks_mean": (sum(blocks_vals) / len(blocks_vals) if blocks_vals else None),
                "resilience_score_mean": (sum(res_vals) / len(res_vals) if res_vals else None),
                "resilience_score_std": _stdev_or_none(res_vals),
                "p95_tat_mean": sum(p95_vals) / len(p95_vals) if p95_vals else None,
                "on_time_rate_mean": sum(on_time_vals) / len(on_time_vals) if on_time_vals else None,
                "critical_compliance_mean": sum(crit_comp_vals) / len(crit_comp_vals) if crit_comp_vals else None,
                "attack_success_rate_mean": (
                    sum(attack_succ_vals) / len(attack_succ_vals) if attack_succ_vals else None
                ),
                "stealth_success_rate_mean": (sum(stealth_vals) / len(stealth_vals) if stealth_vals else None),
                "n_cells": len(group),
            }
        )
    return out


def _full_table_agg_key(csv_key: str, suffix: str) -> str:
    """Map CSV column to full-table output key: e.g. sec.detection_latency_steps -> detection_latency_steps_mean."""
    if "." in csv_key:
        return csv_key.split(".", 1)[1] + "_" + suffix
    return csv_key + "_" + suffix


def build_sota_leaderboard_full(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-method aggregates for every numeric column: mean for rates/latency, sum for cost.total_tokens and cost.estimated_cost_usd."""
    by_method: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        mid = (r.get("method_id") or "").strip()
        if not mid:
            continue
        by_method.setdefault(mid, []).append(r)

    out: list[dict[str, Any]] = []
    for method_id in sorted(by_method.keys()):
        group = by_method[method_id]
        row_out: dict[str, Any] = {"method_id": method_id}
        for csv_key in SUMMARY_ROW_NUMERIC_KEYS:
            vals = []
            for r in group:
                v = r.get(csv_key)
                if v is None or (isinstance(v, str) and v.strip() == ""):
                    continue
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
            if not vals:
                continue
            if csv_key in FULL_TABLE_SUM_KEYS:
                agg_val = sum(vals)
                out_key = _full_table_agg_key(csv_key, "sum")
            else:
                agg_val = sum(vals) / len(vals)
                out_key = _full_table_agg_key(csv_key, "mean")
            row_out[out_key] = agg_val
        out.append(row_out)
    return out


def build_method_class_comparison(
    rows: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Aggregate by comparison class: centralized, ripple, evolving, auctions, kernel_schedulers, etc."""
    by_class: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        mid = (r.get("method_id") or "").strip()
        if not mid:
            continue
        cls = _comparison_class(mid, registry)
        by_class.setdefault(cls, []).append(r)

    out: list[dict[str, Any]] = []
    for class_id in sorted(by_class.keys()):
        group = by_class[class_id]
        tp = [_parse_float(r.get("perf.throughput")) for r in group]
        viol = [r.get("safety.violations_total") for r in group]
        blocks = [_parse_float(r.get("safety.blocks_total")) for r in group]
        res = [_parse_float(r.get("robustness.resilience_score")) for r in group]
        attack_succ = [_parse_float(r.get("sec.attack_success_rate")) for r in group]
        stealth = [_parse_float(r.get("sec.stealth_success_rate")) for r in group]
        tp_vals = [x for x in tp if x is not None]
        viol_vals = [x for x in viol if x is not None]
        blocks_vals = [x for x in blocks if x is not None]
        res_vals = [x for x in res if x is not None]
        attack_vals = [x for x in attack_succ if x is not None]
        stealth_vals = [x for x in stealth if x is not None]
        out.append(
            {
                "method_class": class_id,
                "throughput_mean": (sum(tp_vals) / len(tp_vals) if tp_vals else None),
                "violations_mean": (sum(viol_vals) / len(viol_vals) if viol_vals else None),
                "blocks_mean": (sum(blocks_vals) / len(blocks_vals) if blocks_vals else None),
                "resilience_score_mean": (sum(res_vals) / len(res_vals) if res_vals else None),
                "attack_success_rate_mean": (sum(attack_vals) / len(attack_vals) if attack_vals else None),
                "stealth_success_rate_mean": (sum(stealth_vals) / len(stealth_vals) if stealth_vals else None),
                "n_cells": len(group),
            }
        )
    return out


def write_leaderboard_by_phase_csv(out_path: Path, leaderboard: list[dict[str, Any]]) -> None:
    """Write sota_leaderboard_by_phase.csv."""
    columns = [
        "method_id",
        "application_phase",
        "throughput_mean",
        "throughput_std",
        "violations_mean",
        "blocks_mean",
        "resilience_score_mean",
        "resilience_score_std",
        "p95_tat_mean",
        "on_time_rate_mean",
        "critical_compliance_mean",
        "attack_success_rate_mean",
        "stealth_success_rate_mean",
        "n_cells",
    ]
    float_cols = [c for c in columns if c not in ("method_id", "application_phase", "n_cells")]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in leaderboard:
            row = {k: r.get(k) for k in columns}
            for k in float_cols:
                if row.get(k) is None:
                    row[k] = ""
                elif isinstance(row[k], float):
                    row[k] = round(row[k], 4)
            w.writerow(row)


def write_leaderboard_by_phase_md(out_path: Path, leaderboard: list[dict[str, Any]]) -> None:
    """Write sota_leaderboard_by_phase.md (markdown table)."""
    lines = [
        "# SOTA leaderboard by method and phase (coordination)",
        "",
        "Per-method and per-application_phase means.",
        "",
        "| method_id | application_phase | throughput_mean | throughput_std | violations_mean | blocks_mean | resilience_score_mean | resilience_score_std | p95_tat_mean | on_time_rate_mean | critical_compliance_mean | attack_success_rate_mean | stealth_success_rate_mean | n_cells |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in leaderboard:
        tp = r.get("throughput_mean")
        tp_std = r.get("throughput_std")
        viol = r.get("violations_mean")
        blocks = r.get("blocks_mean")
        res = r.get("resilience_score_mean")
        res_std = r.get("resilience_score_std")
        p95 = r.get("p95_tat_mean")
        on_time = r.get("on_time_rate_mean")
        crit = r.get("critical_compliance_mean")
        attack = r.get("attack_success_rate_mean")
        stealth = r.get("stealth_success_rate_mean")
        n = r.get("n_cells", 0)
        cells = [
            r.get("method_id", ""),
            r.get("application_phase", ""),
            f"{tp:.4f}" if tp is not None else "—",
            f"{tp_std:.4f}" if tp_std is not None else "—",
            f"{viol:.2f}" if viol is not None else "—",
            f"{blocks:.2f}" if blocks is not None else "—",
            f"{res:.4f}" if res is not None else "—",
            f"{res_std:.4f}" if res_std is not None else "—",
            f"{p95:.1f}" if p95 is not None else "—",
            f"{on_time:.4f}" if on_time is not None else "—",
            f"{crit:.4f}" if crit is not None else "—",
            f"{attack:.4f}" if attack is not None else "—",
            f"{stealth:.4f}" if stealth is not None else "—",
            str(n),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_leaderboard_csv(out_path: Path, leaderboard: list[dict[str, Any]]) -> None:
    """Write sota_leaderboard.csv (includes hospital-lab metrics, blocks, attack_success, std)."""
    columns = [
        "method_id",
        "throughput_mean",
        "throughput_std",
        "violations_mean",
        "blocks_mean",
        "resilience_score_mean",
        "resilience_score_std",
        "p95_tat_mean",
        "on_time_rate_mean",
        "critical_compliance_mean",
        "attack_success_rate_mean",
        "stealth_success_rate_mean",
        "n_cells",
    ]
    float_cols = [
        "throughput_mean",
        "throughput_std",
        "violations_mean",
        "blocks_mean",
        "resilience_score_mean",
        "resilience_score_std",
        "p95_tat_mean",
        "on_time_rate_mean",
        "critical_compliance_mean",
        "attack_success_rate_mean",
        "stealth_success_rate_mean",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in leaderboard:
            row = {k: r.get(k) for k in columns}
            for k in float_cols:
                if row.get(k) is None:
                    row[k] = ""
                elif isinstance(row[k], float):
                    row[k] = round(row[k], 4)
            w.writerow(row)


def write_leaderboard_md(
    out_path: Path,
    leaderboard: list[dict[str, Any]],
    *,
    source_note: str | None = None,
    run_metadata: dict[str, Any] | None = None,
) -> None:
    """Write sota_leaderboard.md (markdown table). Optionally prepend run metadata when provided."""
    lines = [
        "# SOTA leaderboard (coordination)",
        "",
        "Per-method means over all cells (scale x injection).",
        "",
    ]
    if run_metadata:
        seed = run_metadata.get("seed_base")
        sha = run_metadata.get("git_sha")
        meta_parts = [f"seed_base={seed}" if seed is not None else "", f"git_sha={sha}" if sha else ""]
        meta_str = ", ".join(p for p in meta_parts if p)
        if meta_str:
            lines.extend([f"Run metadata: {meta_str} (when available).", ""])
    if source_note:
        lines.extend([source_note, ""])
    lines.extend(
        [
            "| method_id | throughput_mean | throughput_std | violations_mean | blocks_mean | resilience_score_mean | resilience_score_std | p95_tat_mean | on_time_rate_mean | critical_compliance_mean | attack_success_rate_mean | stealth_success_rate_mean | n_cells |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for r in leaderboard:
        tp = r.get("throughput_mean")
        tp_std = r.get("throughput_std")
        viol = r.get("violations_mean")
        blocks = r.get("blocks_mean")
        res = r.get("resilience_score_mean")
        res_std = r.get("resilience_score_std")
        p95 = r.get("p95_tat_mean")
        on_time = r.get("on_time_rate_mean")
        crit = r.get("critical_compliance_mean")
        attack = r.get("attack_success_rate_mean")
        stealth = r.get("stealth_success_rate_mean")
        n = r.get("n_cells", 0)
        cells = [
            r.get("method_id", ""),
            f"{tp:.4f}" if tp is not None else "—",
            f"{tp_std:.4f}" if tp_std is not None else "—",
            f"{viol:.2f}" if viol is not None else "—",
            f"{blocks:.2f}" if blocks is not None else "—",
            f"{res:.4f}" if res is not None else "—",
            f"{res_std:.4f}" if res_std is not None else "—",
            f"{p95:.1f}" if p95 is not None else "—",
            f"{on_time:.4f}" if on_time is not None else "—",
            f"{crit:.4f}" if crit is not None else "—",
            f"{attack:.4f}" if attack is not None else "—",
            f"{stealth:.4f}" if stealth is not None else "—",
            str(n),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "Key hospital-lab metrics: throughput (releases/episode), p95_tat (s), on_time_rate (SLA), critical_compliance (notify/ack), violations, blocks, resilience, attack_success_rate. See docs/benchmarks/hospital_lab_metrics.md in the repository."
    )
    all_zero_throughput = all((r.get("throughput_mean") or 0) == 0 for r in leaderboard)
    if all_zero_throughput and leaderboard:
        lines.extend(
            [
                "",
                "**Note (throughput_mean = 0):** Throughput is the mean number of "
                "specimen releases (RELEASE_RESULT) per episode; higher is better. "
                "When all methods show 0, no coordination cell produced any releases. "
                "Common causes: (1) coord_risk pack cells use 1 episode per cell and "
                "coordination methods may not yet assign work that completes the "
                "accept -> process -> release pipeline in that horizon; (2) kernel "
                "allocators can report num_assignments = 0 (no alloc_emits); (3) LLM "
                "methods may error or return no valid release actions. For throughput "
                "comparison, run the throughput_sla task with scripted or kernel "
                "baselines; see coordination_benchmark_card.md.",
            ]
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_leaderboard_full_csv(out_path: Path, leaderboard_full: list[dict[str, Any]]) -> None:
    """Write sota_leaderboard_full.csv with all aggregated numeric columns."""
    if not leaderboard_full:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("method_id\n", encoding="utf-8")
        return
    all_keys = set()
    for r in leaderboard_full:
        all_keys.update(k for k in r if k != "method_id")
    columns = ["method_id"] + sorted(all_keys)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in leaderboard_full:
            row = {k: r.get(k) for k in columns}
            for k in columns:
                if k == "method_id":
                    continue
                if row.get(k) is None or row.get(k) == "":
                    row[k] = ""
                elif isinstance(row[k], float):
                    row[k] = round(row[k], 4)
            w.writerow(row)


def write_leaderboard_full_md(out_path: Path, leaderboard_full: list[dict[str, Any]]) -> None:
    """Write sota_leaderboard_full.md (full metrics table). Columns depend on data source (pack_summary vs summary_coord)."""
    if not leaderboard_full:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("# SOTA leaderboard (full metrics)\n\nNo data.\n", encoding="utf-8")
        return
    all_keys = set()
    for r in leaderboard_full:
        all_keys.update(k for k in r if k != "method_id")
    columns = ["method_id"] + sorted(all_keys)
    lines = [
        "# SOTA leaderboard (full metrics)",
        "",
        "Per-method aggregates over all cells; columns depend on data source (pack_summary vs summary_coord).",
        "When source is summary_coord.csv, comm/LLM/cost columns may be present.",
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for r in leaderboard_full:
        cells = []
        for k in columns:
            v = r.get(k)
            if v is None or v == "":
                cells.append("—")
            elif isinstance(v, float):
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_method_class_csv(out_path: Path, comparison: list[dict[str, Any]]) -> None:
    """Write method_class_comparison.csv (includes blocks_mean, attack_success_rate_mean)."""
    columns = [
        "method_class",
        "throughput_mean",
        "violations_mean",
        "blocks_mean",
        "resilience_score_mean",
        "attack_success_rate_mean",
        "stealth_success_rate_mean",
        "n_cells",
    ]
    float_cols = [c for c in columns if c not in ("method_class", "n_cells")]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in comparison:
            row = {k: r.get(k) for k in columns}
            for k in float_cols:
                if row.get(k) is None:
                    row[k] = ""
                elif isinstance(row[k], float):
                    row[k] = round(row[k], 4)
            w.writerow(row)


def write_method_class_md(
    out_path: Path,
    comparison: list[dict[str, Any]],
    *,
    source_note: str | None = None,
) -> None:
    """Write method_class_comparison.md (markdown table; includes blocks_mean, attack_success_rate_mean)."""
    lines = [
        "# Method class comparison (coordination)",
        "",
        "Centralized vs ripple vs evolving vs auctions vs kernel_schedulers (and other classes).",
        "",
    ]
    if source_note:
        lines.extend([source_note, ""])
    lines.extend(
        [
            "| method_class | throughput_mean | violations_mean | blocks_mean | resilience_score_mean | attack_success_rate_mean | stealth_success_rate_mean | n_cells |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for r in comparison:
        tp = r.get("throughput_mean")
        viol = r.get("violations_mean")
        blocks = r.get("blocks_mean")
        res = r.get("resilience_score_mean")
        attack = r.get("attack_success_rate_mean")
        stealth = r.get("stealth_success_rate_mean")
        n = r.get("n_cells", 0)
        cells = [
            r.get("method_class", ""),
            f"{tp:.4f}" if tp is not None else "—",
            f"{viol:.2f}" if viol is not None else "—",
            f"{blocks:.2f}" if blocks is not None else "—",
            f"{res:.4f}" if res is not None else "—",
            f"{attack:.4f}" if attack is not None else "—",
            f"{stealth:.4f}" if stealth is not None else "—",
            str(n),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _write_summary_readme(
    summary_out: Path,
    has_phase: bool,
    repo_root: Path | None = None,
) -> None:
    """Write summary/README.md describing leaderboard and method-class files and metric reference."""
    lines = [
        "# Coordination summary",
        "",
        "This directory contains aggregated coordination results.",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| sota_leaderboard.csv, .md | Key SOTA metrics per method (throughput, violations, blocks, resilience, p95 TAT, etc.). |",
        "| sota_leaderboard_full.csv, .md | All aggregated numerics per method. |",
        "| method_class_comparison.csv, .md | Same metrics grouped by method class. |",
    ]
    if has_phase:
        lines.append(
            "| sota_leaderboard_by_phase.csv, .md | Per-method and per-application_phase means. |"
        )
    metrics_link = "../../../docs/contracts/metrics_contract.md"
    link_note = ""
    if repo_root is not None:
        try:
            rel = summary_out.resolve().relative_to(repo_root.resolve())
            up = "/".join(".." for _ in rel.parts)
            metrics_link = f"{up}/docs/contracts/metrics_contract.md" if up else "docs/contracts/metrics_contract.md"
        except ValueError:
            link_note = " Links assume the repository root is three levels above this directory."
    else:
        link_note = " Links assume the repository root is three levels above this directory."
    lines.extend(
        [
            "",
            f"Metrics: see [Metrics contract]({metrics_link}) and the coordination benchmark card for sec.* and robustness.*.{link_note}",
            "",
        ]
    )
    (summary_out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def run_summarize(
    in_dir: Path,
    out_dir: Path,
    repo_root: Path | None = None,
) -> None:
    """
    Load summary_coord.csv from in_dir, build leaderboard and method-class comparison, write to out_dir.

    Writes:
      - summary/sota_leaderboard.csv, summary/sota_leaderboard.md
      - summary/method_class_comparison.csv, summary/method_class_comparison.md
    """
    csv_path = _find_summary_csv(in_dir)
    if not csv_path:
        raise FileNotFoundError(
            f"No summary CSV under {in_dir}. Looked for summary/summary_coord.csv, summary_coord.csv, pack_summary.csv."
        )

    rows = load_summary_rows(csv_path)
    if not rows:
        raise ValueError(f"Empty or missing data in {csv_path}")

    is_pack_summary = csv_path.name == "pack_summary.csv"
    has_phase = any((r.get("application_phase") or "").strip() for r in rows)
    source_note: str | None = None
    if is_pack_summary and has_phase:
        source_note = "Source: pack_summary.csv. This run includes an application_phase dimension."
    elif is_pack_summary:
        source_note = "Source: pack_summary.csv."

    registry: dict[str, dict[str, Any]] | None = None
    if repo_root is not None:
        reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
        if reg_path.is_file():
            try:
                from labtrust_gym.policy.coordination import load_coordination_methods

                registry = load_coordination_methods(reg_path)
            except Exception:
                pass

    leaderboard = build_sota_leaderboard(rows)
    leaderboard_full = build_sota_leaderboard_full(rows)
    comparison = build_method_class_comparison(rows, registry)

    run_metadata: dict[str, Any] | None = None
    for manifest_dir in (in_dir, in_dir.parent):
        manifest_path = manifest_dir / "pack_manifest.json"
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                run_metadata = {"seed_base": data.get("seed_base"), "git_sha": data.get("git_sha")}
            except Exception:
                pass
            break

    summary_out = out_dir / "summary"
    summary_out.mkdir(parents=True, exist_ok=True)
    _write_summary_readme(summary_out, has_phase, repo_root=repo_root)
    write_leaderboard_csv(summary_out / "sota_leaderboard.csv", leaderboard)
    write_leaderboard_md(
        summary_out / "sota_leaderboard.md",
        leaderboard,
        source_note=source_note,
        run_metadata=run_metadata,
    )
    write_leaderboard_full_csv(summary_out / "sota_leaderboard_full.csv", leaderboard_full)
    write_leaderboard_full_md(summary_out / "sota_leaderboard_full.md", leaderboard_full)
    write_method_class_csv(summary_out / "method_class_comparison.csv", comparison)
    write_method_class_md(summary_out / "method_class_comparison.md", comparison, source_note=source_note)
    if has_phase:
        leaderboard_by_phase = build_sota_leaderboard_by_phase(rows)
        write_leaderboard_by_phase_csv(summary_out / "sota_leaderboard_by_phase.csv", leaderboard_by_phase)
        write_leaderboard_by_phase_md(summary_out / "sota_leaderboard_by_phase.md", leaderboard_by_phase)
