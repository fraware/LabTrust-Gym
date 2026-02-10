"""
Coordination result aggregation: SOTA leaderboard and method-class comparison.

Reads summary_coord.csv from a run directory, aggregates per method and per
method class (centralized, ripple, evolving, auctions, kernel_schedulers),
writes sota_leaderboard table and method_class_comparison table (CSV + MD).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

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


def _comparison_class(
    method_id: str, registry: dict[str, dict[str, Any]] | None
) -> str:
    """Map method_id to comparison class for method-class table."""
    if method_id in COMPARISON_CLASS_BY_METHOD:
        return COMPARISON_CLASS_BY_METHOD[method_id]
    if registry and method_id in registry:
        cls = (registry[method_id] or {}).get("coordination_class") or ""
        if cls == "centralized":
            return (
                "kernel_schedulers"
                if method_id.startswith("kernel_")
                else "centralized"
            )
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
    """Load summary_coord.csv and return list of row dicts with numeric fields parsed."""
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            row = dict(r)
            for k in (
                "perf.throughput",
                "robustness.resilience_score",
                "sec.stealth_success_rate",
            ):
                row[k] = _parse_float(row.get(k))
            row["safety.violations_total"] = _parse_float(
                row.get("safety.violations_total")
            )
            if row["safety.violations_total"] is not None:
                row["safety.violations_total"] = int(row["safety.violations_total"])
            rows.append(row)
    return rows


def build_sota_leaderboard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-method aggregates: throughput_mean, violations_mean, resilience_score_mean, stealth_success_rate_mean."""
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
        res = [_parse_float(r.get("robustness.resilience_score")) for r in group]
        stealth = [_parse_float(r.get("sec.stealth_success_rate")) for r in group]
        tp_vals = [x for x in tp if x is not None]
        viol_vals = [x for x in viol if x is not None]
        res_vals = [x for x in res if x is not None]
        stealth_vals = [x for x in stealth if x is not None]
        out.append(
            {
                "method_id": method_id,
                "throughput_mean": sum(tp_vals) / len(tp_vals) if tp_vals else None,
                "violations_mean": (
                    sum(viol_vals) / len(viol_vals) if viol_vals else None
                ),
                "resilience_score_mean": (
                    sum(res_vals) / len(res_vals) if res_vals else None
                ),
                "stealth_success_rate_mean": (
                    sum(stealth_vals) / len(stealth_vals) if stealth_vals else None
                ),
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
        res = [_parse_float(r.get("robustness.resilience_score")) for r in group]
        stealth = [_parse_float(r.get("sec.stealth_success_rate")) for r in group]
        tp_vals = [x for x in tp if x is not None]
        viol_vals = [x for x in viol if x is not None]
        res_vals = [x for x in res if x is not None]
        stealth_vals = [x for x in stealth if x is not None]
        out.append(
            {
                "method_id": method_id,
                "application_phase": application_phase,
                "throughput_mean": sum(tp_vals) / len(tp_vals) if tp_vals else None,
                "violations_mean": (
                    sum(viol_vals) / len(viol_vals) if viol_vals else None
                ),
                "resilience_score_mean": (
                    sum(res_vals) / len(res_vals) if res_vals else None
                ),
                "stealth_success_rate_mean": (
                    sum(stealth_vals) / len(stealth_vals) if stealth_vals else None
                ),
                "n_cells": len(group),
            }
        )
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
        res = [_parse_float(r.get("robustness.resilience_score")) for r in group]
        stealth = [_parse_float(r.get("sec.stealth_success_rate")) for r in group]
        out.append(
            {
                "method_class": class_id,
                "throughput_mean": (
                    sum(x for x in tp if x is not None)
                    / len([x for x in tp if x is not None])
                    if any(x is not None for x in tp)
                    else None
                ),
                "violations_mean": (
                    sum(x for x in viol if x is not None)
                    / len([x for x in viol if x is not None])
                    if any(x is not None for x in viol)
                    else None
                ),
                "resilience_score_mean": (
                    sum(x for x in res if x is not None)
                    / len([x for x in res if x is not None])
                    if res and any(x is not None for x in res)
                    else None
                ),
                "stealth_success_rate_mean": (
                    sum(x for x in stealth if x is not None)
                    / len([x for x in stealth if x is not None])
                    if stealth and any(x is not None for x in stealth)
                    else None
                ),
                "n_cells": len(group),
            }
        )
    return out


def write_leaderboard_by_phase_csv(
    out_path: Path, leaderboard: list[dict[str, Any]]
) -> None:
    """Write sota_leaderboard_by_phase.csv."""
    columns = [
        "method_id",
        "application_phase",
        "throughput_mean",
        "violations_mean",
        "resilience_score_mean",
        "stealth_success_rate_mean",
        "n_cells",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in leaderboard:
            row = {k: r.get(k) for k in columns}
            for k in (
                "throughput_mean",
                "violations_mean",
                "resilience_score_mean",
                "stealth_success_rate_mean",
            ):
                if row.get(k) is None:
                    row[k] = ""
                elif isinstance(row[k], float):
                    row[k] = round(row[k], 4)
            w.writerow(row)


def write_leaderboard_by_phase_md(
    out_path: Path, leaderboard: list[dict[str, Any]]
) -> None:
    """Write sota_leaderboard_by_phase.md (markdown table)."""
    lines = [
        "# SOTA leaderboard by method and phase (coordination)",
        "",
        "Per-method and per-application_phase means.",
        "",
        "| method_id | application_phase | throughput_mean | violations_mean | resilience_score_mean | stealth_success_rate_mean | n_cells |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in leaderboard:
        tp = r.get("throughput_mean")
        viol = r.get("violations_mean")
        res = r.get("resilience_score_mean")
        stealth = r.get("stealth_success_rate_mean")
        n = r.get("n_cells", 0)
        cells = [
            r.get("method_id", ""),
            r.get("application_phase", ""),
            f"{tp:.4f}" if tp is not None else "—",
            f"{viol:.2f}" if viol is not None else "—",
            f"{res:.4f}" if res is not None else "—",
            f"{stealth:.4f}" if stealth is not None else "—",
            str(n),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_leaderboard_csv(out_path: Path, leaderboard: list[dict[str, Any]]) -> None:
    """Write sota_leaderboard.csv."""
    columns = [
        "method_id",
        "throughput_mean",
        "violations_mean",
        "resilience_score_mean",
        "stealth_success_rate_mean",
        "n_cells",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in leaderboard:
            row = {k: r.get(k) for k in columns}
            for k in (
                "throughput_mean",
                "violations_mean",
                "resilience_score_mean",
                "stealth_success_rate_mean",
            ):
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
) -> None:
    """Write sota_leaderboard.md (markdown table)."""
    lines = [
        "# SOTA leaderboard (coordination)",
        "",
        "Per-method means over all cells (scale x injection).",
        "",
    ]
    if source_note:
        lines.extend([source_note, ""])
    lines.extend(
        [
            "| method_id | throughput_mean | violations_mean | resilience_score_mean | stealth_success_rate_mean | n_cells |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for r in leaderboard:
        tp = r.get("throughput_mean")
        viol = r.get("violations_mean")
        res = r.get("resilience_score_mean")
        stealth = r.get("stealth_success_rate_mean")
        n = r.get("n_cells", 0)
        cells = [
            r.get("method_id", ""),
            f"{tp:.4f}" if tp is not None else "—",
            f"{viol:.2f}" if viol is not None else "—",
            f"{res:.4f}" if res is not None else "—",
            f"{stealth:.4f}" if stealth is not None else "—",
            str(n),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_method_class_csv(out_path: Path, comparison: list[dict[str, Any]]) -> None:
    """Write method_class_comparison.csv."""
    columns = [
        "method_class",
        "throughput_mean",
        "violations_mean",
        "resilience_score_mean",
        "stealth_success_rate_mean",
        "n_cells",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in comparison:
            row = {k: r.get(k) for k in columns}
            for k in (
                "throughput_mean",
                "violations_mean",
                "resilience_score_mean",
                "stealth_success_rate_mean",
            ):
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
    """Write method_class_comparison.md (markdown table)."""
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
            "| method_class | throughput_mean | violations_mean | resilience_score_mean | stealth_success_rate_mean | n_cells |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for r in comparison:
        tp = r.get("throughput_mean")
        viol = r.get("violations_mean")
        res = r.get("resilience_score_mean")
        stealth = r.get("stealth_success_rate_mean")
        n = r.get("n_cells", 0)
        cells = [
            r.get("method_class", ""),
            f"{tp:.4f}" if tp is not None else "—",
            f"{viol:.2f}" if viol is not None else "—",
            f"{res:.4f}" if res is not None else "—",
            f"{stealth:.4f}" if stealth is not None else "—",
            str(n),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


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
            f"No summary CSV under {in_dir}. "
            "Looked for summary/summary_coord.csv, summary_coord.csv, pack_summary.csv."
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
        reg_path = (
            repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
        )
        if reg_path.is_file():
            try:
                from labtrust_gym.policy.coordination import load_coordination_methods

                registry = load_coordination_methods(reg_path)
            except Exception:
                pass

    leaderboard = build_sota_leaderboard(rows)
    comparison = build_method_class_comparison(rows, registry)

    summary_out = out_dir / "summary"
    summary_out.mkdir(parents=True, exist_ok=True)
    write_leaderboard_csv(summary_out / "sota_leaderboard.csv", leaderboard)
    write_leaderboard_md(
        summary_out / "sota_leaderboard.md", leaderboard, source_note=source_note
    )
    write_method_class_csv(summary_out / "method_class_comparison.csv", comparison)
    write_method_class_md(
        summary_out / "method_class_comparison.md", comparison, source_note=source_note
    )
    if has_phase:
        leaderboard_by_phase = build_sota_leaderboard_by_phase(rows)
        write_leaderboard_by_phase_csv(
            summary_out / "sota_leaderboard_by_phase.csv", leaderboard_by_phase
        )
        write_leaderboard_by_phase_md(
            summary_out / "sota_leaderboard_by_phase.md", leaderboard_by_phase
        )
