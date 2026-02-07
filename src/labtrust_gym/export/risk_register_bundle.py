"""
Build RiskRegisterBundle.v0.1: single JSON artifact for risk register + evidence links.

Deterministic given identical policy and run dirs. Validates against
policy/schemas/risk_register_bundle.v0.1.schema.json.

Evidence model: security_attack (attack_results), coord_cell/summary, pareto_front,
safety_case_claim (SAFETY_CASE/safety_case.json), bundle_verification (MANIFEST).
Missing evidence is explicit via status=missing stubs with expected_sources.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from labtrust_gym.benchmarks.security_runner import load_attack_suite
from labtrust_gym.export.verify import verify_bundle_structured
from labtrust_gym.policy.coordination import load_method_risk_matrix
from labtrust_gym.policy.loader import load_yaml
from labtrust_gym.policy.risks import load_risk_registry

# Output filename for export-risk-register (writes into --out dir)
RISK_REGISTER_BUNDLE_FILENAME = "RISK_REGISTER_BUNDLE.v0.1.json"
MANIFEST_FILENAME = "MANIFEST.v0.1.json"
EVIDENCE_BUNDLE_DIR = "EvidenceBundle.v0.1"

# Columns from summary_coord.csv to surface for reviewers (security + resilience side-by-side)
COORD_SUMMARY_COLUMNS = [
    "sec.attack_success_rate",
    "sec.stealth_success_rate",
    "sec.time_to_attribution_steps",
    "sec.blast_radius_proxy",
    "robustness.resilience_score",
    "perf.p95_tat",
    "perf.throughput",
    "safety.violations_total",
]

# Risk registry category -> risk_domain (contract enum)
_CATEGORY_TO_DOMAIN: dict[str, str] = {
    "tool": "tool",
    "flow": "flow",
    "system": "system",
    "comms": "comms",
    "data": "data",
    "capability": "capability",
}
# Default applies_to when not derived per-risk
_DEFAULT_APPLIES_TO: list[str] = ["engine", "coordination"]
# Coverage order: best first
_COVERAGE_ORDER = ["covered", "partially_covered", "uncovered", "not_applicable"]


def _best_coverage(statuses: list[str]) -> str:
    """Return best coverage from list (covered > partially_covered > uncovered > not_applicable)."""
    for c in _COVERAGE_ORDER:
        if c in statuses:
            return c
    return "not_applicable"


def _policy_fingerprints(repo_root: Path) -> dict[str, str]:
    """Build policy_fingerprints from repo (deterministic)."""
    fp: dict[str, str] = {}
    paths = [
        ("risk_registry", "policy/risks/risk_registry.v0.1.yaml"),
        ("security_attack_suite", "policy/golden/security_attack_suite.v0.1.yaml"),
        ("method_risk_matrix", "policy/coordination/method_risk_matrix.v0.1.yaml"),
        ("safety_case_claims", "policy/safety_case/claims.v0.1.yaml"),
    ]
    for key, rel in paths:
        p = repo_root / rel
        if p.exists():
            fp[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    return fp


def _git_commit_hash(repo_root: Path) -> str | None:
    """Return current git commit hash or None."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def resolve_run_dirs(
    repo_root: Path,
    run_specs: list[str],
    include_official_pack_dir: Path | str | None = None,
) -> list[Path]:
    """
    Resolve run_specs (paths or globs) to a sorted list of existing directories.
    If include_official_pack_dir is set, append it to the list.
    """
    repo_root = Path(repo_root)
    seen: set[Path] = set()
    for spec in run_specs:
        spec_path = Path(spec)
        if not spec_path.is_absolute():
            spec_path = repo_root / spec_path
        if "*" in spec or "**" in spec:
            for p in sorted(glob.glob(str(spec_path))):
                path = Path(p).resolve()
                if path.is_dir() and path not in seen:
                    seen.add(path)
        else:
            if spec_path.is_dir() and spec_path.resolve() not in seen:
                seen.add(spec_path.resolve())
    if include_official_pack_dir is not None:
        pack = Path(include_official_pack_dir)
        if not pack.is_absolute():
            pack = repo_root / pack
        if pack.is_dir() and pack.resolve() not in seen:
            seen.add(pack.resolve())
    return sorted(seen)


