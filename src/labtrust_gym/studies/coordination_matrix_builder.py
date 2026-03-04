"""
Coordination Matrix builder: produce CoordinationMatrix v0.1 from llm_live coordination run dirs.

Builds the matrix artifact from Phase 1 policies (inputs, column_map, spec), source tables
in the run directory, and enforces llm_live-only, deterministic extraction, worst-case
attack aggregation, robust_minmax normalization, hard gates, and per-scale ranking.

Output validates against policy/schemas/coordination_matrix.v0.1.schema.json.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    load_policy_file,
    validate_against_schema,
)

# Default policy filenames (Phase 1)
_INPUTS_FILENAME = "coordination_matrix_inputs.v0.1.yaml"
_COLUMN_MAP_FILENAME = "coordination_matrix_column_map.v0.1.yaml"
_SPEC_FILENAME = "coordination_matrix_spec.v0.1.yaml"
_OUTPUT_SCHEMA_FILENAME = "coordination_matrix.v0.1.schema.json"

# Canonical metric sources (single file each; builder uses only these when present)
CANONICAL_CLEAN_SOURCE = "summary_coord.csv"
CANONICAL_ATTACKED_SOURCE = "pack_summary.csv"
CLEAN_KEY_COLUMNS = ["scale_id", "method_id"]
ATTACKED_KEY_COLUMNS = ["scale_id", "method_id", "injection_id"]

# When matrix_mode is "pack", clean metrics can be derived from pack_summary baseline rows
PACK_COLUMN_TO_CLEAN_METRIC: dict[str, str] = {
    "perf.throughput": "throughput_per_hr",
    "perf.p95_tat": "p95_tat_s",
    "safety.violations_total": "violation_rate",
    "cost.estimated_cost_usd": "estimated_cost_usd",
}
MATRIX_MODE_PACK = "pack"

# Canonical metadata search order for pipeline_mode
_METADATA_CANDIDATES = [
    "metadata.json",
    "index.json",
    "results.json",
]


def _get_pipeline_mode_from_run_dir(run_dir: Path, strict: bool) -> str:
    """
    Attempt to read pipeline_mode from the most canonical metadata in run_dir.
    Search order: metadata.json, index.json, results.json; then summary/, then rglob results.json.
    """
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run_dir is not a directory: {run_dir}")

    # Direct children first
    for name in _METADATA_CANDIDATES:
        p = run_dir / name
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "pipeline_mode" in data:
                    return str(data["pipeline_mode"])
            except (json.JSONDecodeError, OSError):
                continue

    # summary/ (e.g. coordination study layout)
    summary_dir = run_dir / "summary"
    if summary_dir.is_dir():
        for name in _METADATA_CANDIDATES:
            p = summary_dir / name
            if p.is_file():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "pipeline_mode" in data:
                        return str(data["pipeline_mode"])
                except (json.JSONDecodeError, OSError):
                    continue

    # Any results.json under run_dir
    for res_path in run_dir.rglob("results.json"):
        if not res_path.is_file():
            continue
        try:
            data = json.loads(res_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "pipeline_mode" in data:
                return str(data["pipeline_mode"])
        except (json.JSONDecodeError, OSError):
            continue

    if strict:
        raise ValueError(
            "Could not determine pipeline_mode from run directory. "
            "Expected metadata.json, index.json, or results.json with 'pipeline_mode'."
        )
    return "deterministic"  # fallback only when not strict


def _assert_llm_live(pipeline_mode: str) -> None:
    """Raise if not llm_live with the required message."""
    if pipeline_mode != "llm_live":
        raise ValueError(
            f"Matrix builder is llm_live-only; offline pipelines are out of scope. Got pipeline_mode={pipeline_mode!r}."
        )


def _find_first_file(run_dir: Path, filename: str) -> Path | None:
    """Return first path under run_dir (or run_dir itself) whose name equals filename."""
    if (run_dir / filename).is_file():
        return run_dir / filename
    for p in run_dir.rglob(filename):
        if p.is_file():
            return p
    return None


def _get_table_headers(path: Path) -> list[str]:
    """Return column names from table (CSV header or JSON first row keys)."""
    suf = path.suffix.lower()
    if suf == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader.fieldnames or [])
    if suf == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return list(data[0].keys())
        if isinstance(data, dict):
            for key in ("results", "rows", "entries", "cells"):
                if key in data and isinstance(data[key], list) and data[key] and isinstance(data[key][0], dict):
                    return list(data[key][0].keys())
    return []


def _validate_canonical_table(
    path: Path,
    key_columns: list[str],
    metric_ids: list[str],
    column_map: dict[str, Any],
    role: str,
) -> list[str]:
    """
    Validate canonical table: required key columns present, no duplicate keys,
    at least one candidate column per metric_id present. Returns list of error messages.
    """
    errors: list[str] = []
    headers = _get_table_headers(path)
    for k in key_columns:
        if k not in headers:
            errors.append(f"{role}: missing key column {k!r}; headers: {headers}")
    if errors:
        return errors
    rows = _load_table(path)
    seen: dict[tuple[str, ...], int] = {}
    for i, row in enumerate(rows):
        key = _get_cell_key(row, key_columns)
        if len(key) >= len(key_columns):
            tkey = key[: len(key_columns)]
            if tkey in seen:
                errors.append(f"{role}: duplicate key {tkey} (rows {seen[tkey] + 1} and {i + 1})")
            else:
                seen[tkey] = i
    for mid in metric_ids:
        entry = column_map.get(mid)
        if not entry:
            continue
        candidates = entry.get("candidates") or []
        if not any(c in headers for c in candidates):
            errors.append(
                f"{role}: metric_id {mid!r} has no candidate column in table; "
                f"candidates: {candidates}; attempted_columns: {headers}"
            )
    return errors


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    """Load CSV as list of dicts (header -> row values)."""
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    """Load JSON; if top-level is list, return it; if dict, look for results/rows/entries or single row."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("results", "rows", "entries", "cells"):
            if key in data and isinstance(data[key], list):
                return [r for r in data[key] if isinstance(r, dict)]
        # Single row as dict
        if "scale_id" in data or "method_id" in data:
            return [data]
    return []


