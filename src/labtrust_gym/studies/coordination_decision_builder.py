"""
Coordination decision builder: given a run directory and selection policy,
produce COORDINATION_DECISION.v0.1.json (machine-readable) and
COORDINATION_DECISION.md (human-readable rationale). Optimal method selection
is an artifact, not a vibe. Output is deterministic and schema-validated.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from labtrust_gym.config import policy_path
from labtrust_gym.policy.loader import (
    get_partner_overlay_dir,
    load_yaml,
    load_json,
    validate_against_schema,
)

SCHEMA_VERSION = "0.1"
KIND = "coordination_decision"
DECISION_FILENAME_JSON = "COORDINATION_DECISION.v0.1.json"
DECISION_FILENAME_MD = "COORDINATION_DECISION.md"
SELECTION_POLICY_FILENAME = "coordination_selection_policy.v0.1.yaml"
SCHEMA_FILENAME = "coordination_decision.v0.1.schema.json"

# Summary sources (first found wins)
SUMMARY_CANDIDATES = [
    "pack_summary.csv",
    "summary/summary_coord.csv",
]


def check_security_gate(run_dir: Path) -> tuple[bool, list[dict[str, str]]]:
    """
    Check pack_gate.md under run_dir. Return (passed, failed_cells).
    passed is False if any cell has verdict FAIL. failed_cells is a list of
    {"scale_id", "method_id", "injection_id"} for each FAIL cell.
    If pack_gate.md is missing, return (True, []).
    """
    run_dir = Path(run_dir).resolve()
    gate_path = run_dir / "pack_gate.md"
    if not gate_path.is_file():
        return (True, [])
    text = gate_path.read_text(encoding="utf-8")
    failed: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("|") or "|--" in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 4 and parts[0].lower() != "scale_id":
            scale_id = parts[0]
            method_id = parts[1]
            injection_id = parts[2]
            verdict = (parts[3] or "").strip().upper()
            if verdict == "FAIL":
                failed.append(
                    {
                        "scale_id": scale_id,
                        "method_id": method_id,
                        "injection_id": injection_id,
                    }
                )
    return (len(failed) == 0, failed)


def _find_summary_csv(run_dir: Path) -> tuple[Path, str] | None:
    """Return (path, label) for first existing summary CSV under run_dir."""
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_dir():
        return None
    for name in SUMMARY_CANDIDATES:
        p = run_dir / name
        if p.is_file():
            return (p, name)
    return None


def _load_summary_rows(csv_path: Path) -> list[dict[str, Any]]:
    """Load CSV and normalize numeric columns; return list of row dicts."""
    rows: list[dict[str, Any]] = []
    numeric_keys = {
        "perf.throughput",
        "perf.p95_tat",
        "safety.violations_total",
        "safety.blocks_total",
        "sec.attack_success_rate",
        "sec.detection_latency_steps",
        "sec.containment_time_steps",
        "robustness.resilience_score",
        "cost.estimated_cost_usd",
        "cost.total_tokens",
    }
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            out = dict(r)
            for k in list(out.keys()):
                v = out[k]
                if v == "" or v is None:
                    out[k] = None
                    continue
                if k in numeric_keys:
                    try:
                        out[k] = (
                            float(v)
                            if "." in str(v) or "e" in str(v).lower()
                            else int(v)
                        )
                    except (ValueError, TypeError):
                        out[k] = None
            rows.append(out)
    return rows


def _aggregated_for_cell(
    rows: list[dict[str, Any]],
    scale_id: str,
    method_id: str,
    policy_constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build aggregated metrics for (scale_id, method_id): baseline metrics and
    attack-aggregated metrics (max/mean) per policy constraint aggregation.
    """
    cell_rows = [
        r
        for r in rows
        if (r.get("scale_id") or "").strip() == scale_id
        and (r.get("method_id") or "").strip() == method_id
    ]
    baseline_rows = [
        r
        for r in cell_rows
        if (r.get("injection_id") or "").strip().lower() in ("none", "")
    ]
    attack_rows = [
        r
        for r in cell_rows
        if (r.get("injection_id") or "").strip().lower() not in ("none", "")
    ]

    out: dict[str, Any] = {
        "baseline": {},
        "max_over_attacks": {},
        "mean_over_attacks": {},
    }
    metric_keys = set()
    for r in cell_rows:
        metric_keys.update(
            k
            for k in r
            if k not in ("scale_id", "method_id", "injection_id", "risk_id")
        )
    for k in metric_keys:
        if k in ("scale_id", "method_id", "injection_id", "risk_id"):
            continue
        base_vals = [r[k] for r in baseline_rows if r.get(k) is not None]
        out["baseline"][k] = (
            base_vals[0]
            if len(base_vals) == 1
            else (base_vals[0] if base_vals else None)
        )
        attack_vals = [r[k] for r in attack_rows if r.get(k) is not None]
        if attack_vals:
            try:
                nums = [float(x) for x in attack_vals]
                out["max_over_attacks"][k] = max(nums)
                out["mean_over_attacks"][k] = sum(nums) / len(nums)
            except (TypeError, ValueError):
                out["max_over_attacks"][k] = None
                out["mean_over_attacks"][k] = None
        else:
            out["max_over_attacks"][k] = None
            out["mean_over_attacks"][k] = None
    return out


