"""
Lab coordination report builder: bundle summarize + recommend and write
LAB_COORDINATION_REPORT.md for hospital lab stakeholders.

Takes a directory that already contains pack output (pack_summary.csv,
pack_gate.md, SECURITY/coordination_risk_matrix.*), runs summarize-coordination
and recommend-coordination-method, then writes a single lab report markdown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LAB_REPORT_FILENAME = "LAB_COORDINATION_REPORT.md"
SECURITY_REPORT_FILENAME = "SECURITY_REPORT.md"
SAFETY_CASE_REPORT_FILENAME = "SAFETY_CASE_REPORT.md"


def _ensure_summarize(pack_dir: Path, out_dir: Path, policy_root: Path) -> None:
    """Run summarize-coordination if summary artifacts are missing or refresh them."""
    from labtrust_gym.studies.coordination_summarizer import run_summarize

    run_summarize(in_dir=pack_dir, out_dir=out_dir, repo_root=policy_root)


def _ensure_recommend(
    pack_dir: Path,
    out_dir: Path,
    policy_root: Path,
    partner_id: str | None = None,
) -> dict[str, Any]:
    """Run recommend-coordination-method and return decision dict."""
    from labtrust_gym.studies.coordination_decision_builder import run_recommend_coordination_method

    return run_recommend_coordination_method(
        run_dir=pack_dir,
        out_dir=out_dir,
        policy_root=policy_root,
        partner_id=partner_id,
    )


def _read_snippet(path: Path, max_lines: int = 25) -> list[str]:
    """Read file and return first max_lines as list of strings; empty if missing."""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        return lines[:max_lines]
    except (OSError, UnicodeDecodeError):
        return []


def _write_security_report(pack_dir: Path, out_dir: Path) -> bool:
    """Write SECURITY_REPORT.md from pack output. Return True if written."""
    from labtrust_gym.studies.coordination_decision_builder import check_security_gate

    gate_path = pack_dir / "pack_gate.md"
    if not gate_path.is_file():
        return False
    passed, failed_cells = check_security_gate(pack_dir)
    security_dir = pack_dir / "SECURITY"
    lines = [
        "# Security report",
        "",
        "Summary of the coordination security pack run and gate result.",
        "",
        "## Gate result",
        "",
        "**Overall:** " + ("PASS" if passed else "FAIL") + ".",
        "",
    ]
    if not passed:
        lines.append("The following cells failed the gate:")
        lines.append("")
        for c in failed_cells[:50]:
            lines.append(f"- {c.get('scale_id')} / {c.get('method_id')} / {c.get('injection_id')}")
        lines.append("")
    rel_gate = "pack_gate.md"
    rel_risk = "SECURITY/coordination_risk_matrix.md"
    if out_dir != pack_dir:
        try:
            rel_gate = str(gate_path.relative_to(out_dir))
        except ValueError:
            pass
        if security_dir.is_dir():
            try:
                rel_risk = str((security_dir / "coordination_risk_matrix.md").relative_to(out_dir))
            except ValueError:
                pass
    lines.extend([
        "## Artifacts",
        "",
        f"- [pack_gate.md]({rel_gate}) – per-cell verdict (PASS / FAIL / not_supported).",
        f"- [SECURITY/coordination_risk_matrix.md]({rel_risk}) – method x injection outcomes (when present).",
        "",
        "This report ties the coordination decision and risk register to the security pack evidence.",
        "",
    ])
    report_path = out_dir / SECURITY_REPORT_FILENAME
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return True


def _write_safety_case_report(out_dir: Path, pack_dir: Path) -> bool:
    """Write SAFETY_CASE_REPORT.md when SAFETY_CASE/safety_case.json exists. Return True if written."""
    for base in (out_dir, pack_dir):
        safety_json = base / "SAFETY_CASE" / "safety_case.json"
        if not safety_json.is_file():
            continue
        try:
            import json
            data = json.loads(safety_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        claims = data.get("claims") or []
        lines = [
            "# Safety case report",
            "",
            "Summary of the safety case (claim → control → test → artifact).",
            "",
            "## Claims",
            "",
        ]
        for c in claims[:30]:
            claim_id = c.get("claim_id") or c.get("id") or "?"
            controls = c.get("controls") or []
            tests = c.get("tests") or []
            lines.append(f"- **{claim_id}**: {len(controls)} control(s), {len(tests)} test(s).")
        lines.extend([
            "",
            "## Artifacts",
            "",
            "- [SAFETY_CASE/safety_case.json](SAFETY_CASE/safety_case.json) – full claim tree.",
            "- [SAFETY_CASE/safety_case.md](SAFETY_CASE/safety_case.md) – human-readable (when present).",
            "",
            "This report links the coordination decision and risk register to the safety case evidence.",
            "",
        ])
        report_path = out_dir / SAFETY_CASE_REPORT_FILENAME
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return True
    return False


def _decision_summary(decision: dict[str, Any]) -> list[str]:
    """Format scale decisions as markdown lines."""
    lines: list[str] = []
    for sd in decision.get("scale_decisions") or []:
        scale_id = sd.get("scale_id") or ""
        chosen = sd.get("chosen_method_id")
        if chosen:
            lines.append(f"- **{scale_id}**: chosen method `{chosen}`")
        else:
            lines.append(f"- **{scale_id}**: no admissible method")
    return lines


COORDINATION_MATRIX_FILENAME = "coordination_matrix.v0.1.json"


def build_lab_coordination_report(
    pack_dir: Path,
    out_dir: Path | None = None,
    policy_root: Path | None = None,
    matrix_preset_name: str | None = None,
    include_matrix: bool = False,
    partner_id: str | None = None,
) -> Path:
    """
    Build the lab coordination report bundle from a pack output directory.

    1. Run summarize-coordination (SOTA leaderboard, method-class comparison) into out_dir.
    2. Run recommend-coordination-method (COORDINATION_DECISION.*) into out_dir.
    3. Optionally build CoordinationMatrix in pack mode and write coordination_matrix.v0.1.json.
    4. Write LAB_COORDINATION_REPORT.md into out_dir with scope, links, snippets, and next steps.

    pack_dir: directory containing pack_summary.csv (and optionally pack_gate.md, SECURITY/).
    out_dir: directory for summary/, COORDINATION_DECISION.*, and LAB_COORDINATION_REPORT.md.
             If None, uses pack_dir.
    policy_root: repo policy root for selection policy and schemas; required for recommend.
    matrix_preset_name: optional preset name (e.g. hospital_lab) for report scope line.
    include_matrix: if True, build CoordinationMatrix from pack (pack mode) and add to artifacts.
    partner_id: optional partner overlay ID; selection policy loaded from partner overlay when present.

    Returns the path to LAB_COORDINATION_REPORT.md.
    """
    pack_dir = Path(pack_dir).resolve()
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"Pack directory not found: {pack_dir}")
    summary_csv = pack_dir / "pack_summary.csv"
    if not summary_csv.is_file():
        raise FileNotFoundError(
            f"pack_summary.csv not found under {pack_dir}. "
            "Run labtrust run-coordination-security-pack first."
        )
    out_dir = Path(out_dir).resolve() if out_dir else pack_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if policy_root is None:
        try:
            from labtrust_gym.config import get_repo_root
            policy_root = Path(get_repo_root())
        except Exception:
            policy_root = pack_dir
    policy_root = Path(policy_root).resolve()

    _ensure_summarize(pack_dir, out_dir, policy_root)
    result = _ensure_recommend(pack_dir, out_dir, policy_root, partner_id=partner_id)
    decision = result.get("decision") or {}

    matrix_path: Path | None = None
    if include_matrix:
        from labtrust_gym.studies.coordination_matrix_builder import (
            MATRIX_MODE_PACK,
            build_coordination_matrix,
        )
        matrix_path = out_dir / COORDINATION_MATRIX_FILENAME
        build_coordination_matrix(
            pack_dir, matrix_path, policy_root=policy_root, matrix_mode=MATRIX_MODE_PACK
        )

    scope = (
        f"Matrix preset: `{matrix_preset_name}`."
        if matrix_preset_name
        else "Coordination security pack run (scale x method x injection)."
    )
    decision_lines = _decision_summary(decision)
    _write_security_report(pack_dir, out_dir)
    _write_safety_case_report(out_dir, pack_dir)
    pack_gate_path = pack_dir / "pack_gate.md"
    risk_matrix_md_path = pack_dir / "SECURITY" / "coordination_risk_matrix.md"
    leaderboard_md_path = out_dir / "summary" / "sota_leaderboard.md"
    method_class_md_path = out_dir / "summary" / "method_class_comparison.md"
    decision_md_path = out_dir / "COORDINATION_DECISION.md"

    gate_rel = "pack_gate.md"
    if pack_gate_path.is_file() and out_dir != pack_dir:
        try:
            gate_rel = str(pack_gate_path.relative_to(out_dir))
        except ValueError:
            gate_rel = "pack_gate.md"
    risk_rel = "SECURITY/coordination_risk_matrix.md"
    if risk_matrix_md_path.is_file() and out_dir != pack_dir:
        try:
            risk_rel = str(risk_matrix_md_path.relative_to(out_dir))
        except ValueError:
            risk_rel = "SECURITY/coordination_risk_matrix.md"

    report_lines: list[str] = [
        "# Lab coordination report",
        "",
        "Single report bundle for coordination security pack results, SOTA leaderboard, and recommended method per scale.",
        "",
        "## Scope",
        "",
        scope,
        "",
        "## Recommended method per scale",
        "",
    ]
    report_lines.extend(decision_lines if decision_lines else ["(No scale decisions in artifact.)"])
    report_lines.extend([
        "",
        "## Artifacts in this bundle",
        "",
        "| Artifact | Description |",
        "| -------- | ----------- |",
        f"| [SECURITY_REPORT.md]({SECURITY_REPORT_FILENAME}) | Security pack and gate summary; links to pack_gate and SECURITY/. |",
        f"| [SAFETY_CASE_REPORT.md]({SAFETY_CASE_REPORT_FILENAME}) | Safety case summary and links (when SAFETY_CASE/ present). |",
        f"| [pack_gate.md]({gate_rel}) | PASS/FAIL/not_supported per cell. |",
        f"| [SECURITY/coordination_risk_matrix.md]({risk_rel}) | Method x injection x phase outcomes. |",
        "| [summary/sota_leaderboard.md](summary/sota_leaderboard.md) | Per-method means (throughput, violations, resilience, stealth). |",
        "| [summary/method_class_comparison.md](summary/method_class_comparison.md) | Comparison by method class. |",
        "| [COORDINATION_DECISION.md](COORDINATION_DECISION.md) | Chosen method and rationale (constraints + objective). |",
    ]
    if matrix_path is not None and matrix_path.is_file():
        report_lines.append(f"| [{COORDINATION_MATRIX_FILENAME}]({COORDINATION_MATRIX_FILENAME}) | CoordinationMatrix (pack-based): scores and ops_first/sec_first/balanced per scale. |")
    report_lines.extend([
        "",
        "## How to interpret",
        "",
        "- **pack_gate.md**: Each row is a cell (scale, method, injection). Verdict PASS means the cell met the gate rule for that injection.",
        "- **coordination_risk_matrix**: Security metrics (attack_success_rate, detection_latency_steps, verdict) per method and injection.",
        "- **SOTA leaderboard**: Methods ranked by aggregate metrics over all cells; use for throughput vs safety trade-offs.",
        "- **COORDINATION_DECISION**: The recommended method per scale under the selection policy (constraints + maximize_overall_score).",
        "",
        "## Next steps",
        "",
        "- Deploy the chosen method(s) from COORDINATION_DECISION for each scale.",
        "- Re-run with a different matrix preset (e.g. `--matrix-preset hospital_lab`) or `--methods-from full` for full coverage.",
        "- Use `labtrust run-coordination-security-pack --out <dir> --matrix-preset hospital_lab` then `labtrust build-lab-coordination-report --pack-dir <dir>` to refresh this report.",
        "",
    ])

    report_path = out_dir / LAB_REPORT_FILENAME
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return report_path
