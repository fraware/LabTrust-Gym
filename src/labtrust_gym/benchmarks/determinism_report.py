"""
Determinism proof: run benchmark twice with identical args, compare hashes and v0.2 metrics.

Produces determinism_report.md and determinism_report.json with sha256 of episode logs,
results.json (canonical), and receipts bundle root hash. Asserts: v0.2 metrics identical;
episode log hash identical. With timing=simulated, device service-time sampling is
seeded only from the provided seed (engine RNG = base_seed + episode index per episode).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.benchmarks.summarize import _normalize_to_v02
from labtrust_gym.util.json_utils import canonical_json


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_string(s: str) -> str:
    return _sha256_bytes(s.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _v02_metrics_canonical(results: dict[str, Any]) -> str:
    """Canonical v0.2 content: task, seeds, episodes (seed + metrics)."""
    norm = _normalize_to_v02(results)
    if not norm:
        return ""
    # Strip non-deterministic / variable fields for comparison
    episodes = norm.get("episodes") or []
    out = {
        "task": norm["task"],
        "seeds": norm["seeds"],
        "agent_baseline_id": norm["agent_baseline_id"],
        "episodes": [
            {"seed": ep.get("seed"), "metrics": ep.get("metrics") or {}}
            for ep in episodes
        ],
    }
    return canonical_json(out)


def _run_and_hash(
    task_name: str,
    num_episodes: int,
    base_seed: int,
    run_dir: Path,
    repo_root: Path,
    partner_id: str | None = None,
    timing_mode: str | None = None,
    coord_method: str | None = None,
) -> tuple[dict[str, Any], str, str, str | None]:
    """
    Run benchmark once in run_dir; return (results, episode_log_sha256, results_sha256,
    receipts_bundle_root_hash). Hashes: results = canonical JSON; episode log = raw bytes.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "episode_log.jsonl"
    results_path = run_dir / "results.json"
    run_benchmark(
        task_name=task_name,
        num_episodes=num_episodes,
        base_seed=base_seed,
        out_path=results_path,
        repo_root=repo_root,
        log_path=log_path,
        partner_id=partner_id,
        timing_mode=timing_mode,
        coord_method=coord_method,
    )
    results = json.loads(results_path.read_text(encoding="utf-8"))
    episode_log_sha256 = _sha256_file(log_path)
    results_sha256 = _sha256_string(canonical_json(results))
    receipts_dir = run_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    bundle_root_hash: str | None = None
    try:
        from labtrust_gym.export.receipts import export_receipts

        bundle_dir = export_receipts(
            log_path,
            receipts_dir,
            partner_id=partner_id,
            policy_root=repo_root,
        )
        manifest_path = bundle_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bundle_root_hash = _sha256_string(canonical_json(manifest))
    except Exception:
        pass
    return results, episode_log_sha256, results_sha256, bundle_root_hash


