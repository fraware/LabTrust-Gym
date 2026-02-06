"""
Summarize benchmark results: load multiple results.json, aggregate by task + baseline + partner_id,
output wide CSV + markdown table (mean/std for throughput, TAT, on_time_rate, violations, etc.).
Emits summary_v0.2.csv (CI-stable, same semantics as before) and summary_v0.3.csv (paper-grade: quantiles, CI).
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

RESULTS_SCHEMA_VERSION = "0.2"
RESULTS_SCHEMA_VERSION_V03 = "0.3"
METRIC_KEYS = [
    "throughput",
    "p50_turnaround_s",
    "p95_turnaround_s",
    "on_time_rate",
    "violations_total",
    "critical_communication_compliance_rate",
    "detection_latency_s",
    "containment_success",
    "time_to_first_detected_security_violation",
    "fraction_of_attacks_contained",
    "forensic_quality_score",
]


def _normalize_to_v02(data: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a results dict to v0.2 shape (task, seeds, policy_fingerprint, partner_id, git_sha, agent_baseline_id, episodes)."""
    task = data.get("task")
    episodes = data.get("episodes")
    if not task or not isinstance(episodes, list):
        return None
    seeds = data.get("seeds")
    if not seeds and episodes:
        seeds = [
            ep.get("seed")
            for ep in episodes
            if isinstance(ep, dict) and ep.get("seed") is not None
        ]
    agent_baseline_id = data.get("agent_baseline_id") or "scripted_ops_v1"
    git_sha = data.get("git_sha") or data.get("git_commit_hash")
    return {
        "task": str(task),
        "seeds": seeds or [],
        "policy_fingerprint": data.get("policy_fingerprint"),
        "partner_id": data.get("partner_id"),
        "git_sha": git_sha,
        "agent_baseline_id": str(agent_baseline_id),
        "episodes": episodes,
    }


def _violations_total(metrics: dict[str, Any]) -> int:
    """Sum violation counts from violations_by_invariant_id."""
    vbi = metrics.get("violations_by_invariant_id") or {}
    if isinstance(vbi, dict):
        return sum(int(x) for x in vbi.values())
    return 0