def _load_manifest_hashes(run_dir: Path) -> dict[str, str]:
    """Load MANIFEST.v0.1.json from run_dir; return path -> sha256. Normalize path to forward slashes."""
    manifest_path = run_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = data.get("files") or []
        out: dict[str, str] = {}
        for entry in files:
            if isinstance(entry, dict):
                p = entry.get("path", "")
                h = entry.get("sha256", "")
                if p:
                    out[str(p).replace("\\", "/")] = h
        return out
    except Exception:
        return {}


def _find_evidence_bundle(run_dir: Path) -> Path | None:
    """Return first EvidenceBundle.v0.1 directory under run_dir (receipts/<task>/EvidenceBundle.v0.1 or evidence_bundle/)."""
    run_dir = Path(run_dir)
    for sub in ["receipts", "evidence_bundle"]:
        parent = run_dir / sub
        if not parent.is_dir():
            continue
        for p in parent.iterdir():
            if p.is_dir():
                bundle = p / EVIDENCE_BUNDLE_DIR
                if (bundle / "manifest.json").exists():
                    return bundle
    return None


def _expected_sources_for_risk(
    risk_id: str,
    suite: dict[str, Any],
    matrix: dict[str, Any],
) -> list[str]:
    """Return expected_sources for a risk when evidence is missing (for stubs)."""
    sources: list[str] = []
    for a in suite.get("attacks") or []:
        if a.get("risk_id") == risk_id:
            sources.append("security suite smoke")
            break
    for c in matrix.get("cells") or []:
        if c.get("risk_id") == risk_id:
            sources.append("coordination study required_bench")
            break
    if not sources:
        sources.append("policy or run evidence")
    return list(dict.fromkeys(sources))


