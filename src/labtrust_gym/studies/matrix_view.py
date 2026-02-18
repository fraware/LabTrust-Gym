"""
Matrix view: method-risk coverage and pack (method x scale x injection) as table/csv/markdown.

Used by CLI show-method-risk-matrix and show-pack-matrix, and by docs generation.
Scale taxonomy (scale_id, num_agents_total) is included so the matrix is interpretable
by number of agents (hospital lab taxonomy).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import load_yaml


def _load_scale_configs_yaml(repo_root: Path) -> list[dict[str, Any]]:
    """Load scale_configs.v0.1.yaml; return list of config dicts (id, num_agents_total, name, description)."""
    path = repo_root / "policy" / "coordination" / "scale_configs.v0.1.yaml"
    if not path.is_file():
        return []
    data = load_yaml(path)
    root = data.get("scale_configs") or data
    configs = root.get("configs") if isinstance(root, dict) else []
    if not isinstance(configs, list):
        return []
    return [c for c in configs if isinstance(c, dict) and c.get("id")]


def get_scale_taxonomy(repo_root: Path) -> list[dict[str, Any]]:
    """
    Return scale taxonomy: list of {scale_id, num_agents_total, name, description}.
    Used for hospital lab matrix interpretation (matrix depends on number of agents).
    """
    configs = _load_scale_configs_yaml(repo_root)
    return [
        {
            "scale_id": str(c.get("id", "")),
            "num_agents_total": int(c.get("num_agents_total", 0)),
            "name": str(c.get("name", c.get("id", ""))),
            "description": str(c.get("description", "")),
        }
        for c in configs
    ]


def format_method_risk_matrix(
    matrix: dict[str, Any],
    output_format: str = "table",
) -> str:
    """
    Format method-risk matrix (from load_method_risk_matrix) as table, csv, or markdown.
    output_format: "table" (ASCII), "csv", "markdown".
    """
    cells = matrix.get("cells") or []
    if not cells:
        header = f"# Method-risk matrix: {matrix.get('matrix_id', '')} v{matrix.get('version', '')}\n(no cells)\n"
        return header if output_format == "markdown" else "(no cells)\n"

    rows = []
    for c in cells:
        if not isinstance(c, dict):
            continue
        rows.append({
            "method_id": str(c.get("method_id", "")),
            "risk_id": str(c.get("risk_id", "")),
            "coverage": str(c.get("coverage", "")),
            "required_bench": "yes" if c.get("required_bench") else "no",
            "rationale": str(c.get("rationale", ""))[:80],
        })

    if output_format == "csv":
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["method_id", "risk_id", "coverage", "required_bench", "rationale"])
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue()

    if output_format == "markdown":
        lines = [
            f"# Method-risk matrix: {matrix.get('matrix_id', '')} v{matrix.get('version', '')}",
            "",
            "| method_id | risk_id | coverage | required_bench | rationale |",
            "|-----------|---------|----------|----------------|-----------|",
        ]
        for r in rows:
            lines.append(f"| {r['method_id']} | {r['risk_id']} | {r['coverage']} | {r['required_bench']} | {r['rationale']} |")
        return "\n".join(lines)

    # table: simple ASCII
    col_w = {"method_id": max(8, max((len(r["method_id"]) for r in rows), default=0)),
             "risk_id": max(8, max((len(r["risk_id"]) for r in rows), default=0)),
             "coverage": 10, "required_bench": 8, "rationale": 40}
    sep = "  "
    head = sep.join([
        f"{'method_id':<{col_w['method_id']}}",
        f"{'risk_id':<{col_w['risk_id']}}",
        f"{'coverage':<{col_w['coverage']}}",
        f"{'req_bench':<{col_w['required_bench']}}",
        f"{'rationale':<{col_w['rationale']}}",
    ])
    lines = [head, "-" * len(head)]
    for r in rows:
        rshort = (r["rationale"][: col_w["rationale"] - 2] + "..") if len(r["rationale"]) > col_w["rationale"] else r["rationale"]
        lines.append(sep.join([
            f"{r['method_id']:<{col_w['method_id']}}",
            f"{r['risk_id']:<{col_w['risk_id']}}",
            f"{r['coverage']:<{col_w['coverage']}}",
            f"{r['required_bench']:<{col_w['required_bench']}}",
            f"{rshort:<{col_w['rationale']}}",
        ]))
    return "\n".join(lines)


def _resolve_pack_methods_scales_injections(
    repo_root: Path,
    pack_config: dict[str, Any],
    matrix_preset: str | None,
) -> tuple[list[str], list[str], list[str]]:
    """Resolve method_ids, scale_ids, injection_ids from pack config and optional preset."""
    if matrix_preset and (pack_config.get("matrix_presets") or {}).get(matrix_preset):
        preset = pack_config["matrix_presets"][matrix_preset]
        method_ids = list(preset.get("method_ids") or [])
        scale_ids = list(preset.get("scale_ids") or [])
        injection_ids = list(preset.get("injection_ids") or [])
        if method_ids or scale_ids or injection_ids:
            if not scale_ids:
                scale_ids = list((pack_config.get("scale_ids") or {}).get("default") or ["small_smoke", "medium_stress_signed_bus"])
            return method_ids, scale_ids, injection_ids
    method_ids = list((pack_config.get("method_ids") or {}).get("default") or [])
    scale_ids = list((pack_config.get("scale_ids") or {}).get("default") or ["small_smoke", "medium_stress_signed_bus"])
    injection_ids = list((pack_config.get("injection_ids") or {}).get("default") or [])
    return method_ids, scale_ids, injection_ids


def _injection_ids_policy(repo_root: Path) -> list[str]:
    """Resolve injection_ids when preset uses 'policy' (all from injections.v0.2 + registry)."""
    from labtrust_gym.studies.coordination_security_pack import (
        _get_injection_ids_from_policy_and_registry,
    )
    return _get_injection_ids_from_policy_and_registry(repo_root)


def get_pack_matrix_cells(
    repo_root: Path,
    matrix_preset: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (cells, scale_taxonomy). cells = list of {method_id, scale_id, injection_id};
    scale_taxonomy = get_scale_taxonomy(repo_root).
    """
    path = repo_root / "policy" / "coordination" / "coordination_security_pack.v0.1.yaml"
    pack_config = load_yaml(path) if path.is_file() else {}
    method_ids, scale_ids, injection_ids = _resolve_pack_methods_scales_injections(
        repo_root, pack_config, matrix_preset
    )
    if not method_ids:
        method_ids = ["kernel_auction_whca_shielded", "llm_repair_over_kernel_whca", "llm_local_decider_signed_bus"]
    if not scale_ids:
        scale_ids = ["small_smoke", "medium_stress_signed_bus"]
    policy_injections = (
        injection_ids == "policy"
        or (
            isinstance(injection_ids, list)
            and len(injection_ids) == 1
            and injection_ids[0] == "policy"
        )
    )
    if policy_injections:
        injection_ids = _injection_ids_policy(repo_root)
    if not injection_ids:
        injection_ids = ["none", "INJ-ID-SPOOF-001", "INJ-COMMS-POISON-001", "INJ-COORD-PROMPT-INJECT-001"]
    cells = []
    for mid in method_ids:
        for sid in scale_ids:
            for iid in injection_ids:
                cells.append({"method_id": mid, "scale_id": sid, "injection_id": iid})
    taxonomy = get_scale_taxonomy(repo_root)
    return cells, taxonomy