def run_determinism_report(
    task_name: str,
    num_episodes: int,
    base_seed: int,
    out_dir: Path,
    partner_id: str | None = None,
    timing_mode: str | None = None,
    repo_root: Path | None = None,
    coord_method: str | None = None,
) -> tuple[bool, dict[str, Any], str]:
    """
    Run benchmark twice in fresh temp dirs with identical args; compare hashes and v0.2.

    Returns (passed, report_dict, markdown_text).
    Asserts: episode log sha256 identical; results canonical sha256 identical;
    v0.2 metrics canonical identical; receipts bundle root identical (when export ok).
    For coord_scale/coord_risk, coord_method required (default: kernel_centralized_edf).
    """
    if repo_root is None:
        from labtrust_gym.config import get_repo_root

        repo_root = get_repo_root()
    repo_root = Path(repo_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if task_name in ("coord_scale", "coord_risk") and coord_method is None:
        coord_method = "kernel_centralized_edf"

    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="labtrust_det_run1_") as td1:
        results1, log_sha1, res_sha1, bundle_hash1 = _run_and_hash(
            task_name,
            num_episodes,
            base_seed,
            Path(td1),
            repo_root,
            partner_id=partner_id,
            timing_mode=timing_mode,
            coord_method=coord_method,
        )
    with tempfile.TemporaryDirectory(prefix="labtrust_det_run2_") as td2:
        results2, log_sha2, res_sha2, bundle_hash2 = _run_and_hash(
            task_name,
            num_episodes,
            base_seed,
            Path(td2),
            repo_root,
            partner_id=partner_id,
            timing_mode=timing_mode,
            coord_method=coord_method,
        )

    if log_sha1 != log_sha2:
        errors.append("Episode log SHA-256 mismatch (non-deterministic episode log)")
    if res_sha1 != res_sha2:
        errors.append("Results.json canonical SHA-256 mismatch (non-deterministic results)")
    v02_c1 = _v02_metrics_canonical(results1)
    v02_c2 = _v02_metrics_canonical(results2)
    if v02_c1 != v02_c2:
        errors.append("v0.2 metrics canonical representation mismatch")
    if bundle_hash1 and bundle_hash2 and bundle_hash1 != bundle_hash2:
        errors.append("Receipts bundle root hash mismatch")
    elif (bundle_hash1 is None) != (bundle_hash2 is None):
        errors.append(
            "Receipts bundle export failed for one run; cannot compare bundle root"
        )

    run1_payload = {
        "episode_log_sha256": log_sha1,
        "results_sha256": res_sha1,
        "receipts_bundle_root_hash": bundle_hash1,
    }
    run2_payload = {
        "episode_log_sha256": log_sha2,
        "results_sha256": res_sha2,
        "receipts_bundle_root_hash": bundle_hash2,
    }
    passed = len(errors) == 0
    report = {
        "task": task_name,
        "num_episodes": num_episodes,
        "base_seed": base_seed,
        "partner_id": partner_id,
        "timing_mode": timing_mode or "explicit",
        "coord_method": coord_method,
        "run1": run1_payload,
        "run2": run2_payload,
        "passed": passed,
        "errors": errors,
        "v02_metrics_identical": v02_c1 == v02_c2,
        "episode_log_identical": log_sha1 == log_sha2,
        "results_identical": res_sha1 == res_sha2,
        "receipts_bundle_identical": (
            (bundle_hash1 == bundle_hash2) if (bundle_hash1 and bundle_hash2) else None
        ),
    }

    status_label = "PASSED" if passed else "FAILED"
    n_passed = (
        (1 if log_sha1 == log_sha2 else 0)
        + (1 if res_sha1 == res_sha2 else 0)
        + (1 if v02_c1 == v02_c2 else 0)
    )
    n_total = 4 if (bundle_hash1 and bundle_hash2) else 3
    if bundle_hash1 and bundle_hash2:
        n_passed += 1 if bundle_hash1 == bundle_hash2 else 0
    checks_line = f"**Checks:** {n_passed}/{n_total} passed."
    if not passed:
        checks_line += " See Errors below."
    md_lines = [
        "# Determinism report",
        "",
        checks_line,
        "",
        "Two runs, identical args; hashes and v0.2 metrics must match.",
        "",
        "---",
        "",
        "## Run configuration",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Task | {task_name} |",
        f"| Episodes | {num_episodes} |",
        f"| Seed | {base_seed} |",
        f"| Partner | {partner_id or '(none)'} |",
        f"| Timing | {report['timing_mode']} |",
    ]
    if coord_method:
        md_lines.append(f"| Coord method | {coord_method} |")
    md_lines.extend(
        [
            "",
            "---",
            "",
            "## Result",
            "",
            f"**{status_label}**",
            "",
        ]
    )
    if errors:
        md_lines.append("### Errors")
        md_lines.append("")
        for e in errors:
            md_lines.append(f"- {e}")
        md_lines.append("")
    log_match = "yes" if log_sha1 == log_sha2 else "**no**"
    res_match = "yes" if res_sha1 == res_sha2 else "**no**"
    v02_match = "yes" if v02_c1 == v02_c2 else "**no**"
    row_log = (
        f"| Episode log SHA-256 | `{log_sha1[:16]}...` | "
        f"`{log_sha2[:16]}...` | {log_match} |"
    )
    row_res = (
        f"| Results canonical SHA-256 | `{res_sha1[:16]}...` | "
        f"`{res_sha2[:16]}...` | {res_match} |"
    )
    md_lines.extend(
        [
            "## Hash comparison",
            "",
            "| Check | Run 1 | Run 2 | Match |",
            "|-------|-------|-------|-------|",
            row_log,
            row_res,
            f"| v0.2 metrics canonical | — | — | {v02_match} |",
            "",
        ]
    )
    if bundle_hash1 and bundle_hash2:
        bundle_match = "yes" if bundle_hash1 == bundle_hash2 else "**no**"
        md_lines.append(
            f"| Receipts bundle root | `{bundle_hash1[:16]}...` | "
            f"`{bundle_hash2[:16]}...` | {bundle_match} |"
        )
        md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(
        "When `timing=simulated`, device service-time sampling is seeded only from "
        "the provided seed (engine RNG per episode = base_seed + episode index)."
    )
    markdown_text = "\n".join(md_lines)

    report_path_json = out_dir / "determinism_report.json"
    report_path_md = out_dir / "determinism_report.md"
    report_path_json.write_text(
        canonical_json(report) + "\n", encoding="utf-8"
    )
    report_path_md.write_text(markdown_text, encoding="utf-8")

    return passed, report, markdown_text
