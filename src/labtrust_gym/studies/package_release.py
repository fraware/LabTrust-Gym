"""
Release candidate research artifact: reproduce + export-receipts + export-fhir + make-plots,
then MANIFEST.v0.1.json, BENCHMARK_CARD.md, metadata.json.

Profiles: minimal | full | paper_v0.1 (benchmark-first: baselines + TaskF study + summarize + receipts + FIGURES/TABLES).

Single command: labtrust package-release --profile minimal|full|paper_v0.1 --out <dir> [--seed-base N]
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
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


def _collect_files_with_hashes(
    root: Path, exclude_dirs: Optional[List[str]] = None
) -> List[Dict[str, str]]:
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
            out.append(
                {
                    "path": str(rel).replace("\\", "/"),
                    "sha256": _sha256_file(f),
                }
            )
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
- Transport: TaskE scripted policy emits DISPATCH_TRANSPORT → TRANSPORT_TICK → CHAIN_OF_CUSTODY_SIGN → RECEIVE_TRANSPORT; transport is mandatory and audited.
"""


PAPER_BASELINES_DIR = "_baselines"
PAPER_STUDY_DIR = "_study"
PAPER_REPR_DIR = "_repr"
PAPER_FIGURES_DIR = "FIGURES"
PAPER_TABLES_DIR = "TABLES"
PAPER_EPISODES_BASELINES = 50
PAPER_EPISODES_STUDY_TASKF = 50
OFFICIAL_TASKS = ["TaskA", "TaskB", "TaskC", "TaskD", "TaskE", "TaskF"]