def _build_risks(
    repo_root: Path,
    risk_registry: Any,
    matrix: dict[str, Any],
    suite: dict[str, Any],
    evidence_ids_by_risk: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Build risks[] with crosswalk fields. Deterministic order (by risk_id)."""
    cells = matrix.get("cells") or []
    coverage_by_risk: dict[str, list[str]] = {}
    for c in cells:
        rid = c.get("risk_id")
        if not rid:
            continue
        cov = c.get("coverage", "not_applicable")
        if cov not in _COVERAGE_ORDER:
            cov = "not_applicable"
        coverage_by_risk.setdefault(rid, []).append(cov)

    risk_to_controls: dict[str, list[str]] = {}
    for a in suite.get("attacks") or []:
        rid = a.get("risk_id")
        cid = a.get("control_id")
        if rid and cid:
            risk_to_controls.setdefault(rid, []).append(cid)

    out: list[dict[str, Any]] = []
    for risk_id in sorted(risk_registry.risks.keys()):
        r = risk_registry.risks[risk_id]
        category = (r.get("category") or "tool").lower()
        risk_domain = _CATEGORY_TO_DOMAIN.get(category, "operational")
        coverage_status = _best_coverage(coverage_by_risk.get(risk_id, []))
        claimed = list(dict.fromkeys(risk_to_controls.get(risk_id, [])))
        evidence_refs = list(
            dict.fromkeys(evidence_ids_by_risk.get(risk_id, []))
        )

        entry: dict[str, Any] = {
            "risk_id": risk_id,
            "name": r.get("name", risk_id),
            "risk_domain": risk_domain,
            "applies_to": list(_DEFAULT_APPLIES_TO),
            "claimed_controls": claimed,
            "evidence_refs": evidence_refs,
            "coverage_status": coverage_status,
        }
        for opt in [
            "description",
            "typical_failure_mode",
            "mitigation_options",
            "suggested_injections",
            "primary_metrics",
            "severity_hint",
            "complexity_hint",
        ]:
            if r.get(opt) is not None:
                entry[opt] = r[opt]
        out.append(entry)
    return out


def _build_controls(suite: dict[str, Any], claims_path: Path) -> list[dict[str, Any]]:
    """Build controls[] from security suite and safety_case claims."""
    by_id: dict[str, dict[str, Any]] = {}
    for c in suite.get("controls") or []:
        cid = c.get("control_id")
        if cid:
            by_id[cid] = {
                "control_id": cid,
                "name": c.get("name", cid),
                "description": c.get("description"),
                "source": "security_suite",
            }
    if claims_path.exists():
        try:
            data = load_yaml(claims_path)
            for claim in data.get("safety_case_claims", {}).get("claims") or []:
                for c in claim.get("controls") or []:
                    name = c if isinstance(c, str) else c.get("name")
                    if name and name not in by_id:
                        by_id[name] = {
                            "control_id": name,
                            "name": name,
                            "source": "safety_case",
                        }
        except Exception:
            pass
    return [by_id[k] for k in sorted(by_id.keys())]


def _build_evidence(
    repo_root: Path,
    run_dirs: list[Path],
    suite: dict[str, Any],
    matrix: dict[str, Any],
    all_risk_ids: list[str],
    include_missing_stubs: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """
    Build evidence[] from run_dirs. Returns (evidence_list, risk_id -> evidence_ids).
    Includes SECURITY/attack_results.json, coverage.json, summary_coord.csv, PARETO/pareto.json,
    SAFETY_CASE/safety_case.json, MANIFEST.v0.1.json. Uses MANIFEST for artifacts sha256 when present.
    If include_missing_stubs, adds one evidence stub per risk with no evidence (status=missing).
    Deterministic order by evidence_id.
    """
    evidence: list[dict[str, Any]] = []
    risk_to_evidence: dict[str, list[str]] = {}
    ev_id = 0

    for run_dir in run_dirs:
        run_dir = Path(run_dir)
        prefix = run_dir.name + "/" if len(run_dirs) > 1 else ""
        manifest_hashes = _load_manifest_hashes(run_dir)

        def _artifact(rel: str) -> dict[str, Any]:
            key = rel.replace("\\", "/")
            a: dict[str, Any] = {"path": prefix + key if prefix else key}
            if key in manifest_hashes:
                a["sha256"] = manifest_hashes[key]
            return a

        # SECURITY/attack_results.json
        security_dir = run_dir / "SECURITY"
        attack_results_path = "SECURITY/attack_results.json"
        if (security_dir / "attack_results.json").exists():
            eid = f"ev-security-{ev_id}"
            ev_id += 1
            entry: dict[str, Any] = {
                "evidence_id": eid,
                "type": "security_suite",
                "path": prefix + attack_results_path,
                "label": "Security attack results",
                "status": "present",
                "artifacts": [_artifact(attack_results_path)],
            }
            try:
                ar = json.loads(
                    (security_dir / "attack_results.json").read_text(
                        encoding="utf-8"
                    )
                )
                sm = ar.get("summary") or {}
                entry["summary"] = {
                    "total": sm.get("total", 0),
                    "passed": sm.get("passed", 0),
                    "failed": sm.get("failed", 0),
                }
                reason_code_dist: dict[str, int] = {}
                for res in ar.get("results") or []:
                    rid = res.get("risk_id")
                    if rid:
                        risk_to_evidence.setdefault(rid, []).append(eid)
                    for code, count in (res.get("reason_code_counts") or {}).items():
                        if isinstance(count, (int, float)):
                            reason_code_dist[str(code)] = reason_code_dist.get(str(code), 0) + int(count)
                if reason_code_dist:
                    entry["reason_code_distribution"] = dict(
                        sorted(reason_code_dist.items(), key=lambda x: -x[1])[:20]
                    )
            except Exception:
                pass
            evidence.append(entry)

        # SECURITY/coverage.json
        coverage_path = "SECURITY/coverage.json"
        if (security_dir / "coverage.json").exists():
            eid = f"ev-coverage-{ev_id}"
            ev_id += 1
            evidence.append({
                "evidence_id": eid,
                "type": "security_suite",
                "path": prefix + coverage_path,
                "label": "Security coverage",
                "status": "present",
                "artifacts": [_artifact(coverage_path)],
            })

        # summary/summary_coord.csv (security + resilience metrics side-by-side)
        summary_path = "summary/summary_coord.csv"
        summary_csv = run_dir / "summary" / "summary_coord.csv"
        if summary_csv.exists():
            eid = f"ev-coord-summary-{ev_id}"
            ev_id += 1
            coord_entry: dict[str, Any] = {
                "evidence_id": eid,
                "type": "coordination_study",
                "path": prefix + summary_path,
                "label": "Coordination study summary",
                "status": "present",
                "artifacts": [_artifact(summary_path)],
            }
            try:
                with summary_csv.open(newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows: list[dict[str, Any]] = []
                    for row in reader:
                        out: dict[str, Any] = {}
                        for col in COORD_SUMMARY_COLUMNS:
                            val = row.get(col)
                            if val == "" or val is None:
                                out[col] = None
                                continue
                            try:
                                out[col] = float(val)
                            except (ValueError, TypeError):
                                out[col] = val
                        rows.append(out)
                    if rows:
                        coord_entry["summary"] = {
                            "coord_metrics": rows,
                            "row_count": len(rows),
                        }
            except Exception:
                pass
            evidence.append(coord_entry)

        # PARETO/pareto.json
        pareto_path = "PARETO/pareto.json"
        pareto = run_dir / "PARETO" / "pareto.json"
        if pareto.exists():
            eid = f"ev-pareto-{ev_id}"
            ev_id += 1
            evidence.append({
                "evidence_id": eid,
                "type": "coordination_study",
                "path": prefix + pareto_path,
                "label": "Pareto front",
                "status": "present",
                "artifacts": [_artifact(pareto_path)],
            })

        # SAFETY_CASE/safety_case.json
        safety_path = "SAFETY_CASE/safety_case.json"
        safety_json = run_dir / "SAFETY_CASE" / "safety_case.json"
        if safety_json.exists():
            eid = f"ev-safety-case-{ev_id}"
            ev_id += 1
            evidence.append({
                "evidence_id": eid,
                "type": "safety_case",
                "path": prefix + safety_path,
                "label": "Safety case claims",
                "status": "present",
                "artifacts": [_artifact(safety_path)],
            })

        # MANIFEST.v0.1.json (bundle_verification); optional EvidenceBundle verification summary
        if (run_dir / MANIFEST_FILENAME).exists():
            eid = f"ev-manifest-{ev_id}"
            ev_id += 1
            manifest_entry: dict[str, Any] = {
                "evidence_id": eid,
                "type": "bundle_verification",
                "path": prefix + MANIFEST_FILENAME,
                "label": "Run manifest (hashes)",
                "status": "present",
                "artifacts": [_artifact(MANIFEST_FILENAME)],
            }
            bundle_path = _find_evidence_bundle(run_dir)
            if bundle_path is not None:
                try:
                    vs = verify_bundle_structured(bundle_path, repo_root, allow_extra_files=True)
                    manifest_entry["verification_summary"] = {
                        "manifest_valid": vs.get("manifest_valid", False),
                        "schema_valid": vs.get("schema_valid", False),
                        "hashchain_valid": vs.get("hashchain_valid", False),
                        "invariant_trace_valid": vs.get("invariant_trace_valid", False),
                        "policy_fingerprints": vs.get("policy_fingerprints") or {},
                        "errors": vs.get("errors") or [],
                    }
                except Exception:
                    pass
            evidence.append(manifest_entry)

    # Missing evidence stubs: one per risk with no evidence_refs
    if include_missing_stubs:
        for risk_id in all_risk_ids:
            if risk_id in risk_to_evidence:
                continue
            eid = f"ev-missing-{risk_id}"
            evidence.append({
                "evidence_id": eid,
                "type": "other",
                "path": "",
                "label": f"Evidence missing for {risk_id}",
                "status": "missing",
                "expected_sources": _expected_sources_for_risk(risk_id, suite, matrix),
                "risk_ids": [risk_id],
            })
            risk_to_evidence[risk_id] = [eid]

    return evidence, risk_to_evidence


def _build_reproduce(evidence_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build reproduce[]: one entry per evidence with deterministic CLI commands.
    UI renders these as "how to reproduce" without hardcoding. Placeholders
    <output_dir> and <study_spec> can be substituted by the user.
    """
    out: list[dict[str, Any]] = []
    for e in evidence_list:
        eid = e.get("evidence_id", "")
        etype = e.get("type", "other")
        status = e.get("status", "present")
        label = e.get("label") or eid

        if status == "missing" or etype == "other":
            out.append({
                "evidence_id": eid,
                "label": label,
                "commands": [],
            })
            continue

        if etype == "security_suite":
            # attack_results or coverage: same run produces both
            out.append({
                "evidence_id": eid,
                "label": "Security suite",
                "commands": [
                    "labtrust run-security-suite --out <output_dir> --seed 42",
                ],
            })
        elif etype == "coordination_study":
            out.append({
                "evidence_id": eid,
                "label": "Coordination study",
                "commands": [
                    "labtrust run-coordination-study --spec <study_spec> --out <output_dir>",
                    "# Or single cell: labtrust run-benchmark --task TaskH_COORD_RISK --coord-method <method> --injection <injection> --seed 42 --out <output_dir>",
                ],
            })
        elif etype == "safety_case":
            out.append({
                "evidence_id": eid,
                "label": "Safety case",
                "commands": [
                    "labtrust safety-case --out <output_dir>",
                ],
            })
        elif etype == "official_pack":
            out.append({
                "evidence_id": eid,
                "label": "Official benchmark pack",
                "commands": [
                    "labtrust run-official-pack --out <output_dir> [--seed-base 42]",
                ],
            })
        elif etype == "bundle_verification":
            out.append({
                "evidence_id": eid,
                "label": "Bundle verification",
                "commands": [
                    "labtrust verify-bundle --bundle <run_dir>",
                    "# Or full release: labtrust package-release --profile paper_v0.1 --out <output_dir>",
                ],
            })
        else:
            out.append({
                "evidence_id": eid,
                "label": label,
                "commands": [],
            })
    return out


def _build_links(repo_root: Path, run_dirs: list[Path]) -> list[dict[str, Any]]:
    """Build links[] for repo-local and run-local paths. Deterministic order.
    Run-local hrefs are normalized to repo-relative forward-slash paths for portability.
    """
    repo_root = Path(repo_root).resolve()
    links: list[dict[str, Any]] = []
    repo_links = [
        ("policy/risks/risk_registry.v0.1.yaml", "Risk registry"),
        ("policy/coordination/method_risk_matrix.v0.1.yaml", "Method-risk matrix"),
        ("policy/golden/security_attack_suite.v0.1.yaml", "Security attack suite"),
        ("policy/safety_case/claims.v0.1.yaml", "Safety case claims"),
        ("docs/risk_register_contract.v0.1.md", "Risk register contract"),
    ]
    for rel, label in repo_links:
        if (repo_root / rel).exists():
            links.append({
                "href": rel,
                "label": label,
                "type": "repo_local",
            })
    for run_dir in run_dirs:
        run_dir = Path(run_dir)
        for rel, label in [
            ("SECURITY/attack_results.json", "Attack results"),
            ("SECURITY/coverage.json", "Coverage"),
            ("summary/summary_coord.csv", "Summary coord"),
            ("PARETO/pareto.json", "Pareto front"),
            ("SAFETY_CASE/safety_case.json", "Safety case"),
            (MANIFEST_FILENAME, "Manifest"),
        ]:
            if (run_dir / rel).exists():
                full = run_dir / rel
                try:
                    href = full.relative_to(repo_root).as_posix()
                except ValueError:
                    href = str(full)
                links.append({
                    "href": href,
                    "label": label,
                    "type": "run_local",
                })
    return links


def build_risk_register_bundle(
    repo_root: Path,
    run_dirs: list[Path] | None = None,
    *,
    include_generated_at: bool = False,
    include_git_hash: bool = True,
) -> dict[str, Any]:
    """
    Build RiskRegisterBundle.v0.1 from repo policy and optional run dirs.

    Deterministic when policy and run_dirs content are identical. Output
    validates against policy/schemas/risk_register_bundle.v0.1.schema.json.
    """
    repo_root = Path(repo_root)
    run_dirs = run_dirs or []

    risk_reg_path = repo_root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    risk_registry = load_risk_registry(risk_reg_path)

    matrix_path = (
        repo_root
        / "policy"
        / "coordination"
        / "method_risk_matrix.v0.1.yaml"
    )
    matrix = (
        load_method_risk_matrix(matrix_path)
        if matrix_path.exists()
        else {"cells": []}
    )

    suite = load_attack_suite(repo_root)
    claims_path = repo_root / "policy" / "safety_case" / "claims.v0.1.yaml"

    all_risk_ids = sorted(risk_registry.risks.keys())
    evidence_list, risk_to_evidence = _build_evidence(
        repo_root,
        run_dirs,
        suite=suite,
        matrix=matrix,
        all_risk_ids=all_risk_ids,
        include_missing_stubs=True,
    )
    risks_list = _build_risks(
        repo_root,
        risk_registry,
        matrix,
        suite,
        risk_to_evidence,
    )
    controls_list = _build_controls(suite, claims_path)
    links_list = _build_links(repo_root, run_dirs)
    reproduce_list = _build_reproduce(evidence_list)

    bundle: dict[str, Any] = {
        "bundle_version": "0.1",
        "risks": risks_list,
        "controls": controls_list,
        "evidence": evidence_list,
        "links": links_list,
        "reproduce": reproduce_list,
    }
    if include_generated_at:
        from datetime import datetime, timezone

        bundle["generated_at"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
    if include_git_hash:
        h = _git_commit_hash(repo_root)
        if h:
            bundle["git_commit_hash"] = h
    bundle["policy_fingerprints"] = _policy_fingerprints(repo_root)
    return bundle


def validate_bundle_against_schema(bundle: dict[str, Any], repo_root: Path) -> list[str]:
    """Validate bundle against risk_register_bundle.v0.1.schema.json. Returns list of errors."""
    schema_path = (
        repo_root
        / "policy"
        / "schemas"
        / "risk_register_bundle.v0.1.schema.json"
    )
    if not schema_path.exists():
        return [f"Schema not found: {schema_path}"]
    try:
        from labtrust_gym.policy.loader import load_json, validate_against_schema

        schema = load_json(schema_path)
        validate_against_schema(bundle, schema, path=schema_path)
        return []
    except Exception as e:
        return [str(e)]


def write_risk_register_bundle(
    repo_root: Path,
    out_path: Path,
    run_dirs: list[Path] | None = None,
    *,
    include_generated_at: bool = False,
    include_git_hash: bool = True,
    validate: bool = True,
) -> None:
    """Build bundle and write JSON to out_path. Deterministic key order."""
    bundle = build_risk_register_bundle(
        repo_root,
        run_dirs=run_dirs or [],
        include_generated_at=include_generated_at,
        include_git_hash=include_git_hash,
    )
    if validate:
        errs = validate_bundle_against_schema(bundle, Path(repo_root))
        if errs:
            raise ValueError(f"Bundle validation failed: {errs}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def export_risk_register(
    repo_root: Path,
    out_dir: Path,
    run_specs: list[str] | None = None,
    include_official_pack_dir: Path | str | None = None,
    *,
    include_generated_at: bool = False,
    include_git_hash: bool = True,
    validate: bool = True,
    inject_ui_export: bool = False,
) -> Path:
    """
    Build RiskRegisterBundle.v0.1 and write to out_dir/RISK_REGISTER_BUNDLE.v0.1.json.
    Run specs are paths or globs (resolved against repo_root). Optional include_official_pack_dir
    is added to the run dirs. If inject_ui_export is True, also write the same bundle into each
    resolved run dir so the UI can load it from there.
    Returns the path to the written bundle file.
    """
    repo_root = Path(repo_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dirs = resolve_run_dirs(
        repo_root,
        run_specs or [],
        include_official_pack_dir=include_official_pack_dir,
    )
    bundle = build_risk_register_bundle(
        repo_root,
        run_dirs=run_dirs,
        include_generated_at=include_generated_at,
        include_git_hash=include_git_hash,
    )
    if validate:
        errs = validate_bundle_against_schema(bundle, repo_root)
        if errs:
            raise ValueError(f"Bundle validation failed: {errs}")
    out_path = out_dir / RISK_REGISTER_BUNDLE_FILENAME
    out_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if inject_ui_export:
        for run_dir in run_dirs:
            run_dir = Path(run_dir)
            inject_path = run_dir / RISK_REGISTER_BUNDLE_FILENAME
            inject_path.write_text(
                json.dumps(bundle, indent=2, sort_keys=True),
                encoding="utf-8",
            )
    return out_path


def check_crosswalk_integrity(bundle: dict[str, Any]) -> list[str]:
    """
    Verify crosswalk integrity: every risk_id referenced in evidence exists in risks;
    every control_id in claimed_controls exists in controls. Returns list of error messages.
    """
    errors: list[str] = []
    risks_list = bundle.get("risks") or []
    controls_list = bundle.get("controls") or []
    evidence_list = bundle.get("evidence") or []

    risk_ids = {r["risk_id"] for r in risks_list if r.get("risk_id")}
    control_ids = {c["control_id"] for c in controls_list if c.get("control_id")}
    evidence_ids = {e["evidence_id"] for e in evidence_list if e.get("evidence_id")}

    for e in evidence_list:
        for rid in e.get("risk_ids") or []:
            if rid and rid not in risk_ids:
                errors.append(f"evidence {e.get('evidence_id')!r} references risk_id {rid!r} not in risks")
    for r in risks_list:
        for ref in r.get("evidence_refs") or []:
            if ref and ref not in evidence_ids:
                errors.append(f"risk {r.get('risk_id')!r} references evidence_id {ref!r} not in evidence")
        for cid in r.get("claimed_controls") or []:
            if cid and cid not in control_ids:
                errors.append(f"risk {r.get('risk_id')!r} references control_id {cid!r} not in controls")
    return errors


def check_risk_register_coverage(
    bundle: dict[str, Any],
    repo_root: Path,
    *,
    waived_risk_ids: set[str] | None = None,
    matrix_path: Path | None = None,
) -> tuple[bool, list[tuple[str, str]]]:
    """
    Check that every required_bench (method_id, risk_id) cell is either evidenced
    (risk has at least one present evidence in the bundle) or waived.
    Same philosophy as coordination coverage gate. Returns (passed, missing_list).
    missing_list is [(method_id, risk_id), ...] for cells with no evidence and not waived.
    """
    from labtrust_gym.policy.coordination import get_required_bench_cells, load_method_risk_matrix

    waived = waived_risk_ids or set()
    repo_root = Path(repo_root)
    matrix_path = matrix_path or (
        repo_root / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    )
    if not matrix_path.exists():
        return True, []

    matrix = load_method_risk_matrix(matrix_path)
    required = get_required_bench_cells(matrix)
    evidence_list = bundle.get("evidence") or []
    evidence_by_id = {e["evidence_id"]: e for e in evidence_list if e.get("evidence_id")}
    risk_ids_with_present_evidence: set[str] = set()
    for r in bundle.get("risks") or []:
        rid = r.get("risk_id")
        if not rid:
            continue
        for eid in r.get("evidence_refs") or []:
            ev = evidence_by_id.get(eid)
            if ev and ev.get("status") == "present":
                risk_ids_with_present_evidence.add(rid)
                break

    missing: list[tuple[str, str]] = []
    for cell in required:
        if not isinstance(cell, dict):
            continue
        mid = str(cell.get("method_id") or "").strip()
        rid = str(cell.get("risk_id") or "").strip()
        if not rid:
            continue
        if rid in waived:
            continue
        if rid in risk_ids_with_present_evidence:
            continue
        missing.append((mid, rid))
    return (len(missing) == 0, missing)
