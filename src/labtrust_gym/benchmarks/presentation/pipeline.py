"""Load run manifests and compute cross-method analytics for benchmark reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

BENCHMARK_BUNDLE_SCHEMA_VERSION = "1.2.0"


def load_run_meta(run_dir: Path) -> dict[str, Any]:
    path = Path(run_dir) / "run_meta.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_run_summary(run_dir: Path) -> dict[str, Any] | None:
    path = Path(run_dir) / "run_summary.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def default_report_out_dir(run_dir: Path) -> Path:
    """Convention: sibling folder ``{run_name}_report`` next to the run directory."""
    r = Path(run_dir).resolve()
    return r.parent / f"{r.name}_report"


def compute_run_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate comparable metrics across method rows (``build_rows`` shape)."""
    total = len(rows)
    by_status: dict[str, int] = {}
    wall_s: list[tuple[str, float]] = []
    llm_calls_sum = 0
    meta_tokens_sum = 0
    nonzero_tp = 0
    tp_values: list[float] = []
    resil_values: list[float] = []
    transport_positive = 0

    for r in rows:
        st = str(r.get("status") or "UNKNOWN")
        by_status[st] = by_status.get(st, 0) + 1
        ds = r.get("duration_s")
        if isinstance(ds, (int, float)) and ds > 0:
            wall_s.append((str(r.get("method") or "?"), float(ds)))
        calls = r.get("llm_calls")
        if isinstance(calls, int) and calls > 0:
            llm_calls_sum += calls
        mt = r.get("metadata_total_tokens")
        if isinstance(mt, int) and mt > 0:
            meta_tokens_sum += mt
        en = r.get("enrich") or {}
        mtp = en.get("mean_throughput")
        if isinstance(mtp, (int, float)):
            tp_values.append(float(mtp))
            if float(mtp) > 1e-12:
                nonzero_tp += 1
        mrs = en.get("mean_resilience")
        if isinstance(mrs, (int, float)):
            resil_values.append(float(mrs))
        tc = en.get("total_transport_consignment")
        if isinstance(tc, int) and tc > 0:
            transport_positive += 1

    wall_s.sort(key=lambda x: x[1], reverse=True)
    longest = wall_s[0] if wall_s else None
    total_wall_h = sum(s for _, s in wall_s) / 3600.0

    all_throughput_zero = bool(tp_values) and all(abs(v) < 1e-15 for v in tp_values)
    no_transport = transport_positive == 0 and by_status.get("PASS", 0) > 0

    insights: list[str] = []
    if by_status.get("PENDING", 0) > 0:
        insights.append(
            f"{by_status['PENDING']} method(s) still pending — sweep incomplete or interrupted."
        )
    if all_throughput_zero and tp_values:
        insights.append(
            "Mean episode throughput is zero for every completed cell in this run. "
            "Compare resilience, wall time, and LLM cost — PASS here reflects live "
            "harness checks, not logistics outcome."
        )
    if no_transport:
        insights.append(
            "No method recorded positive transport consignments in aggregated "
            "episode metrics."
        )

    return {
        "row_count": total,
        "by_status": by_status,
        "total_wall_clock_hours": round(total_wall_h, 4),
        "longest_method_wall": {"method": longest[0], "seconds": round(longest[1], 2)}
        if longest
        else None,
        "sum_llm_calls": llm_calls_sum,
        "sum_metadata_tokens": meta_tokens_sum,
        "methods_with_positive_mean_throughput": nonzero_tp,
        "mean_resilience_over_methods_with_data": round(
            sum(resil_values) / len(resil_values), 4
        )
        if resil_values
        else None,
        "methods_with_positive_transport": transport_positive,
        "flags": {
            "all_mean_throughput_zero": all_throughput_zero,
            "no_recorded_transport": no_transport,
        },
        "insights": insights,
    }


def first_git_sha_from_rows(rows: list[dict[str, Any]]) -> str | None:
    for r in rows:
        sha = (r.get("enrich") or {}).get("git_sha")
        if isinstance(sha, str) and len(sha.strip()) >= 7:
            return sha.strip()[:12]
    return None


def write_methods_matrix_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a flat CSV aligned with the HTML method matrix (one row per method)."""
    headers = (
        "method",
        "family",
        "status",
        "wall_seconds",
        "llm_model_id",
        "num_episodes",
        "mean_throughput",
        "mean_resilience",
        "transport_consignment_total",
        "llm_calls",
        "metadata_total_tokens",
        "llm_error_rate",
        "ended_at",
        "results_json_filename",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            en = r.get("enrich") or {}
            rp = r.get("result_path")
            name = Path(rp).name if rp else ""
            w.writerow(
                [
                    r.get("method"),
                    r.get("family"),
                    r.get("status"),
                    float(ds)
                    if isinstance((ds := r.get("duration_s")), (int, float))
                    else "",
                    r.get("llm_model_id") or en.get("llm_model_id") or "",
                    en.get("num_episodes") if en.get("num_episodes") is not None else "",
                    en.get("mean_throughput")
                    if isinstance(en.get("mean_throughput"), (int, float))
                    else "",
                    en.get("mean_resilience")
                    if isinstance(en.get("mean_resilience"), (int, float))
                    else "",
                    en.get("total_transport_consignment")
                    if isinstance(en.get("total_transport_consignment"), int)
                    else "",
                    r.get("llm_calls") if r.get("llm_calls") is not None else "",
                    r.get("metadata_total_tokens")
                    if r.get("metadata_total_tokens") is not None
                    else "",
                    r.get("llm_error_rate")
                    if r.get("llm_error_rate") is not None
                    else "",
                    r.get("ended_at") or "",
                    name,
                ],
            )


def build_presentation_manifest(
    *,
    schema_version: str,
    generated_at: str,
    run_dir: Path,
    scale_id: str,
    analytics: dict[str, Any],
    summary_counts: dict[str, int],
    git_sha_hint: str | None,
) -> dict[str, Any]:
    """Machine-readable bundle index for archival tools and CI."""
    return {
        "schema_version": schema_version,
        "kind": "labtrust_coordination_sweep_bundle",
        "generated_at": generated_at,
        "source_run_dir": str(run_dir),
        "scale_id": scale_id,
        "git_sha_from_cells": git_sha_hint,
        "artifacts": {
            "index.html": "Interactive HTML report (briefing, charts, sortable table).",
            "snapshot.json": "Full per-method snapshot including enrich blobs.",
            "analysis_summary.json": "Aggregates, flags, and narrative insight strings.",
            "methods_matrix.csv": "Flat matrix for pandas, R, or spreadsheets.",
            "manifest.json": "This bundle index.",
        },
        "summary_counts": summary_counts,
        "analytics_headline": {
            "total_wall_clock_hours": analytics.get("total_wall_clock_hours"),
            "sum_llm_calls": analytics.get("sum_llm_calls"),
            "sum_metadata_tokens": analytics.get("sum_metadata_tokens"),
        },
    }