def _load_table(path: Path) -> list[dict[str, Any]]:
    """Load table from CSV or JSON."""
    suf = path.suffix.lower()
    if suf == ".csv":
        return _load_csv_rows(path)
    if suf == ".json":
        return _load_json_rows(path)
    raise ValueError(f"Unsupported table format: {path.suffix}")


def _apply_transform(value: float, transform: str) -> float:
    """Apply column_map transform (identity, pct_to_rate, ms_to_s, s_to_ms)."""
    if transform == "identity":
        return value
    if transform == "pct_to_rate":
        return value / 100.0
    if transform == "ms_to_s":
        return value / 1000.0
    if transform == "s_to_ms":
        return value * 1000.0
    return value


def _get_cell_key(row: dict[str, Any], keys: list[str]) -> tuple[str, ...]:
    """Return tuple of row values for key columns; use empty string if missing."""
    return tuple(str(row.get(k, "")).strip() for k in keys)


def _extract_metric_from_row(
    row: dict[str, Any],
    entry: dict[str, Any],
) -> float | None:
    """Try candidates in order; apply transform; return float or None."""
    candidates = entry.get("candidates") or []
    transform = entry.get("transform") or "identity"
    for col in candidates:
        if col not in row:
            continue
        raw = row[col]
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        return _apply_transform(val, transform)
    return None


def _derive_clean_cells_from_pack(
    run_dir: Path,
    clean_metric_ids: list[str],
) -> dict[tuple[str, str], dict[str, float | None]]:
    """
    Derive clean (baseline) cells from pack_summary.csv when no summary_coord exists.
    Uses rows where injection_id is none; maps pack columns to clean metric_ids.
    """
    pack_path = _find_first_file(run_dir, CANONICAL_ATTACKED_SOURCE)
    if pack_path is None:
        raise FileNotFoundError(f"Cannot derive clean cells: {CANONICAL_ATTACKED_SOURCE} not found under {run_dir}")
    rows = _load_table(pack_path)
    baseline_rows = [r for r in rows if (str(r.get("injection_id") or "").strip().lower() in ("none", ""))]
    if not baseline_rows:
        raise ValueError(f"pack_summary has no baseline rows (injection_id=none) in {pack_path}")
    out: dict[tuple[str, str], dict[str, float | None]] = {}
    for r in baseline_rows:
        scale_id = str(r.get("scale_id") or "").strip()
        method_id = str(r.get("method_id") or "").strip()
        if not scale_id or not method_id:
            continue
        key = (scale_id, method_id)
        cell: dict[str, float | None] = {mid: None for mid in clean_metric_ids}
        for col, mid in PACK_COLUMN_TO_CLEAN_METRIC.items():
            if mid not in cell:
                continue
            raw = r.get(col)
            if raw is None or raw == "":
                continue
            try:
                cell[mid] = float(raw)
            except (TypeError, ValueError):
                pass
        out[key] = cell
    return out


class _MetricExtractionError(Exception):
    """Raised when a required metric cannot be extracted (missing_policy=error)."""

    def __init__(
        self,
        metric_id: str,
        preferred_sources: list[str],
        candidates: list[str],
        files_tried: list[tuple[str, bool]],
        attempted_columns: list[str] | None = None,
    ) -> None:
        self.metric_id = metric_id
        self.preferred_sources = preferred_sources
        self.candidates = candidates
        self.files_tried = files_tried
        self.attempted_columns = attempted_columns or []
        msg = (
            f"Required metric {metric_id!r} missing. "
            f"Preferred sources: {preferred_sources}; candidates: {candidates}. "
            f"Files tried: {files_tried}."
        )
        if self.attempted_columns:
            msg += f" Attempted columns in table: {self.attempted_columns}."
        super().__init__(msg)