def _value_for_constraint(
    agg: dict[str, Any],
    metric_key: str,
    aggregation: str,
) -> float | None:
    """Resolve metric value for constraint check. Return None if missing."""
    if aggregation == "baseline_only":
        return (agg.get("baseline") or {}).get(metric_key)
    if aggregation == "max_over_attacks":
        return (agg.get("max_over_attacks") or {}).get(metric_key)
    if aggregation == "mean_over_attacks":
        return (agg.get("mean_over_attacks") or {}).get(metric_key)
    return None


def _check_constraint(
    value: float | None,
    operator: str,
    threshold: float,
    allow_missing: bool,
) -> tuple[bool, str | None]:
    """Return (passes, failure_reason)."""
    if value is None:
        if allow_missing:
            return (True, None)
        return (False, "metric missing")
    if operator == "<=":
        return (True, None) if value <= threshold else (False, f"{value} > {threshold}")
    if operator == ">=":
        return (True, None) if value >= threshold else (False, f"{value} < {threshold}")
    if operator == "<":
        return (True, None) if value < threshold else (False, f"{value} >= {threshold}")
    if operator == ">":
        return (True, None) if value > threshold else (False, f"{value} <= {threshold}")
    if operator == "==":
        return (
            (True, None) if value == threshold else (False, f"{value} != {threshold}")
        )
    return (True, None)


def _overall_score_for_ranking(
    agg: dict[str, Any],
    objective: dict[str, Any],
) -> float:
    """
    Compute a single number for ranking (higher better). Uses resilience_score
    when available; else fallback: throughput (higher better) minus normalized violations.
    """
    base = agg.get("baseline") or {}
    res = base.get("robustness.resilience_score")
    if res is not None:
        return float(res)
    throughput = base.get("perf.throughput")
    violations = base.get("safety.violations_total")
    if throughput is not None and violations is not None:
        return float(throughput) - float(violations) / 100.0
    if throughput is not None:
        return float(throughput)
    if violations is not None:
        return -float(violations) / 100.0
    return 0.0