def format_pack_matrix(
    repo_root: Path,
    matrix_preset: str | None = None,
    output_format: str = "table",
    include_scale_taxonomy: bool = True,
) -> str:
    """
    Format pack matrix (method x scale x injection) as table, csv, or markdown.
    If include_scale_taxonomy, prepend scale taxonomy (scale_id, num_agents_total) for hospital lab.
    """
    cells, taxonomy = get_pack_matrix_cells(repo_root, matrix_preset)
    scale_agents = {t["scale_id"]: t["num_agents_total"] for t in taxonomy}

    out_lines: list[str] = []
    if include_scale_taxonomy and taxonomy and output_format == "markdown":
        out_lines.append("## Scale taxonomy (number of agents)")
        out_lines.append("")
        out_lines.append("| scale_id | num_agents_total | name |")
        out_lines.append("|----------|------------------|------|")
        for t in taxonomy:
            out_lines.append(f"| {t['scale_id']} | {t['num_agents_total']} | {t['name']} |")
        out_lines.append("")
        out_lines.append("The pack matrix below depends on scale: each (method, scale, injection) cell is run at that scale's agent count.")
        out_lines.append("")

    if output_format == "markdown":
        out_lines.append("## Pack matrix (method x scale x injection)")
        out_lines.append("")
        out_lines.append("| method_id | scale_id | num_agents | injection_id |")
        out_lines.append("|-----------|----------|------------|--------------|")
        for c in cells:
            n = scale_agents.get(c["scale_id"], "")
            out_lines.append(f"| {c['method_id']} | {c['scale_id']} | {n} | {c['injection_id']} |")
        return "\n".join(out_lines)

    if output_format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["method_id", "scale_id", "num_agents_total", "injection_id"])
        w.writeheader()
        for c in cells:
            row = {"method_id": c["method_id"], "scale_id": c["scale_id"], "injection_id": c["injection_id"]}
            row["num_agents_total"] = scale_agents.get(c["scale_id"], "")
            w.writerow(row)
        return buf.getvalue()

    # table
    if include_scale_taxonomy and taxonomy:
        out_lines.append("Scale taxonomy (num_agents_total):")
        for t in taxonomy:
            out_lines.append(f"  {t['scale_id']}: {t['num_agents_total']} agents")
        out_lines.append("")
    out_lines.append("method_id  scale_id  injection_id")
    out_lines.append("-" * 60)
    for c in cells[:50]:  # limit for terminal
        out_lines.append(f"{c['method_id']}  {c['scale_id']}  {c['injection_id']}")
    if len(cells) > 50:
        out_lines.append(f"... and {len(cells) - 50} more cells")
    return "\n".join(out_lines)


