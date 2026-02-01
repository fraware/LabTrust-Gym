"""
Release candidate research artifact: reproduce + export-receipts + export-fhir + make-plots,
then MANIFEST.v0.1.json, BENCHMARK_CARD.md, metadata.json.

Single command: labtrust package-release --profile minimal|full --out <dir>
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.studies.reproduce import run_reproduce


MANIFEST_VERSION = "0.1"
REPRO_DIR_NAME = "_repro"


def _git_commit_hash(cwd: Optional[Path] = None) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd or Path.cwd(),
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_files_with_hashes(root: Path, exclude_dirs: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Walk root, return list of {path: relpath, sha256: hex} sorted by path. Skip exclude_dirs."""
    exclude = set(exclude_dirs or [])
    out: List[Dict[str, str]] = []
    root = root.resolve()
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root)
            if any(rel.parts[i] in exclude for i in range(len(rel.parts))):
                continue
            out.append({
                "path": str(rel).replace("\\", "/"),
                "sha256": _sha256_file(f),
            })
        except ValueError:
            continue
    return out


def _render_benchmark_card_template(
    repo_root: Path,
    metadata: Dict[str, Any],
) -> str:
    """Render BENCHMARK_CARD.md from template (docs/benchmark_card.md) and metadata."""
    template_path = repo_root / "docs" / "benchmark_card.md"
    if template_path.exists():
        body = template_path.read_text(encoding="utf-8")
    else:
        body = _default_benchmark_card_content()
    # Optional: inject metadata (e.g. generated timestamp)
    return body


def _default_benchmark_card_content() -> str:
    return """# LabTrust-Gym Benchmark Card

## Scope

Blood Sciences lane: specimen reception, accessioning, pre-analytics, routine and STAT analytics, QC, critical result notification, and release. Multi-site transport (hub + acute) with consignments and chain-of-custody.

## Invariants and enforcement

- **Invariant registry** (v1.0): zone movement, co-location, restricted door, critical ack, stability, transport (INV-COC-001, INV-TRANSPORT-001), etc.
- **Enforcement**: optional throttle, kill_switch, freeze_zone, forensic_freeze via policy/enforcement.

## Tasks (A–E)

| Task | Description | SLA |
|------|-------------|-----|
| TaskA | Throughput under SLA | 3600 s |
| TaskB | STAT insertion under load | 1800 s |
| TaskC | QC fail cascade | — |
| TaskD | Adversarial disruption | 3600 s |
| TaskE | Multi-site STAT (transport latency) | 2400 s |

## Baselines

- **Scripted (ops + runner)**: deterministic policy; used in reproduce and package-release.
- **Adversary** (TaskD): scripted adversary agent.
- **PPO/MARL**: optional Stable-Baselines3; train-ppo / eval-ppo.
- **LLM mock**: optional LLM agent stub.

## Known limitations and non-goals

- Golden suite: some scenarios (e.g. zone door alarm) may depend on enforcement or timing.
- Full FHIR validation: export is minimal structural; no terminology server.
- Transport: scripted agents do not yet emit DISPATCH_TRANSPORT; TaskE runs without transport actions unless extended.
"""