def build_decision(
    run_dir: Path,
    policy_root: Path,
    partner_id: str | None = None,
) -> dict[str, Any]:
    """
    Load summary from run_dir, load selection policy from policy_root (or partner
    overlay when partner_id is set), compute admissible methods per scale, rank
    by objective, and build the decision artifact. Deterministic given same
    run_dir contents and policy.
    """
    run_dir = Path(run_dir).resolve()
    policy_root = Path(policy_root).resolve()
    summary_info = _find_summary_csv(run_dir)
    if not summary_info:
        raise FileNotFoundError(
            f"No summary CSV found under {run_dir}. Expected one of: {SUMMARY_CANDIDATES}"
        )
    csv_path, summary_source = summary_info
    rows = _load_summary_rows(csv_path)
    if not rows:
        raise ValueError(f"Summary CSV is empty: {csv_path}")

    # Security gate: if this run is from coordination security pack, check pack_gate.md for any FAIL
    security_gate_passed = True
    security_gate_failed_cells: list[dict[str, str]] = []
    if summary_source == "pack_summary.csv":
        security_gate_passed, security_gate_failed_cells = check_security_gate(run_dir)

    # Optionally enrich pack_summary rows with resilience_score from resilience_scoring policy
    has_resilience = any(r.get("robustness.resilience_score") is not None for r in rows)
    if not has_resilience and "pack_summary" in summary_source:
        try:
            from labtrust_gym.studies.resilience_scoring import (
                load_resilience_scoring_policy,
                enrich_pack_rows_with_resilience,
            )

            resilience_policy_path = policy_path(
                policy_root, "coordination", "resilience_scoring.v0.1.yaml"
            )
            if resilience_policy_path.is_file():
                policy_res = load_resilience_scoring_policy(resilience_policy_path)
                enrich_pack_rows_with_resilience(rows, policy=policy_res)
        except Exception:
            pass

    # Partner overlay may override selection policy
    selection_policy_path = policy_path(policy_root, "coordination", SELECTION_POLICY_FILENAME)
    if partner_id:
        overlay_path = (
            get_partner_overlay_dir(policy_root, partner_id)
            / "coordination"
            / SELECTION_POLICY_FILENAME
        )
        if overlay_path.is_file():
            selection_policy_path = overlay_path
    if not selection_policy_path.is_file():
        raise FileNotFoundError(f"Selection policy not found: {selection_policy_path}")
    policy = load_yaml(selection_policy_path)
    policy_id = policy.get("policy_id") or "coordination_selection_v0.1"
    constraints: list[dict[str, Any]] = policy.get("constraints") or []
    objective: dict[str, Any] = policy.get("objective") or {
        "type": "maximize_overall_score"
    }
    per_scale_rules: dict[str, Any] = policy.get("per_scale_rules") or {}

    scale_ids = sorted(
        {
            (r.get("scale_id") or "").strip()
            for r in rows
            if (r.get("scale_id") or "").strip()
        }
    )
    if not scale_ids:
        scale_ids = ["default"]

    scale_decisions: list[dict[str, Any]] = []
    all_violated: list[dict[str, Any]] = []
    any_no_admissible = False

    for scale_id in scale_ids:
        method_ids = sorted(
            {
                (r.get("method_id") or "").strip()
                for r in rows
                if (r.get("scale_id") or "").strip() == scale_id
                and (r.get("method_id") or "").strip()
            }
        )
        admissible: list[dict[str, Any]] = []
        disqualified: list[dict[str, Any]] = []

        for method_id in method_ids:
            agg = _aggregated_for_cell(rows, scale_id, method_id, constraints)
            violated_list: list[dict[str, Any]] = []
            for c in constraints:
                cid = c.get("constraint_id") or ""
                metric_key = c.get("metric_key") or ""
                operator = c.get("operator") or "<="
                threshold = float(c.get("threshold") or 0)
                aggregation = c.get("aggregation") or "baseline_only"
                allow_missing = c.get("allow_missing") or False
                value = _value_for_constraint(agg, metric_key, aggregation)
                if (
                    metric_key == "cost.estimated_cost_usd"
                    and value is None
                    and allow_missing
                ):
                    value = 0.0
                passes, _ = _check_constraint(value, operator, threshold, allow_missing)
                if not passes:
                    violated_list.append(
                        {
                            "constraint_id": cid,
                            "metric_key": metric_key,
                            "threshold": threshold,
                            "actual": value,
                            "description": c.get("description") or "",
                        }
                    )
            if violated_list:
                disqualified.append(
                    {
                        "method_id": method_id,
                        "reason": "; ".join(
                            f"{v['constraint_id']}={v['actual']}" for v in violated_list
                        ),
                        "violated_constraints": violated_list,
                    }
                )
                for v in violated_list:
                    all_violated.append(v)
            else:
                score = _overall_score_for_ranking(agg, objective)
                admissible.append(
                    {"method_id": method_id, "overall_score": score, "rank": None}
                )

        admissible.sort(key=lambda x: (-(x["overall_score"] or 0), x["method_id"]))
        for i, a in enumerate(admissible, start=1):
            a["rank"] = i
        chosen = admissible[0] if admissible else None
        scale_decisions.append(
            {
                "scale_id": scale_id,
                "chosen_method_id": chosen["method_id"] if chosen else None,
                "overall_score": chosen.get("overall_score") if chosen else None,
                "rank": chosen.get("rank") if chosen else None,
                "admissible_methods": admissible,
                "disqualified": disqualified,
            }
        )
        if not admissible:
            any_no_admissible = True

    # Security gate takes precedence: if any pack cell failed the gate, verdict is security_gate_failed
    if not security_gate_passed:
        verdict = "security_gate_failed"
    else:
        verdict = "admissible" if not any_no_admissible else "no_admissible_method"
    recommended_actions = (
        [
            "Tighten defenses or add safe fallback for failing methods.",
            "Relax cost or violation constraints in selection policy if acceptable.",
            "Add or re-run cells for missing baseline (injection_id=none) or attack coverage.",
        ]
        if any_no_admissible
        else []
    )

    chosen_evidence = "No method chosen (no admissible method)."
    rejected_rationale = "All methods disqualified by constraint failure."
    residual = "Residual risk: constraints not met for at least one scale."
    if not security_gate_passed:
        chosen_evidence = "No method chosen (security gate failed)."
        rejected_rationale = (
            "One or more coordination security pack cells failed the gate (see security_gate_failed.failed_cells)."
        )
        residual = "Residual risk: security/safety gate failed; do not deploy until gate passes."
    elif not any_no_admissible:
        chosen_list = [
            sd["chosen_method_id"]
            for sd in scale_decisions
            if sd.get("chosen_method_id")
        ]
        chosen_evidence = (
            "Chosen method(s) for deployment: " + ", ".join(chosen_list) + "."
        )
        rejected_rationale = (
            "Rejected others: "
            + "; ".join(
                f"{d['method_id']}: {d['reason']}"
                for sd in scale_decisions
                for d in sd.get("disqualified") or []
            )
            or "None (all admissible or only one method)."
        )
        residual = (
            "Residual risk: see per-scale disqualified methods and policy constraints."
        )

    risk_register_linkage = {
        "chosen_method_evidence": chosen_evidence,
        "rejected_others_rationale": rejected_rationale,
        "residual_risk_statement": residual,
    }

    decision: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "policy_id": policy_id,
        "policy_path": str(policy_path),
        "summary_source": summary_source,
        "verdict": verdict,
        "scale_decisions": scale_decisions,
        "risk_register_linkage": risk_register_linkage,
    }
    if not security_gate_passed:
        decision["security_gate_failed"] = {"failed_cells": security_gate_failed_cells}
    if any_no_admissible:
        decision["no_admissible_method"] = {
            "violated_constraints": [
                {
                    k: v
                    for k, v in vd.items()
                    if k
                    in (
                        "constraint_id",
                        "metric_key",
                        "threshold",
                        "actual",
                        "description",
                    )
                }
                for vd in all_violated[:50]
            ],
            "recommended_actions": recommended_actions,
        }
    return decision