def format_pack_results_from_run(
    run_dir: Path,
    output_format: str = "markdown",
) -> str:
    """
    Format the result matrix from a completed pack run (real results, no placeholders).
    Reads pack_summary.csv and SECURITY/coordination_risk_matrix.csv/.md from run_dir.
    output_format: "markdown" (prefer coordination_risk_matrix.md), "table", "csv".
    """
    run_dir = Path(run_dir)
    risk_md = run_dir / "SECURITY" / "coordination_risk_matrix.md"
    risk_csv = run_dir / "SECURITY" / "coordination_risk_matrix.csv"
    pack_csv = run_dir / "pack_summary.csv"

    if output_format == "markdown" and risk_md.is_file():
        return risk_md.read_text(encoding="utf-8")

    # Load from CSV (risk matrix has verdict; pack_summary has full metrics)
    if risk_csv.is_file():
        path = risk_csv
    elif pack_csv.is_file():
        path = pack_csv
    else:
        return f"(No result matrix found under {run_dir}; run labtrust run-coordination-security-pack --out <dir> first.)"

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return "(Empty result matrix.)"
        fieldnames = list(reader.fieldnames or [])

    if output_format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    # table: compact view with key columns
    key_cols = [c for c in ["method_id", "scale_id", "injection_id", "verdict", "sec.attack_success_rate"] if c in fieldnames]
    if not key_cols:
        key_cols = fieldnames[:6]
    col_w = {k: max(len(k), max((len(str(r.get(k, ""))) for r in rows), default=0)) for k in key_cols}
    sep = "  "
    head = sep.join(f"{k:<{col_w[k]}}" for k in key_cols)
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(sep.join(f"{str(r.get(k, '')):<{col_w[k]}}" for k in key_cols))
    return "\n".join(lines)