def _extract_clean_metrics(
    run_dir: Path,
    sources: list[str],
    column_map: dict[str, Any],
    metric_ids: list[str],
    key_columns: list[str],
) -> dict[tuple[str, str], dict[str, float | None]]:
    """
    Load canonical clean source only. Key rows by (scale_id, method_id), extract each metric_id.
    Uses CANONICAL_CLEAN_SOURCE when present; fails with precise message if missing or malformed.
    """
    canonical_path = _find_first_file(run_dir, CANONICAL_CLEAN_SOURCE)
    if canonical_path is None:
        attempted = [
            (name, _find_first_file(run_dir, name) is not None) for name in (sources or [CANONICAL_CLEAN_SOURCE])
        ]
        metric_detail = "; ".join(
            f"{mid!r}: candidates {column_map.get(mid, {}).get('candidates', [])!r}" for mid in metric_ids
        )
        raise FileNotFoundError(
            f"Canonical clean source {CANONICAL_CLEAN_SOURCE!r} not found under {run_dir}. "
            f"Required key columns: {key_columns}. "
            f"Attempted sources: {attempted}. "
            f"Required metrics and candidate columns: {metric_detail}"
        )

    all_rows = _load_table(canonical_path)
    if not all_rows:
        raise ValueError(f"Canonical clean source {canonical_path} has no rows. Required key columns: {key_columns}.")

    validation_errors = _validate_canonical_table(
        canonical_path,
        key_columns,
        metric_ids,
        column_map,
        role="clean",
    )
    if validation_errors:
        raise ValueError(f"Canonical clean source {canonical_path} failed validation: " + "; ".join(validation_errors))

    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for row in all_rows:
        key = _get_cell_key(row, key_columns)
        if len(key) >= 2:
            cells[key] = row

    headers = _get_table_headers(canonical_path)
    out: dict[tuple[str, str], dict[str, float | None]] = {}
    for cell_key, row in cells.items():
        out[cell_key] = {}
        for mid in metric_ids:
            entry = column_map.get(mid)
            if not entry:
                out[cell_key][mid] = None
                continue
            preferred = entry.get("preferred_sources") or []
            candidates = entry.get("candidates") or []
            missing_policy = entry.get("missing_policy") or "error"
            val = _extract_metric_from_row(row, entry)
            if val is None and missing_policy == "error":
                files_tried = [
                    (CANONICAL_CLEAN_SOURCE, True),
                ]
                raise _MetricExtractionError(mid, preferred, candidates, files_tried, attempted_columns=headers)
            out[cell_key][mid] = val
    return out


def _extract_attacked_metrics(
    run_dir: Path,
    sources: list[str],
    column_map: dict[str, Any],
    metric_ids: list[str],
    key_columns: list[str],
) -> dict[tuple[str, str, str], dict[str, float | None]]:
    """
    Load canonical attacked source only. Rows keyed by (scale_id, method_id, injection_id).
    Return per (scale_id, method_id, injection_id); caller aggregates worst-case.
    When metric_ids is non-empty, requires CANONICAL_ATTACKED_SOURCE; fails precisely if missing.
    """
    if not metric_ids:
        return {}

    canonical_path = _find_first_file(run_dir, CANONICAL_ATTACKED_SOURCE)
    if canonical_path is None:
        attempted = [
            (name, _find_first_file(run_dir, name) is not None) for name in (sources or [CANONICAL_ATTACKED_SOURCE])
        ]
        metric_detail = "; ".join(
            f"{mid!r}: candidates {column_map.get(mid, {}).get('candidates', [])!r}" for mid in metric_ids
        )
        raise FileNotFoundError(
            f"Canonical attacked source {CANONICAL_ATTACKED_SOURCE!r} not found under {run_dir}. "
            f"Required key columns: {key_columns}. "
            f"Attempted sources: {attempted}. "
            f"Required metrics and candidate columns: {metric_detail}"
        )

    all_rows = _load_table(canonical_path)
    if not all_rows:
        return {}

    validation_errors = _validate_canonical_table(
        canonical_path,
        key_columns,
        metric_ids,
        column_map,
        role="attacked",
    )
    if validation_errors:
        raise ValueError(
            f"Canonical attacked source {canonical_path} failed validation: " + "; ".join(validation_errors)
        )

    cells: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in all_rows:
        key = _get_cell_key(row, key_columns)
        cells[key] = row

    headers = _get_table_headers(canonical_path)
    out: dict[tuple[str, str, str], dict[str, float | None]] = {}
    for cell_key, row in cells.items():
        scale_id = cell_key[0] if len(cell_key) > 0 else ""
        method_id = cell_key[1] if len(cell_key) > 1 else ""
        injection_id = cell_key[2] if len(cell_key) > 2 else ""
        out[(scale_id, method_id, injection_id)] = {}
        for mid in metric_ids:
            entry = column_map.get(mid)
            if not entry:
                out[(scale_id, method_id, injection_id)][mid] = None
                continue
            val = _extract_metric_from_row(row, entry)
            missing_policy = entry.get("missing_policy") or "error"
            if val is None and missing_policy == "error":
                raise _MetricExtractionError(
                    mid,
                    entry.get("preferred_sources") or [],
                    entry.get("candidates") or [],
                    [(CANONICAL_ATTACKED_SOURCE, True)],
                    attempted_columns=headers,
                )
            out[(scale_id, method_id, injection_id)][mid] = val
    return out