def _extract_metric(metrics: dict[str, Any], key: str) -> float | None:
    if key == "violations_total":
        return float(_violations_total(metrics))
    if key == "containment_success":
        v = metrics.get("containment_success")
        if v is None:
            return None
        return 1.0 if v else 0.0
    v = metrics.get(key)
    if v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    return None


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    """Percentile p (0..100) from sorted list. Returns None if empty."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def _ci_95_mean(vals: list[float]) -> tuple[float | None, float | None]:
    """95% CI for mean: (lower, upper). Returns (None, None) if len < 2 or empty."""
    if len(vals) < 2:
        return (None, None)
    mean = statistics.mean(vals)
    std = statistics.stdev(vals)
    n = len(vals)
    half = 1.96 * std / math.sqrt(n)
    return (mean - half, mean + half)


def _aggregate_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute mean and std for each metric across episodes. Returns dict with key_mean, key_std (v0.2)."""
    if not episodes:
        return {}
    values_by_key: dict[str, list[float]] = {k: [] for k in METRIC_KEYS}
    for ep in episodes:
        metrics = ep.get("metrics") or {}
        for key in METRIC_KEYS:
            x = _extract_metric(metrics, key)
            if x is not None:
                values_by_key[key].append(x)
    out: dict[str, Any] = {}
    for key in METRIC_KEYS:
        vals = values_by_key[key]
        if vals:
            out[f"{key}_mean"] = statistics.mean(vals)
            out[f"{key}_std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        else:
            out[f"{key}_mean"] = None
            out[f"{key}_std"] = None
    comm_keys = ["msg_count", "p95_latency_ms", "drop_rate"]
    for ck in comm_keys:
        vals = []
        for ep in episodes:
            comm = (ep.get("metrics") or {}).get("coordination") or {}
            v = (comm.get("comm") or {}).get(ck)
            if v is not None:
                vals.append(float(v))
        if vals:
            out[f"comm_{ck}_mean"] = statistics.mean(vals)
            out[f"comm_{ck}_std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        else:
            out[f"comm_{ck}_mean"] = None
            out[f"comm_{ck}_std"] = None
    return out


def _aggregate_episodes_v03(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Paper-grade: v0.2 aggregates plus quantiles (p50, p90) and 95% CI for key metrics."""
    base = _aggregate_episodes(episodes)
    if not episodes:
        return base
    values_by_key: dict[str, list[float]] = {k: [] for k in METRIC_KEYS}
    for ep in episodes:
        metrics = ep.get("metrics") or {}
        for key in METRIC_KEYS:
            x = _extract_metric(metrics, key)
            if x is not None:
                values_by_key[key].append(x)
    for key in METRIC_KEYS:
        vals = values_by_key[key]
        if not vals:
            continue
        sorted_vals = sorted(vals)
        base[f"{key}_p50"] = _percentile(sorted_vals, 50)
        base[f"{key}_p90"] = _percentile(sorted_vals, 90)
        lo, hi = _ci_95_mean(vals)
        base[f"{key}_mean_ci_lower"] = lo
        base[f"{key}_mean_ci_upper"] = hi
    return base


def load_results_from_path(path: Path) -> list[dict[str, Any]]:
    """Load one or more results.json from a path (file or directory). Returns list of normalized v0.2 dicts."""
    path = Path(path).resolve()
    loaded: list[dict[str, Any]] = []
    if path.is_file():
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("episodes") is not None:
                    norm = _normalize_to_v02(data)
                    if norm:
                        loaded.append(norm)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            n = _normalize_to_v02(item)
                            if n:
                                loaded.append(n)
            except Exception:
                pass
        return loaded
    if path.is_dir():
        for f in sorted(path.rglob("results*.json")):
            if f.is_file():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("episodes") is not None:
                        norm = _normalize_to_v02(data)
                        if norm:
                            loaded.append(norm)
                except Exception:
                    pass
    return loaded


def summarize_results(
    results_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Group by (task, agent_baseline_id, partner_id) and aggregate metrics (mean/std).
    Returns list of row dicts for CSV/markdown: task, agent_baseline_id, partner_id, n_episodes, throughput_mean, throughput_std, ...
    (v0.2: CI-stable; same semantics as before.)
    """
    from collections import defaultdict

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in results_list:
        task = r.get("task") or "unknown"
        baseline = r.get("agent_baseline_id") or "scripted_ops_v1"
        partner = r.get("partner_id") or ""
        key = (task, baseline, partner)
        groups[key].append(r)

    rows: list[dict[str, Any]] = []
    for (task, baseline, partner), group in sorted(groups.items()):
        all_episodes: list[dict[str, Any]] = []
        for g in group:
            all_episodes.extend(g.get("episodes") or [])
        agg = _aggregate_episodes(all_episodes)
        row: dict[str, Any] = {
            "task": task,
            "agent_baseline_id": baseline,
            "partner_id": partner or None,
            "n_episodes": len(all_episodes),
        }
        row.update(agg)
        rows.append(row)
    return rows


def summarize_results_v03(
    results_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Same grouping as summarize_results; aggregate with quantiles and 95% CI (paper-grade v0.3).
    Returns list of row dicts with v0.2 columns plus *_p50, *_p90, *_mean_ci_lower, *_mean_ci_upper.
    """
    from collections import defaultdict

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in results_list:
        task = r.get("task") or "unknown"
        baseline = r.get("agent_baseline_id") or "scripted_ops_v1"
        partner = r.get("partner_id") or ""
        key = (task, baseline, partner)
        groups[key].append(r)

    rows: list[dict[str, Any]] = []
    for (task, baseline, partner), group in sorted(groups.items()):
        all_episodes: list[dict[str, Any]] = []
        for g in group:
            all_episodes.extend(g.get("episodes") or [])
        agg = _aggregate_episodes_v03(all_episodes)
        row: dict[str, Any] = {
            "task": task,
            "agent_baseline_id": baseline,
            "partner_id": partner or None,
            "n_episodes": len(all_episodes),
        }
        row.update(agg)
        rows.append(row)
    return rows


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Convert rows to CSV (header + rows). Deterministic column order."""
    if not rows:
        return ""
    all_keys: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in sorted(r.keys()):
            if k not in seen:
                seen.add(k)
                all_keys.append(k)
    header = ",".join(_csv_escape(str(k)) for k in all_keys)
    lines = [header]
    for r in rows:
        cells = [
            _csv_escape(str(r.get(k, "")) if r.get(k) is not None else "")
            for k in all_keys
        ]
        lines.append(",".join(cells))
    return "\n".join(lines)


def _csv_escape(s: str) -> str:
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def rows_to_markdown_table(rows: list[dict[str, Any]]) -> str:
    """Convert rows to markdown table."""
    if not rows:
        return ""
    all_keys: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in sorted(r.keys()):
            if k not in seen:
                seen.add(k)
                all_keys.append(k)
    header = "| " + " | ".join(str(k) for k in all_keys) + " |"
    sep = "| " + " | ".join("---" for _ in all_keys) + " |"
    lines = [header, sep]
    for r in rows:
        cells = []
        for k in all_keys:
            v = r.get(k)
            if v is None:
                cells.append("")
            elif isinstance(v, float):
                cells.append(f"{v:.4g}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def validate_results_v02(
    data: dict[str, Any], schema_path: Path | None = None
) -> list[str]:
    """
    Validate a results dict against results.v0.2.schema.json. Returns list of error messages; empty if valid.
    """
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema required for validation"]
    path = (
        schema_path
        or Path(__file__).resolve().parent.parent.parent
        / "policy"
        / "schemas"
        / "results.v0.2.schema.json"
    )
    if not path.exists():
        return []
    schema = json.loads(path.read_text(encoding="utf-8"))
    # Normalize: ensure schema_version and agent_baseline_id for validation
    normalized = _normalize_to_v02(data)
    if not normalized:
        return ["Invalid results: missing task or episodes"]
    normalized["schema_version"] = data.get("schema_version", "0.2")
    normalized["agent_baseline_id"] = data.get("agent_baseline_id", "scripted_ops_v1")
    try:
        jsonschema.validate(instance=normalized, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [str(e)]
    except Exception as e:
        return [str(e)]


def validate_results_v03(
    data: dict[str, Any], schema_path: Path | None = None
) -> list[str]:
    """
    Validate a results dict against results.v0.3.schema.json. Document must have schema_version "0.3".
    Returns list of error messages; empty if valid.
    """
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema required for validation"]
    path = (
        schema_path
        or Path(__file__).resolve().parent.parent.parent
        / "policy"
        / "schemas"
        / "results.v0.3.schema.json"
    )
    if not path.exists():
        return []
    schema = json.loads(path.read_text(encoding="utf-8"))
    normalized = _normalize_to_v02(data)
    if not normalized:
        return ["Invalid results: missing task or episodes"]
    normalized["schema_version"] = "0.3"
    normalized["agent_baseline_id"] = data.get("agent_baseline_id", "scripted_ops_v1")
    try:
        jsonschema.validate(instance=normalized, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [str(e)]
    except Exception as e:
        return [str(e)]


def _load_raw_results_with_metadata(in_paths: list[Path]) -> list[dict[str, Any]]:
    """Load raw results dicts (with metadata) from paths. One dict per results file."""
    raw_list: list[dict[str, Any]] = []
    for path_in in in_paths:
        p = Path(path_in).resolve()
        if p.is_file() and p.suffix.lower() == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("episodes") is not None:
                    raw_list.append(data)
            except Exception:
                pass
        elif p.is_dir():
            for f in sorted(p.rglob("results*.json")):
                if f.is_file():
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        if isinstance(data, dict) and data.get("episodes") is not None:
                            raw_list.append(data)
                    except Exception:
                        pass
    return raw_list


def _build_llm_economics_rows(
    raw_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build one row per result that has metadata.llm_backend_id (for llm_economics table)."""
    rows: list[dict[str, Any]] = []
    for data in raw_results:
        meta = data.get("metadata") or {}
        if not meta.get("llm_backend_id"):
            continue
        rows.append(
            {
                "task": data.get("task", ""),
                "agent_baseline_id": data.get("agent_baseline_id", ""),
                "llm_backend_id": meta.get("llm_backend_id"),
                "llm_model_id": meta.get("llm_model_id"),
                "total_tokens": meta.get("total_tokens"),
                "tokens_per_step": meta.get("tokens_per_step"),
                "estimated_cost_usd": meta.get("estimated_cost_usd"),
                "mean_llm_latency_ms": meta.get("mean_llm_latency_ms"),
                "p50_llm_latency_ms": meta.get("p50_llm_latency_ms"),
                "p95_llm_latency_ms": meta.get("p95_llm_latency_ms"),
                "llm_error_rate": meta.get("llm_error_rate"),
            }
        )
    return rows


SUMMARY_MD_HEADER = """# Benchmark summary

## Metric definitions

| Metric | Description |
|--------|-------------|
| task | Benchmark task name (e.g. TaskA, TaskB). |
| agent_baseline_id | Baseline or agent ID (e.g. scripted_ops_v1). |
| partner_id | Partner overlay ID if used; empty otherwise. |
| n_episodes | Number of episodes aggregated for this row. |
| throughput_mean | Mean specimens released (RELEASE_RESULT) per episode. Higher is better. |
| throughput_std | Std dev of throughput across episodes. |
| p50_turnaround_s_mean | Mean 50th percentile turnaround (accept to release) in seconds. |
| p95_turnaround_s_mean | Mean 95th percentile turnaround in seconds. Lower is better for SLA. |
| on_time_rate_mean | Fraction of results released within SLA window. |
| violations_total_mean | Mean total invariant violations per episode. Lower is better. |
| critical_communication_compliance_rate_mean | Fraction of critical results with required notify/ack. |

## Results

"""


def run_summarize(
    in_paths: list[Path],
    out_dir: Path,
    out_basename: str = "summary",
) -> tuple[Path, Path]:
    """
    Load all results from in_paths (files or dirs), aggregate, write summary_v0.2.csv,
    summary_v0.3.csv, summary.csv (copy of v0.2), and summary.md.
    When any result has metadata.llm_backend_id, also write llm_economics.csv and llm_economics.md.
    Returns (path_to_summary_v02_csv, path_to_md). v0.2 CSV is CI-stable; v0.3 CSV is paper-grade.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, Any]] = []
    for p in in_paths:
        all_results.extend(load_results_from_path(Path(p)))
    rows_v02 = summarize_results(all_results)
    rows_v03 = summarize_results_v03(all_results)
    csv_v02_path = out_dir / f"{out_basename}_v0.2.csv"
    csv_v03_path = out_dir / f"{out_basename}_v0.3.csv"
    csv_path = out_dir / f"{out_basename}.csv"
    md_path = out_dir / f"{out_basename}.md"
    csv_v02_path.write_text(rows_to_csv(rows_v02), encoding="utf-8")
    csv_v03_path.write_text(rows_to_csv(rows_v03), encoding="utf-8")
    csv_path.write_text(rows_to_csv(rows_v02), encoding="utf-8")
    md_content = SUMMARY_MD_HEADER + rows_to_markdown_table(rows_v02)
    md_path.write_text(md_content, encoding="utf-8")
    raw_list = _load_raw_results_with_metadata(in_paths)
    llm_rows = _build_llm_economics_rows(raw_list)
    if llm_rows:
        llm_csv = out_dir / "llm_economics.csv"
        llm_md = out_dir / "llm_economics.md"
        llm_csv.write_text(rows_to_csv(llm_rows), encoding="utf-8")
        llm_md.write_text(rows_to_markdown_table(llm_rows), encoding="utf-8")
    return csv_path, md_path