def write_decision_artifact(
    decision: dict[str, Any],
    out_dir: Path,
    policy_root: Path,
) -> tuple[Path, Path]:
    """
    Write COORDINATION_DECISION.v0.1.json (schema-validated) and
    COORDINATION_DECISION.md to out_dir. Return (json_path, md_path).
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / DECISION_FILENAME_JSON
    md_path = out_dir / DECISION_FILENAME_MD

    schemas_dir = policy_path(policy_root, "schemas")
    schema_path = schemas_dir / SCHEMA_FILENAME
    if schema_path.is_file():
        schema = load_json(schema_path)
        validate_against_schema(decision, schema, path=json_path)
    json_path.write_text(_json_dumps(decision), encoding="utf-8")

    md_lines = _render_decision_md(decision)
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return (json_path, md_path)


def _json_dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=2)


def _render_decision_md(decision: dict[str, Any]) -> list[str]:
    """Human-readable rationale: top candidates, disqualifications, trade-offs."""
    lines = [
        "# Coordination Decision (artifact)",
        "",
        f"**Verdict:** {decision.get('verdict', '')}",
        f"**Generated:** {decision.get('generated_at', '')}",
        f"**Run dir:** {decision.get('run_dir', '')}",
        f"**Policy:** {decision.get('policy_id', '')}",
        "",
        "## Scale decisions",
        "",
    ]
    for sd in decision.get("scale_decisions") or []:
        scale_id = sd.get("scale_id") or ""
        chosen = sd.get("chosen_method_id")
        lines.append(f"### {scale_id}")
        lines.append("")
        if chosen:
            lines.append(f"- **Chosen:** {chosen}")
            lines.append(f"- **Overall score:** {sd.get('overall_score')}")
        else:
            lines.append("- **Chosen:** (no admissible method)")
        adm = sd.get("admissible_methods") or []
        if adm:
            lines.append(
                "- **Top candidates:** "
                + ", ".join(
                    f"{a['method_id']} (score={a.get('overall_score')}, rank={a.get('rank')})"
                    for a in adm[:5]
                )
            )
        lines.append("")
        disq = sd.get("disqualified") or []
        if disq:
            lines.append("**Disqualified:**")
            for d in disq:
                lines.append(f"- {d.get('method_id')}: {d.get('reason')}")
            lines.append("")
    lines.append("## Risk register linkage")
    lines.append("")
    rr = decision.get("risk_register_linkage") or {}
    lines.append(
        f"- **Chosen method evidence:** {rr.get('chosen_method_evidence', '')}"
    )
    lines.append(
        f"- **Rejected others rationale:** {rr.get('rejected_others_rationale', '')}"
    )
    lines.append(
        f"- **Residual risk statement:** {rr.get('residual_risk_statement', '')}"
    )
    lines.append("")
    if decision.get("verdict") == "security_gate_failed":
        sgf = decision.get("security_gate_failed") or {}
        lines.append("## Security gate failed")
        lines.append("")
        lines.append("One or more coordination security pack cells failed the gate. Do not deploy until resolved.")
        for cell in (sgf.get("failed_cells") or [])[:30]:
            lines.append(
                f"- {cell.get('scale_id')} / {cell.get('method_id')} / {cell.get('injection_id')}"
            )
        lines.append("")
    if decision.get("verdict") == "no_admissible_method":
        no_adm = decision.get("no_admissible_method") or {}
        lines.append("## No admissible method")
        lines.append("")
        lines.append("**Violated constraints (sample):**")
        for v in (no_adm.get("violated_constraints") or [])[:20]:
            lines.append(
                f"- {v.get('constraint_id')}: {v.get('metric_key')} actual={v.get('actual')} threshold={v.get('threshold')}"
            )
        lines.append("")
        lines.append("**Recommended actions:**")
        for a in no_adm.get("recommended_actions") or []:
            lines.append(f"- {a}")
        lines.append("")
    return lines


def run_recommend_coordination_method(
    run_dir: Path,
    out_dir: Path,
    policy_root: Path,
    partner_id: str | None = None,
) -> dict[str, Any]:
    """
    Build decision from run_dir, write JSON and MD to out_dir, return decision dict.
    When partner_id is set, selection policy is loaded from partner overlay if present.
    """
    decision = build_decision(run_dir, policy_root, partner_id=partner_id)
    json_path, md_path = write_decision_artifact(decision, out_dir, policy_root)
    return {"decision": decision, "json_path": json_path, "md_path": md_path}