def _aggregate_attacked_worst_case(
    per_injection: dict[tuple[str, str, str], dict[str, float | None]],
    metric_ids: list[str],
    directions: dict[str, str],
) -> dict[tuple[str, str], dict[str, float | None]]:
    """
    Aggregate attacked metrics across injections: worst-case.
    For lower_is_better: max value (worst). For higher_is_better: min value (worst).
    If only one row per (scale_id, method_id), use it directly.
    """
    # Group by (scale_id, method_id)
    by_cell: dict[tuple[str, str], list[dict[str, float | None]]] = {}
    for (scale_id, method_id, _inj), metrics in per_injection.items():
        key = (scale_id, method_id)
        by_cell.setdefault(key, []).append(metrics)

    out: dict[tuple[str, str], dict[str, float | None]] = {}
    for key, list_metrics in by_cell.items():
        out[key] = {}
        for mid in metric_ids:
            vals = [m.get(mid) for m in list_metrics if m.get(mid) is not None]
            if not vals:
                out[key][mid] = None
                continue
            direction = directions.get(mid, "lower_is_better")
            if direction == "lower_is_better":
                out[key][mid] = max(vals)
            else:
                out[key][mid] = min(vals)
    return out


def _direction_map(inputs: dict[str, Any]) -> dict[str, str]:
    """Build metric_id -> direction from inputs.clean_metrics and inputs.attack_metrics."""
    out: dict[str, str] = {}
    for lst in (inputs.get("clean_metrics") or [], inputs.get("attack_metrics") or []):
        for m in lst:
            if isinstance(m, dict) and "metric_id" in m:
                out[m["metric_id"]] = m.get("direction", "lower_is_better")
    return out


def _evaluate_gate(predicate: dict[str, Any], value: float | None) -> bool:
    """Return True if predicate passes (value satisfies op threshold)."""
    if value is None:
        return False
    op = predicate.get("op", "==")
    threshold = float(predicate.get("threshold", 0))
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "==":
        return abs(value - threshold) < 1e-12
    if op == "!=":
        return abs(value - threshold) >= 1e-12
    return False


def _robust_minmax_normalize(
    values: list[tuple[str, float]],
    direction: str,
    clip_p5: float,
    clip_p95: float,
    epsilon: float,
) -> dict[str, float]:
    """Clip to [p5, p95], then map to [0,1]. higher_is_better: (x-p5)/(range+eps); lower_is_better: 1 - that."""
    if not values:
        return {}
    vals = [v[1] for v in values]
    p5 = float(min(vals)) if clip_p5 is None else clip_p5
    p95 = float(max(vals)) if clip_p95 is None else clip_p95
    if clip_p5 is not None and clip_p95 is not None:
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        idx_lo = max(0, int((5 / 100) * n) - 1)
        idx_hi = min(n - 1, int((95 / 100) * n))
        p5 = sorted_vals[idx_lo]
        p95 = sorted_vals[idx_hi]
    span = p95 - p5 + epsilon
    out: dict[str, float] = {}
    for key, x in values:
        clipped = max(p5, min(p95, x))
        raw_norm = (clipped - p5) / span
        if direction == "higher_is_better":
            out[key] = raw_norm
        else:
            out[key] = 1.0 - raw_norm
    return out