def _deterministic_timestamp(seed_base: int) -> str:
    """Deterministic UTC timestamp when seed_base is provided (epoch + seed_base seconds)."""
    return (
        datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seed_base)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_package_release_paper(
    out_dir: Path,
    repo_root: Path,
    seed_base: int,
    fixed_timestamp: Optional[str] = None,
) -> Path:
    """
    Paper-ready release profile: generate-official-baselines, TaskF strict_signatures study,
    summarize-results across both, export receipts + verify bundle for one run per task,
    RELEASE_NOTES.md, FIGURES/, TABLES/ (summary.csv + paper_table.md).
    Works offline. When seed_base is set, timestamps in metadata are deterministic.
    Set LABTRUST_PAPER_SMOKE=1 to use 1 episode for baselines and 2 for study (fast smoke test).
    """
    import os

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    baselines_dir = out_dir / PAPER_BASELINES_DIR
    study_dir = out_dir / PAPER_STUDY_DIR
    repr_dir = out_dir / PAPER_REPR_DIR
    figures_dir = out_dir / PAPER_FIGURES_DIR
    tables_dir = out_dir / PAPER_TABLES_DIR
    receipts_dir = out_dir / "receipts"
    ts = (
        fixed_timestamp
        if fixed_timestamp is not None
        else _deterministic_timestamp(seed_base)
    )

    smoke = os.environ.get("LABTRUST_PAPER_SMOKE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    episodes_baselines = 1 if smoke else PAPER_EPISODES_BASELINES
    episodes_study = 2 if smoke else PAPER_EPISODES_STUDY_TASKF

    # 1) Generate official baselines into subdir (deterministic when --seed-base provided)
    baselines_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "generate-official-baselines",
            "--out",
            str(baselines_dir),
            "--episodes",
            str(episodes_baselines),
            "--seed",
            str(seed_base),
            "--force",
        ],
        cwd=str(repo_root),
        check=True,
    )

    # 2) TaskF strict_signatures ablation study (episodes >= 50; 2 when smoke)
    study_dir.mkdir(parents=True, exist_ok=True)
    spec_path = study_dir / "study_spec_taskf_strict_signatures.yaml"
    spec = {
        "task": "TaskF",
        "episodes": episodes_study,
        "seed_base": seed_base,
        "timing_mode": "explicit",
        "ablations": {"strict_signatures": [False, True]},
        "agent_config": "scripted_runner",
    }
    import yaml

    spec_path.write_text(
        yaml.dump(spec, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    from labtrust_gym.studies.study_runner import run_study

    run_study(spec_path, study_dir, repo_root=repo_root)

    # 3) Summarize across official + study outputs
    tables_dir.mkdir(parents=True, exist_ok=True)
    from labtrust_gym.benchmarks.summarize import run_summarize

    baseline_results = baselines_dir / "results"
    in_paths: List[Path] = []
    if baseline_results.exists():
        in_paths.extend(baseline_results.glob("*.json"))
    study_results = study_dir / "results"
    if study_results.exists():
        in_paths.extend(study_results.rglob("results.json"))
    if in_paths:
        run_summarize(
            in_paths,
            tables_dir,
            out_basename="summary",
        )
    # Paper table: markdown version of summary for paper (always write for complete artifact)
    paper_table = tables_dir / "paper_table.md"
    summary_md = tables_dir / "summary.md"
    if summary_md.exists():
        paper_table.write_text(
            "# Paper summary table\n\n" + summary_md.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        paper_table.write_text(
            "# Paper summary table\n\nNo summary data (run_summarize had no inputs or failed).",
            encoding="utf-8",
        )

    # 4) Representative run per task: 1 episode with log, export receipts, verify bundle
    repr_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.export.receipts import export_receipts
    from labtrust_gym.export.verify import verify_bundle

    for task in OFFICIAL_TASKS:
        task_repr = repr_dir / task
        task_repr.mkdir(parents=True, exist_ok=True)
        log_path = task_repr / "episodes.jsonl"
        run_benchmark(
            task_name=task,
            num_episodes=1,
            base_seed=seed_base,
            out_path=task_repr / "results.json",
            repo_root=repo_root,
            log_path=log_path,
        )
        rec_task = receipts_dir / task
        rec_task.mkdir(parents=True, exist_ok=True)
        try:
            export_receipts(log_path, rec_task)
        except Exception:
            pass
        bundle_dir = rec_task / "EvidenceBundle.v0.1"
        if bundle_dir.exists():
            try:
                passed, report, _ = verify_bundle(bundle_dir, policy_root=repo_root)
                (rec_task / "verify_report.txt").write_text(report, encoding="utf-8")
            except Exception:
                pass

    # 5) FIGURES: 2–3 canonical plots from TaskF study
    figures_dir.mkdir(parents=True, exist_ok=True)
    try:
        from labtrust_gym.studies.plots import make_plots

        make_plots(study_dir)
        study_figures = study_dir / "figures"
        if study_figures.exists():
            for f in study_figures.iterdir():
                if f.is_file() and f.suffix.lower() in (".png", ".svg"):
                    shutil.copy2(f, figures_dir / f.name)
    except Exception:
        pass

    # 6) RELEASE_NOTES.md
    git_sha = _git_commit_hash(repo_root)
    release_notes = f"""# Paper-ready release (profile paper_v0.1)

## What ran

- **Official baselines**: Tasks A–F, {episodes_baselines} episodes each, seed_base={seed_base}.
- **TaskF study**: strict_signatures ablation (false/true), {episodes_study} episodes per condition, seed_base={seed_base}.
- **Summarize**: combined official + study results → TABLES/summary.csv, TABLES/summary.md, TABLES/paper_table.md.
- **Representative runs**: 1 episode per task with episode log → export receipts → verify bundle (receipts/<task>/).

## Versions and seeds

- Git SHA: {git_sha or 'unknown'}
- Seed base: {seed_base}
- Timestamp (deterministic when seed-base set): {ts}

## Layout

- `_baselines/`: official baseline results (results/, summary.csv, summary.md, metadata.json).
- `_study/`: TaskF strict_signatures study (manifest.json, results/, logs/, figures/).
- `FIGURES/`: canonical plots from TaskF study.
- `TABLES/`: summary.csv, summary.md, paper_table.md.
- `receipts/<task>/`: EvidenceBundle.v0.1 and verify_report.txt per task.
- `_repr/`: one representative run per task (episodes.jsonl, results.json).
"""
    (out_dir / "RELEASE_NOTES.md").write_text(release_notes, encoding="utf-8")

    # 7) metadata.json (deterministic timestamp when seed_base provided)
    metadata = {
        "profile": "paper_v0.1",
        "seed_base": seed_base,
        "timestamp": ts,
        "git_sha": git_sha,
        "episodes_baselines": episodes_baselines,
        "episodes_study_taskf": episodes_study,
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # 8) BENCHMARK_CARD and MANIFEST (optional; keep artifact self-contained)
    card_content = _render_benchmark_card_template(repo_root, metadata)
    (out_dir / "BENCHMARK_CARD.md").write_text(card_content, encoding="utf-8")
    files_with_hashes = _collect_files_with_hashes(out_dir, exclude_dirs=[])
    manifest = {"version": MANIFEST_VERSION, "files": files_with_hashes}
    (out_dir / "MANIFEST.v0.1.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return out_dir


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
    For profile paper_v0.1, run benchmark-first paper-ready pipeline instead.
    Returns release_out directory.
    """
    repo_root = repo_root or Path.cwd()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    seed_base = seed_base if seed_base is not None else 100

    if profile == "paper_v0.1":
        return run_package_release_paper(
            out_dir=out_dir,
            repo_root=Path(repo_root),
            seed_base=seed_base,
            fixed_timestamp=fixed_timestamp,
        )

    repro_dir = out_dir / REPRO_DIR_NAME

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
            json.dumps(
                {
                    "manifests": all_manifests,
                    "profile": profile,
                    "seed_base": seed_base,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    else:
        results_json_path.write_text(
            json.dumps({"profile": profile, "seed_base": seed_base}, indent=2),
            encoding="utf-8",
        )

    ts = fixed_timestamp
    if ts is None and seed_base is not None:
        ts = _deterministic_timestamp(seed_base)
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
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )

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