def run_package_release(
    profile: str,
    out_dir: Path,
    repo_root: Optional[Path] = None,
    seed_base: Optional[int] = None,
    include_repro_dir: bool = False,
    fixed_timestamp: Optional[str] = None,
) -> Path:
    """
    Run reproduce, export receipts and FHIR, copy plots/tables, write MANIFEST, BENCHMARK_CARD, metadata.
    Returns release_out directory.
    """
    repo_root = repo_root or Path.cwd()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    repro_dir = out_dir / REPRO_DIR_NAME
    seed_base = seed_base if seed_base is not None else 100

    run_reproduce(
        profile=profile,
        out_dir=repro_dir,
        repo_root=repo_root,
        seed_base=seed_base,
    )

    from labtrust_gym.export.receipts import export_receipts
    from labtrust_gym.export.fhir_r4 import export_fhir

    receipts_out = out_dir / "receipts"
    fhir_out = out_dir / "fhir"
    plots_out = out_dir / "plots"
    tables_out = out_dir / "tables"
    results_out = out_dir / "results"
    receipts_out.mkdir(parents=True, exist_ok=True)
    fhir_out.mkdir(parents=True, exist_ok=True)
    plots_out.mkdir(parents=True, exist_ok=True)
    tables_out.mkdir(parents=True, exist_ok=True)
    results_out.mkdir(parents=True, exist_ok=True)

    all_manifests: List[Dict[str, Any]] = []
    partner_id: Optional[str] = None
    policy_fingerprint: Optional[str] = None

    for task in ["taska", "taskc"]:
        task_path = repro_dir / task
        if not task_path.is_dir():
            continue
        manifest_path = task_path / "manifest.json"
        condition_ids: List[str] = []
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            all_manifests.append(manifest)
            if partner_id is None:
                partner_id = manifest.get("partner_id")
            if policy_fingerprint is None:
                policy_fingerprint = manifest.get("policy_fingerprint")
            condition_ids = manifest.get("condition_ids") or []
        for cid in condition_ids:
            log_path = task_path / "logs" / cid / "episodes.jsonl"
            if not log_path.exists():
                continue
            label = f"{task}_{cid}"
            rec_dir = receipts_out / label
            rec_dir.mkdir(parents=True, exist_ok=True)
            try:
                export_receipts(log_path, rec_dir)
            except Exception:
                pass
            bundle_dir = rec_dir / "EvidenceBundle.v0.1"
            if bundle_dir.exists():
                fhir_dir = fhir_out / label
                fhir_dir.mkdir(parents=True, exist_ok=True)
                try:
                    export_fhir(bundle_dir, fhir_dir, out_filename="fhir_bundle.json")
                except Exception:
                    pass
        figures_dir = task_path / "figures"
        if figures_dir.exists():
            for f in figures_dir.iterdir():
                if f.is_file() and f.suffix.lower() in (".png", ".svg"):
                    shutil.copy2(f, plots_out / f"{task}_{f.name}")
            data_tables = figures_dir / "data_tables"
            if data_tables.exists():
                for f in data_tables.iterdir():
                    if f.is_file() and f.suffix.lower() == ".csv":
                        shutil.copy2(f, tables_out / f"{task}_{f.name}")
        results_src = task_path / "results"
        if results_src.exists():
            shutil.copytree(results_src, results_out / task, dirs_exist_ok=True)

    # Summarize results (v0.2): summary.csv + summary.md for leaderboard comparison
    try:
        from labtrust_gym.benchmarks.summarize import run_summarize
        run_summarize([results_out], out_dir, out_basename="summary")
    except Exception:
        pass

    results_json_path = out_dir / "results.json"
    if all_manifests:
        results_json_path.write_text(
            json.dumps({"manifests": all_manifests, "profile": profile, "seed_base": seed_base}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    else:
        results_json_path.write_text(json.dumps({"profile": profile, "seed_base": seed_base}, indent=2), encoding="utf-8")

    ts = fixed_timestamp
    if ts is None and seed_base is not None:
        ts = "2025-01-01T00:00:00+00:00"
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    metadata = {
        "git_sha": _git_commit_hash(repo_root),
        "partner_id": partner_id,
        "policy_fingerprint": policy_fingerprint,
        "seed_base": seed_base,
        "profile": profile,
        "timestamp": ts,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    card_content = _render_benchmark_card_template(repo_root, metadata)
    (out_dir / "BENCHMARK_CARD.md").write_text(card_content, encoding="utf-8")

    exclude = [] if include_repro_dir else [REPRO_DIR_NAME]
    files_with_hashes = _collect_files_with_hashes(out_dir, exclude_dirs=exclude)
    manifest = {
        "version": MANIFEST_VERSION,
        "files": files_with_hashes,
    }
    (out_dir / "MANIFEST.v0.1.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if not include_repro_dir and repro_dir.exists():
        shutil.rmtree(repro_dir)

    return out_dir