def _round_dict(obj: Any, decimals: int) -> Any:
    """Recursively round floats in dicts/lists to decimals."""
    if isinstance(obj, dict):
        return {k: _round_dict(v, decimals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_dict(v, decimals) for v in obj]
    if isinstance(obj, float) and not math.isnan(obj) and not math.isinf(obj):
        return round(obj, decimals)
    return obj


def build_coordination_matrix(
    run_dir: Path,
    out_path: Path,
    *,
    policy_root: Path | None = None,
    strict: bool = True,
    matrix_mode: str = "llm_live",
) -> dict[str, Any]:
    """
    Builds CoordinationMatrix v0.1 from a coordination run directory.

    - When matrix_mode is "llm_live" (default): resolves pipeline_mode from run_dir; errors if not llm_live.
    - When matrix_mode is "pack": skips pipeline check; clean metrics can be derived from pack_summary
      baseline rows (injection_id=none) when summary_coord.csv is absent.
    - Loads Phase 1 policies (inputs, column_map, spec) from policy_root (default repo root).
    - Extracts metrics via column_map from source tables; aggregates attacked worst-case.
    - Applies hard gates, robust_minmax normalization, scoring, ranking; writes validated JSON to out_path.

    Returns the matrix dict (after validation, before rounding for write).
    """
    run_dir = Path(run_dir).resolve()
    out_path = Path(out_path).resolve()

    if policy_root is None:
        from labtrust_gym.config import get_repo_root

        policy_root = Path(get_repo_root())

    policy_root = Path(policy_root).resolve()
    from labtrust_gym.config import policy_path

    coord_dir = policy_path(policy_root, "coordination")
    schemas_dir = policy_path(policy_root, "schemas")

    # 1B) pipeline_mode: pack mode skips llm_live check
    if matrix_mode == MATRIX_MODE_PACK:
        pipeline_mode = MATRIX_MODE_PACK
    else:
        pipeline_mode = _get_pipeline_mode_from_run_dir(run_dir, strict=strict)
        _assert_llm_live(pipeline_mode)

    # 1C) Load Phase 1 policies
    inputs_path = coord_dir / _INPUTS_FILENAME
    column_map_path = coord_dir / _COLUMN_MAP_FILENAME
    spec_path = coord_dir / _SPEC_FILENAME
    if not inputs_path.exists():
        raise FileNotFoundError(f"Inputs policy not found: {inputs_path}")
    if not column_map_path.exists():
        raise FileNotFoundError(f"Column map not found: {column_map_path}")
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec not found: {spec_path}")

    inputs_policy = load_policy_file(inputs_path)
    column_map_policy = load_policy_file(column_map_path)
    spec_policy = load_policy_file(spec_path)

    sources = column_map_policy.get("sources") or {}
    clean_sources = sources.get("clean") or [
        "summary_coord.csv",
        "summary_v0.2.csv",
        "results.json",
    ]
    attacked_sources = sources.get("attacked") or [
        "pack_summary.csv",
        "summary_attack.csv",
    ]
    column_map = column_map_policy.get("column_map") or {}

    clean_metric_ids = [m["metric_id"] for m in (inputs_policy.get("clean_metrics") or []) if isinstance(m, dict)]
    attack_metric_ids = [m["metric_id"] for m in (inputs_policy.get("attack_metrics") or []) if isinstance(m, dict)]
    directions = _direction_map(inputs_policy)

    # 1D) Extract clean metrics from canonical source only; in pack mode fallback to pack baseline
    try:
        clean_cells = _extract_clean_metrics(
            run_dir,
            clean_sources,
            column_map,
            clean_metric_ids,
            CLEAN_KEY_COLUMNS,
        )
    except _MetricExtractionError as e:
        raise ValueError(str(e)) from e
    except FileNotFoundError:
        if matrix_mode == MATRIX_MODE_PACK:
            clean_cells = _derive_clean_cells_from_pack(run_dir, clean_metric_ids)
        else:
            raise

    # Attacked: canonical source only; per (scale_id, method_id, injection_id) then aggregate worst-case
    attacked_per_injection = _extract_attacked_metrics(
        run_dir,
        attacked_sources,
        column_map,
        attack_metric_ids,
        ATTACKED_KEY_COLUMNS,
    )
    if not attacked_per_injection and attack_metric_ids:
        # No attacked source found; use empty attacked metrics per clean cell
        attacked_cells = {k: {mid: None for mid in attack_metric_ids} for k in clean_cells}
    else:
        attacked_cells = _aggregate_attacked_worst_case(
            attacked_per_injection,
            attack_metric_ids,
            directions,
        )
        # Align keys with clean: if a (scale_id, method_id) has clean but no attacked, add empty attacked
        for k in clean_cells:
            if k not in attacked_cells:
                attacked_cells[k] = {mid: None for mid in attack_metric_ids}

    # Degradation: simple ratios where same metric exists in clean and attacked
    degradation_cells: dict[tuple[str, str], dict[str, float | None]] = {}
    for k in clean_cells:
        clean_vals = clean_cells[k]
        atk_vals = attacked_cells.get(k) or {}
        deg: dict[str, float | None] = {}
        for mid in clean_metric_ids:
            if mid in atk_vals and clean_vals.get(mid) is not None and atk_vals.get(mid) is not None:
                c, a = clean_vals[mid], atk_vals[mid]
                if c and c != 0:
                    deg[f"deg.{mid}_ratio"] = (a or 0) / c
                else:
                    deg[f"deg.{mid}_ratio"] = None
        degradation_cells[k] = deg
    # Ensure we have degradation keys for schema (can be empty dict per row)
    for k in clean_cells:
        if k not in degradation_cells:
            degradation_cells[k] = {}

    # 1G) Hard gates
    hard_gates = inputs_policy.get("hard_gates") or []
    feasible_clean: dict[tuple[str, str], bool] = {}
    feasible_attacked: dict[tuple[str, str], bool] = {}
    gate_failures: dict[tuple[str, str], list[str]] = {}
    penalties_applied: dict[tuple[str, str], list[tuple[str, float]]] = {}  # (gate_id, amount) per row

    for key in clean_cells:
        feasible_clean[key] = True
        feasible_attacked[key] = True
        gate_failures[key] = []
        penalties_applied[key] = []

        for gate in hard_gates:
            gate_id = gate.get("gate_id", "")
            predicate = gate.get("predicate") or {}
            metric_id = predicate.get("metric_id")
            on_fail = gate.get("on_fail", "disqualify")
            penalty = float(gate.get("penalty", 0))

            # Value from clean or attacked
            if metric_id in clean_metric_ids:
                val = clean_cells.get(key, {}).get(metric_id)
            else:
                val = attacked_cells.get(key, {}).get(metric_id)

            passes = _evaluate_gate(predicate, val)
            if passes:
                continue
            gate_failures[key].append(gate_id)
            if on_fail == "disqualify":
                if metric_id in clean_metric_ids:
                    feasible_clean[key] = False
                else:
                    feasible_attacked[key] = False
            else:
                penalties_applied[key].append((gate_id, penalty))

    # Overall feasible: both clean and attacked feasible
    feasible_overall: dict[tuple[str, str], bool] = {}
    for key in clean_cells:
        feasible_overall[key] = feasible_clean.get(key, True) and feasible_attacked.get(key, True)

    # 1F) Normalization and scoring
    scale_ids = sorted({k[0] for k in clean_cells})
    coord_weights = (spec_policy.get("scores") or {}).get("coordination_score") or {}
    coord_weights = coord_weights.get("weights") or {}
    res_weights = (spec_policy.get("scores") or {}).get("resilience_score") or {}
    res_weights = res_weights.get("weights") or {}
    alpha = (spec_policy.get("scores") or {}).get("overall_score") or {}
    alpha = float(alpha.get("alpha", 0.6))
    norm_config = (
        (inputs_policy.get("clean_metrics") or [{}])[0].get("normalization")
        if inputs_policy.get("clean_metrics")
        else {}
    )
    clip_lo = 5
    clip_hi = 95
    epsilon = 1.0e-9
    if isinstance(norm_config, dict):
        perc = norm_config.get("clip_percentiles") or [5, 95]
        if len(perc) >= 2:
            clip_lo, clip_hi = perc[0], perc[1]
        epsilon = float(norm_config.get("epsilon", 1e-9))

    cq_scores: dict[tuple[str, str], float] = {}
    ar_scores: dict[tuple[str, str], float] = {}
    overall_scores: dict[tuple[str, str], float] = {}

    for scale_id in scale_ids:
        scale_keys = [k for k in clean_cells if k[0] == scale_id]
        # Per-metric normalization within scale
        for mid, direction in directions.items():
            if mid not in clean_metric_ids and mid not in attack_metric_ids:
                continue
            values: list[tuple[str, float]] = []
            for key in scale_keys:
                if mid in clean_metric_ids:
                    v = clean_cells.get(key, {}).get(mid)
                else:
                    v = attacked_cells.get(key, {}).get(mid)
                if v is not None:
                    values.append((f"{key[0]}_{key[1]}", v))
            if not values:
                continue
            sorted_vals = sorted(v[1] for v in values)
            n = len(sorted_vals)
            idx_lo = max(0, min(n - 1, int((clip_lo / 100) * n)))
            idx_hi = max(0, min(n - 1, int((clip_hi / 100) * n)))
            p5, p95 = sorted_vals[idx_lo], sorted_vals[idx_hi]
            span = p95 - p5 + epsilon
            for key in scale_keys:
                if mid in clean_metric_ids:
                    v = clean_cells.get(key, {}).get(mid)
                else:
                    v = attacked_cells.get(key, {}).get(mid)
                if v is None:
                    continue
                clipped = max(p5, min(p95, v))
                raw_norm = (clipped - p5) / span
                norm_val = raw_norm if direction == "higher_is_better" else (1.0 - raw_norm)
                if key not in cq_scores:
                    cq_scores[key] = 0.0
                    ar_scores[key] = 0.0
                if mid in coord_weights:
                    cq_scores[key] += coord_weights[mid] * norm_val
                if mid in res_weights:
                    ar_scores[key] += res_weights[mid] * norm_val

        for key in scale_keys:
            cq = cq_scores.get(key, 0.0)
            ar = ar_scores.get(key, 0.0)
            overall = alpha * cq + (1.0 - alpha) * ar
            total_penalty = sum(p[1] for p in penalties_applied.get(key, []))
            overall = max(0.0, min(1.0, overall - total_penalty))
            overall_scores[key] = overall

    # 1H) Ranking per scale
    tie_breakers = inputs_policy.get("tie_breakers") or []
    _scale_ids_order = scale_ids

    def _rank_key(key: tuple[str, str], score_map: dict[tuple[str, str], float], desc: bool) -> tuple:
        scale_id, method_id = key
        score = score_map.get(key, 0.0)
        # Tie-break by tie_breakers (metric values from clean then attacked), then method_id
        tb_vals = []
        for mid in tie_breakers:
            if mid in clean_cells.get(key, {}):
                tb_vals.append(clean_cells[key].get(mid) is not None and clean_cells[key].get(mid) or 0.0)
            elif mid in attacked_cells.get(key, {}):
                tb_vals.append(attacked_cells[key].get(mid) is not None and attacked_cells[key].get(mid) or 0.0)
            else:
                tb_vals.append(0.0)
        return ((-score if desc else score), tb_vals, method_id)

    coord_rank: dict[tuple[str, str], int] = {}
    res_rank: dict[tuple[str, str], int] = {}
    overall_rank: dict[tuple[str, str], int] = {}

    for scale_id in scale_ids:
        scale_keys = sorted([k for k in clean_cells if k[0] == scale_id], key=lambda k: k[1])
        # Sort by overall_score desc, then tie_breakers, then method_id
        sorted_overall = sorted(
            scale_keys,
            key=lambda k: _rank_key(k, overall_scores, desc=True),
        )
        sorted_coord = sorted(
            scale_keys,
            key=lambda k: _rank_key(k, cq_scores, desc=True),
        )
        sorted_res = sorted(
            scale_keys,
            key=lambda k: _rank_key(k, ar_scores, desc=True),
        )
        for r, k in enumerate(sorted_overall, 1):
            overall_rank[k] = r
        for r, k in enumerate(sorted_coord, 1):
            coord_rank[k] = r
        for r, k in enumerate(sorted_res, 1):
            res_rank[k] = r

    # Pareto: member if not dominated by any other in (cq, ar)
    pareto_member: dict[tuple[str, str], bool] = {}
    for key in clean_cells:
        cq = cq_scores.get(key, 0.0)
        ar = ar_scores.get(key, 0.0)
        scale_id = key[0]
        others = [k for k in clean_cells if k[0] == scale_id and k != key]
        dominated = False
        for o in others:
            cq_o = cq_scores.get(o, 0.0)
            ar_o = ar_scores.get(o, 0.0)
            if cq_o >= cq and ar_o >= ar and (cq_o > cq or ar_o > ar):
                dominated = True
                break
        pareto_member[key] = not dominated

    # Run metadata slot (builder may not have full run_meta per cell from CSV)
    allowed_backends = ["openai_live", "ollama_live"]
    allowed_methods = (inputs_policy.get("scope") or {}).get("coordination_methods") or []

    # Build rows for output schema
    rows_out: list[dict[str, Any]] = []
    for key in sorted(clean_cells.keys(), key=lambda k: (k[0], overall_rank.get(k, 999), k[1])):
        scale_id, method_id = key
        clean_metrics = clean_cells.get(key) or {}
        atk_metrics = attacked_cells.get(key) or {}
        deg_metrics = degradation_cells.get(key) or {}
        # Schema expects metricValueMap: string -> number | null
        clean_map = {k: (v if v is not None else None) for k, v in clean_metrics.items()}
        atk_map = {k: (v if v is not None else None) for k, v in atk_metrics.items()}
        deg_map = {k: (v if v is not None else None) for k, v in deg_metrics.items()}

        reasons = gate_failures.get(key) or []
        row = {
            "scale_id": scale_id,
            "method_id": method_id,
            "run_meta": {
                "pipeline_mode": "llm_live",
                "allow_network": True,
                "llm_backend_id": allowed_backends[0],
                "llm_model_id": None,
                "partner_id": None,
            },
            "metrics": {
                "clean": clean_map,
                "attacked": atk_map,
                "degradation": deg_map,
            },
            "scores": {
                "cq_score": cq_scores.get(key, 0.0),
                "ar_score": ar_scores.get(key, 0.0),
                "penalties": [{"reason": gid, "amount": amt} for gid, amt in penalties_applied.get(key, [])],
            },
            "ranks": {
                "cq_rank": coord_rank.get(key),
                "ar_rank": res_rank.get(key),
                "pareto_member": pareto_member.get(key, False),
            },
            "feasible": {
                "clean": feasible_clean.get(key, True),
                "attacked": feasible_attacked.get(key, True),
                "overall": feasible_overall.get(key, True),
                "reasons": reasons,
            },
        }
        rows_out.append(row)

    # Recommendations per scale
    recommendations_out: list[dict[str, Any]] = []
    for scale_id in scale_ids:
        scale_rows = [r for r in rows_out if r["scale_id"] == scale_id]
        feasible_rows = [r for r in scale_rows if r["feasible"]["overall"]]
        if not feasible_rows:
            ops_first = sec_first = balanced = {
                "method_id": None,
                "cq_score": None,
                "ar_score": None,
            }
        else:
            best_cq = max(feasible_rows, key=lambda r: r["scores"]["cq_score"])
            best_ar = max(feasible_rows, key=lambda r: r["scores"]["ar_score"])
            best_overall = max(
                feasible_rows,
                key=lambda r: r["scores"]["cq_score"] * alpha + r["scores"]["ar_score"] * (1 - alpha),
            )
            ops_first = {
                "method_id": best_cq["method_id"],
                "cq_score": best_cq["scores"]["cq_score"],
                "ar_score": best_cq["scores"]["ar_score"],
            }
            sec_first = {
                "method_id": best_ar["method_id"],
                "cq_score": best_ar["scores"]["cq_score"],
                "ar_score": best_ar["scores"]["ar_score"],
            }
            balanced = {
                "method_id": best_overall["method_id"],
                "cq_score": best_overall["scores"]["cq_score"],
                "ar_score": best_overall["scores"]["ar_score"],
            }
        recommendations_out.append(
            {
                "scale_id": scale_id,
                "ops_first": ops_first,
                "sec_first": sec_first,
                "balanced": balanced,
                "notes": [],
            }
        )

    # Spec and inputs provenance
    spec_rel = f"policy/coordination/{_SPEC_FILENAME}"
    spec_sha = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    inputs_list: list[dict[str, Any]] = []
    for role, path_rel in [
        ("clean_summary", "summary/summary_coord.csv"),
        ("attacked_summary", "summary/pack_summary.csv"),
        ("column_map", f"policy/coordination/{_COLUMN_MAP_FILENAME}"),
        ("matrix_spec", f"policy/coordination/{_SPEC_FILENAME}"),
    ]:
        full = run_dir / path_rel if not path_rel.startswith("policy/") else policy_root / path_rel
        if full.exists():
            inputs_list.append(
                {
                    "path": path_rel,
                    "sha256": hashlib.sha256(full.read_bytes()).hexdigest(),
                    "role": role,
                }
            )
    if not inputs_list:
        inputs_list.append({"path": spec_rel, "sha256": spec_sha, "role": "matrix_spec"})

    policy_fingerprint = hashlib.sha256(
        json.dumps({"inputs": inputs_policy, "spec": spec_policy}, sort_keys=True).encode()
    ).hexdigest()

    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    matrix = {
        "version": "0.1",
        "kind": "coordination_matrix",
        "generated_at": generated_at,
        "policy_fingerprint": f"sha256:{policy_fingerprint}",
        "spec": {
            "path": spec_rel,
            "sha256": f"sha256:{spec_sha}",
            "scope": {
                "pipeline_mode": "llm_live",
                "allow_network": True,
                "allowed_llm_backends": allowed_backends,
                "allowed_methods": allowed_methods,
            },
        },
        "inputs": inputs_list,
        "scales": [{"scale_id": sid, "meta": {}} for sid in scale_ids],
        "rows": rows_out,
        "recommendations": recommendations_out,
    }

    # 1I) Validate against schema
    schema_path = schemas_dir / _OUTPUT_SCHEMA_FILENAME
    if schema_path.exists():
        schema = load_json(schema_path)
        try:
            validate_against_schema(matrix, schema, out_path)
        except PolicyLoadError as e:
            raise ValueError(f"Matrix output failed schema validation: {e}") from e

    # Write with deterministic rounding (at write time per spec)
    decimals = (spec_policy.get("determinism") or {}).get("float_rounding_decimals", 6)
    matrix_rounded = _round_dict(matrix, decimals)
    write_coordination_matrix(matrix_rounded, out_path)
    return matrix


def write_coordination_matrix(matrix: dict[str, Any], out_path: Path) -> None:
    """
    Writes the matrix as JSON deterministically (stable key ordering, stable float rounding).

    Uses sort_keys=True and the same float rounding as in build (float_rounding_decimals from spec).
    """
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(matrix, sort_keys=True, indent=2)
    out_path.write_text(json_str, encoding="utf-8")
