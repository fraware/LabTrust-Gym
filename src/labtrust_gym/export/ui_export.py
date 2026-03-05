"""
UI export: normalized UI-ready JSON from a labtrust run (quick-eval or package-release).

Produces a zip bundle containing:
- index.json (episodes/tasks/baselines, file refs)
- events.json (normalized gate outcomes from episode logs)
- receipts_index.json (task -> path, receipt_files)
- reason_codes.json (registry from policy)

See docs/ui_data_contract.md for contract and schema version handling.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from labtrust_gym.export.coordination_graphs import (
    GRAPH_ARTIFACT_LABELS,
    build_coordination_graphs,
)

UI_BUNDLE_VERSION = "0.1"

# Stable event field names (contract)
EVENT_FIELDS = (
    "t_s",
    "agent_id",
    "action_type",
    "status",
    "blocked_reason_code",
    "emits",
    "violations",
    "token_consumed",
    "event_id",
)


def _detect_run_type(run_dir: Path) -> str:
    """Return 'quick_eval', 'package_release', or 'full_pipeline' based on directory layout."""
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory does not exist: {run_dir}")
    # package-release: _baselines, _repr, _study, metadata.json, RELEASE_NOTES.md
    has_release_dirs = (
        (run_dir / "_baselines").is_dir() or (run_dir / "_repr").is_dir() or (run_dir / "_study").is_dir()
    )
    if has_release_dirs:
        return "package_release"
    if (run_dir / "metadata.json").exists() or (run_dir / "RELEASE_NOTES.md").exists():
        return "package_release"
    # full-pipeline (hospital lab): baselines/, SECURITY/ or SAFETY_CASE/, optional coordination_pack/
    has_baselines = (run_dir / "baselines").is_dir()
    has_security_or_safety = (run_dir / "SECURITY").is_dir() or (run_dir / "SAFETY_CASE").is_dir()
    if has_baselines and has_security_or_safety:
        return "full_pipeline"
    # quick-eval: throughput_sla.json, adversarial_disruption.json, multi_site_stat.json and logs/
    if (run_dir / "throughput_sla.json").exists() and (run_dir / "logs").is_dir():
        return "quick_eval"
    # Fallback: if we have any Task*.json + logs, treat as quick_eval shape
    task_jsons = list(run_dir.glob("Task*.json"))
    if task_jsons and (run_dir / "logs").is_dir():
        return "quick_eval"
    raise ValueError(
        f"Unrecognized run layout under {run_dir}. "
        "Expected labtrust_runs/quick_eval_* (throughput_sla.json, logs/), "
        "package-release (_baselines, _repr, _study, receipts/), or "
        "full-pipeline (baselines/, SECURITY/ or SAFETY_CASE/)."
    )


def _normalize_event(raw: dict[str, Any], task: str = "", episode_index: int = 0) -> dict[str, Any]:
    """Normalize one JSONL step line to stable UI event fields."""
    out: dict[str, Any] = {}
    for k in EVENT_FIELDS:
        if k in raw:
            out[k] = raw[k]
        elif k == "emits":
            out[k] = raw.get("emits") or []
        elif k == "violations":
            out[k] = raw.get("violations") or []
        elif k == "token_consumed":
            out[k] = raw.get("token_consumed") or []
        else:
            out[k] = None
    out["task"] = task
    out["episode_index"] = episode_index
    out["episode_key"] = f"{task}_{episode_index}"
    return out


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL file; return list of dicts."""
    lines: list[dict[str, Any]] = []
    if not path.is_file():
        return lines
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return lines


def _get_pipeline_mode_from_run(
    run_dir: Path,
    run_type: str,
    tasks: list[str],
) -> str | None:
    """Extract pipeline_mode from run dir: metadata.json (package_release) or first Task*.json (quick_eval)."""
    fields = _get_pipeline_fields_from_run(run_dir, run_type, tasks)
    return fields.get("pipeline_mode")


def _get_pipeline_fields_from_run(
    run_dir: Path,
    run_type: str,
    tasks: list[str],
) -> dict[str, Any]:
    """
    Extract pipeline display fields from run dir for UI/index.
    Returns dict with pipeline_mode, llm_backend_id, llm_model_id, allow_network (when present).
    """
    out: dict[str, Any] = {}
    if run_type == "full_pipeline":
        # pack_manifest.json or first baselines/results/*.json
        manifest_path = run_dir / "pack_manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if "pipeline_mode" in data:
                    out["pipeline_mode"] = data["pipeline_mode"]
                if "allow_network" in data:
                    out["allow_network"] = data["allow_network"]
            except (json.JSONDecodeError, OSError):
                pass
        bl_results = run_dir / "baselines" / "results"
        if bl_results.is_dir():
            for res_path in sorted(bl_results.glob("*.json")):
                if res_path.name.startswith("metadata"):
                    continue
                try:
                    data = json.loads(res_path.read_text(encoding="utf-8"))
                    for key in (
                        "pipeline_mode",
                        "llm_backend_id",
                        "llm_model_id",
                        "allow_network",
                    ):
                        if key in data:
                            out[key] = data[key]
                except (json.JSONDecodeError, OSError):
                    pass
                break
        return out
    if run_type == "package_release":
        meta_path = run_dir / "metadata.json"
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                for key in (
                    "pipeline_mode",
                    "llm_backend_id",
                    "llm_model_id",
                    "allow_network",
                ):
                    if key in data:
                        out[key] = data[key]
                return out
            except (json.JSONDecodeError, OSError):
                pass
        # Fallback: first results.json under _repr
        repr_dir = run_dir / "_repr"
        if repr_dir.is_dir():
            for task_dir in sorted(repr_dir.iterdir()):
                if not task_dir.is_dir():
                    continue
                res_path = task_dir / "results.json"
                if res_path.exists():
                    try:
                        data = json.loads(res_path.read_text(encoding="utf-8"))
                        for key in (
                            "pipeline_mode",
                            "llm_backend_id",
                            "llm_model_id",
                            "allow_network",
                        ):
                            if key in data:
                                out[key] = data[key]
                    except (json.JSONDecodeError, OSError):
                        pass
                    break
        return out
    for task in tasks:
        res_path = run_dir / f"{task}.json"
        if res_path.exists():
            try:
                data = json.loads(res_path.read_text(encoding="utf-8"))
                for key in (
                    "pipeline_mode",
                    "llm_backend_id",
                    "llm_model_id",
                    "allow_network",
                ):
                    if key in data:
                        out[key] = data[key]
            except (json.JSONDecodeError, OSError):
                pass
            break
    return out


def _collect_quick_eval(
    run_dir: Path,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect tasks, episodes index, and receipt entries for quick-eval layout."""
    tasks: list[str] = []
    episodes: list[dict[str, Any]] = []
    receipts_index: list[dict[str, Any]] = []
    logs_dir = run_dir / "logs"
    # Support both Task*.json and task-named results (e.g. throughput_sla.json)
    result_globs = list(run_dir.glob("Task*.json")) or list(run_dir.glob("*.json"))
    for res_path in sorted(result_globs):
        task = res_path.stem
        tasks.append(task)
        try:
            data = json.loads(res_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        eps = data.get("episodes") or []
        log_path = logs_dir / f"{task}.jsonl"
        for ep_idx in range(len(eps)):
            episodes.append(
                {
                    "task": task,
                    "episode_index": ep_idx,
                    "results_ref": str(res_path.relative_to(run_dir)),
                    "log_ref": (str(log_path.relative_to(run_dir)) if log_path.exists() else None),
                    "receipts_ref": None,
                }
            )
    return tasks, episodes, receipts_index


def _collect_full_pipeline(
    run_dir: Path,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """
    Collect tasks, episodes, receipts_index, baselines for full-pipeline layout.

    Layout: baselines/results/*.json, optional coordination_pack/, SECURITY/, SAFETY_CASE/.
    One episode entry per episode in each result file (episode_index 0..N-1).
    Receipts are not produced by full_pipeline runs (no _repr/receipts/); only
    package-release runs produce EvidenceBundle receipts.
    """
    tasks: list[str] = []
    episodes: list[dict[str, Any]] = []
    receipts_index: list[dict[str, Any]] = []
    baselines: list[str] = []

    bl_results = run_dir / "baselines" / "results"
    if not bl_results.is_dir():
        return tasks, episodes, receipts_index, baselines

    for res_path in sorted(bl_results.glob("*.json")):
        if res_path.name in ("metadata.json", "METHOD_TRACE.jsonl"):
            continue
        task = res_path.stem
        if task not in tasks:
            tasks.append(task)
        baselines.append(task)
        # Episode count from result file so index has episode_index 0, 1, 2, ...
        num_eps = 1
        try:
            data = json.loads(res_path.read_text(encoding="utf-8"))
            eps = data.get("episodes") or []
            num_eps = max(1, len(eps))
        except (json.JSONDecodeError, OSError):
            pass
        # Log only for single-episode runs; multi-episode JSONL has no boundaries so we backfill only
        log_ref_val: str | None = None
        if num_eps == 1:
            log_candidate = res_path.parent / f"{res_path.stem}_episodes.jsonl"
            if not log_candidate.exists():
                log_candidate = res_path.parent / "episodes.jsonl"
            if log_candidate.exists():
                log_ref_val = str(log_candidate.relative_to(run_dir))
        results_ref = str(res_path.relative_to(run_dir))
        for ep_idx in range(num_eps):
            episodes.append(
                {
                    "task": task,
                    "episode_index": ep_idx,
                    "results_ref": results_ref,
                    "log_ref": log_ref_val,
                    "receipts_ref": None,
                    "episode_key": f"{task}_{ep_idx}",
                }
            )

    # coordination_pack/pack_results/* are not added as tasks to keep the bundle small;
    # coordination_artifacts (pack_summary.csv, pack_gate.md, etc.) are still collected
    # when present under run_dir/coordination_pack/ via _collect_coordination_artifacts().

    return tasks, episodes, receipts_index, baselines


def _collect_package_release(
    run_dir: Path,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Collect tasks, episodes, receipts_index, baselines for package-release layout."""
    tasks: list[str] = []
    episodes: list[dict[str, Any]] = []
    receipts_index: list[dict[str, Any]] = []
    baselines: list[str] = []

    # _repr/<task>/: results.json, episodes.jsonl; receipts/<task>/
    repr_dir = run_dir / "_repr"
    if repr_dir.is_dir():
        for task_dir in sorted(repr_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            task = task_dir.name
            if task not in tasks:
                tasks.append(task)
            res_path = task_dir / "results.json"
            log_path = task_dir / "episodes.jsonl"
            if res_path.exists():
                try:
                    data = json.loads(res_path.read_text(encoding="utf-8"))
                    eps = data.get("episodes") or []
                except (json.JSONDecodeError, OSError):
                    eps = [{}]
            else:
                eps = [{}] if log_path.exists() else []
            for ep_idx in range(len(eps)):
                episodes.append(
                    {
                        "task": task,
                        "episode_index": ep_idx,
                        "results_ref": str(res_path.relative_to(run_dir)),
                        "log_ref": (str(log_path.relative_to(run_dir)) if log_path.exists() else None),
                        "receipts_ref": f"receipts/{task}",
                    }
                )
            # Receipts for this task
            rec_dir = run_dir / "receipts" / task
            if rec_dir.is_dir():
                receipt_files: list[str] = []
                bundle_dir = rec_dir / "EvidenceBundle.v0.1"
                if bundle_dir.is_dir():
                    for f in bundle_dir.iterdir():
                        if f.is_file() and f.suffix == ".json":
                            receipt_files.append(f.name)
                for f in rec_dir.iterdir():
                    if f.is_file() and f.name.startswith("receipt_") and f.suffix == ".json":
                        receipt_files.append(f.name)
                if receipt_files:
                    receipts_index.append(
                        {
                            "task": task,
                            "path": str(rec_dir.relative_to(run_dir)),
                            "receipt_files": sorted(receipt_files),
                        }
                    )

    # _baselines/results/*.json
    bl_dir = run_dir / "_baselines"
    if bl_dir.is_dir():
        bl_results = bl_dir / "results"
        if bl_results.is_dir():
            for res_path in sorted(bl_results.glob("*.json")):
                task = res_path.stem
                if task not in tasks:
                    tasks.append(task)
                baselines.append(task)
                episodes.append(
                    {
                        "task": task,
                        "episode_index": 0,
                        "results_ref": str(res_path.relative_to(run_dir)),
                        "log_ref": None,
                        "receipts_ref": None,
                    }
                )

    return tasks, episodes, receipts_index, baselines


def _event_from_episode_summary(
    task: str,
    episode_index: int,
    episode_data: dict[str, Any],
) -> dict[str, Any]:
    """Build one UI event from a results JSON episode entry (no step log)."""
    out: dict[str, Any] = {
        "task": task,
        "episode_index": episode_index,
        "episode_key": f"{task}_{episode_index}",
        "event_id": "episode_summary",
    }
    for k in EVENT_FIELDS:
        out[k] = None
    metrics = episode_data.get("metrics") or {}
    out["episode_metrics"] = dict(metrics)
    if "llm_episode" in episode_data:
        out["llm_episode"] = episode_data["llm_episode"]
    if "seed" in episode_data:
        out["seed"] = episode_data["seed"]
    return out


def _build_events(
    run_dir: Path,
    run_type: str,
    tasks: list[str],
    episodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build normalized events.json from episode logs; backfill from results JSON when no log."""
    events: list[dict[str, Any]] = []
    for ep in episodes:
        task = ep.get("task", "")
        ep_idx = ep.get("episode_index", 0)
        log_ref = ep.get("log_ref")
        if log_ref:
            log_path = run_dir / log_ref
            for raw in _load_jsonl(log_path):
                events.append(_normalize_event(raw, task=task, episode_index=ep_idx))
            continue
        # No episode log (e.g. official pack run before logs were written): backfill from results JSON
        results_ref = ep.get("results_ref")
        if run_type != "full_pipeline" or not results_ref:
            continue
        res_path = run_dir / results_ref
        if not res_path.is_file():
            continue
        try:
            data = json.loads(res_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        eps = data.get("episodes") or []
        if ep_idx < len(eps):
            events.append(_event_from_episode_summary(task, ep_idx, eps[ep_idx]))
    return events


# Stable key for coordination telemetry in UI bundle (contract v0.1)
COORD_TELEMETRY_KEY = "coord_telemetry"

# Coordination pack / lab report artifacts to include when present (contract v0.1)
COORDINATION_ARTIFACT_REFS = [
    ("pack_summary.csv", "Pack summary"),
    ("pack_gate.md", "Pack gate"),
    ("SECURITY/coordination_risk_matrix.csv", "Coordination risk matrix (CSV)"),
    ("SECURITY/coordination_risk_matrix.md", "Coordination risk matrix (MD)"),
    ("LAB_COORDINATION_REPORT.md", "Lab coordination report"),
    ("COORDINATION_DECISION.v0.1.json", "Coordination decision (JSON)"),
    ("COORDINATION_DECISION.md", "Coordination decision (MD)"),
    ("summary/sota_leaderboard.md", "SOTA leaderboard"),
    ("summary/sota_leaderboard_full.md", "SOTA leaderboard (full metrics)"),
    ("summary/sota_leaderboard_full.csv", "SOTA leaderboard full CSV"),
    ("summary/method_class_comparison.md", "Method class comparison"),
]


def _collect_coord_telemetry(
    run_dir: Path,
    episodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For each episode with a log_ref, if coord_decisions.jsonl exists in the same
    directory, add an entry { episode_key, coord_decisions_ref } and return list.
    """
    refs: list[dict[str, Any]] = []
    for ep in episodes:
        log_ref = ep.get("log_ref")
        if not log_ref:
            continue
        log_path = run_dir / log_ref
        coord_path = log_path.parent / "coord_decisions.jsonl"
        if not coord_path.is_file():
            continue
        episode_key = ep.get("episode_key") or f"{ep.get('task', '')}_{ep.get('episode_index', 0)}"
        refs.append(
            {
                "episode_key": episode_key,
                "coord_decisions_ref": f"{COORD_TELEMETRY_KEY}/{episode_key}.jsonl",
            }
        )
    return refs


def _collect_coordination_artifacts(run_dir: Path) -> list[dict[str, str]]:
    """
    Collect paths to coordination pack / lab report artifacts when present.
    Checks run_dir and run_dir/coordination_pack/. Returns list of { path, label }
    with path relative to run_dir for index; actual file may be under coordination_pack/.
    """
    out: list[dict[str, str]] = []
    for rel_path, label in COORDINATION_ARTIFACT_REFS:
        full = run_dir / rel_path
        if full.is_file():
            out.append({"path": rel_path, "label": label})
            continue
        # package-release with coordination_pack subdir
        coord_pack = run_dir / "coordination_pack" / rel_path
        if coord_pack.is_file():
            out.append({"path": f"coordination_pack/{rel_path}", "label": label})
    return out


def _load_reason_codes_json(repo_root: Path) -> dict[str, Any]:
    """Load reason code registry and return UI shape: { version, codes }."""
    reg_path = repo_root / "policy" / "reason_codes" / "reason_code_registry.v0.1.yaml"
    if not reg_path.exists():
        return {"version": "0.1", "codes": {}}
    try:
        from labtrust_gym.policy.reason_codes import load_reason_code_registry

        codes = load_reason_code_registry(reg_path)
        return {"version": "0.1", "codes": codes}
    except Exception:
        return {"version": "0.1", "codes": {}}


def export_ui_bundle(
    run_dir: Path,
    out_zip_path: Path,
    repo_root: Path | None = None,
) -> Path:
    """
    Export a UI-ready zip from a labtrust run directory.

    - run_dir: path to labtrust_runs/quick_eval_*, package-release output, or full-pipeline (baselines/, SECURITY/, coordination_pack/)
    - out_zip_path: path to output .zip (e.g. ui_bundle.zip)
    - repo_root: policy root (for reason_codes); default from get_repo_root()

    Writes: index.json, events.json, receipts_index.json, reason_codes.json
    """
    if repo_root is None:
        from labtrust_gym.config import get_repo_root

        repo_root = get_repo_root()

    run_dir = run_dir.resolve()
    out_zip_path = out_zip_path.resolve()
    run_type = _detect_run_type(run_dir)

    if run_type == "quick_eval":
        tasks, episodes, receipts_index = _collect_quick_eval(run_dir)
        baselines = []
    elif run_type == "full_pipeline":
        tasks, episodes, receipts_index, baselines = _collect_full_pipeline(run_dir)
    else:
        tasks, episodes, receipts_index, baselines = _collect_package_release(run_dir)

    events = _build_events(run_dir, run_type, tasks, episodes)
    coord_telemetry_refs = _collect_coord_telemetry(run_dir, episodes)

    pipeline_fields = _get_pipeline_fields_from_run(run_dir, run_type, tasks)
    index = {
        "ui_bundle_version": UI_BUNDLE_VERSION,
        "run_type": run_type,
        "tasks": tasks,
        "episodes": episodes,
        "baselines": baselines,
    }
    if run_type == "full_pipeline" and not receipts_index:
        index["receipts_note"] = (
            "No receipts (expected for full_pipeline runs). "
            "Receipts (EvidenceBundle) are produced by package-release runs only."
        )
    for key in ("pipeline_mode", "llm_backend_id", "llm_model_id", "allow_network"):
        if key in pipeline_fields:
            index[key] = pipeline_fields[key]
    if coord_telemetry_refs:
        index[COORD_TELEMETRY_KEY] = coord_telemetry_refs
    coord_artifacts = _collect_coordination_artifacts(run_dir)
    coord_graphs: list[tuple[str, str]] = []
    if run_type == "full_pipeline" or coord_artifacts:
        coord_graphs = build_coordination_graphs(run_dir)
        for rel_path, _ in coord_graphs:
            label = GRAPH_ARTIFACT_LABELS.get(rel_path, rel_path)
            coord_artifacts.append({"path": rel_path, "label": label})
    if coord_artifacts:
        index["coordination_artifacts"] = coord_artifacts
    reason_codes = _load_reason_codes_json(Path(repo_root))

    out_zip_path.parent.mkdir(parents=True, exist_ok=True)
    graph_paths = {p for p, _ in coord_graphs}
    with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.json", json.dumps(index, indent=2, sort_keys=True))
        for art in coord_artifacts:
            rel = art.get("path", "")
            if not rel:
                continue
            if rel in graph_paths:
                html = next(h for p, h in coord_graphs if p == rel)
                zf.writestr(f"coordination/{rel}", html)
            else:
                full = run_dir / rel
                if full.is_file():
                    zf.write(full, f"coordination/{rel}")
        zf.writestr("events.json", json.dumps(events, indent=2, sort_keys=True))
        zf.writestr("receipts_index.json", json.dumps(receipts_index, indent=2, sort_keys=True))
        zf.writestr("reason_codes.json", json.dumps(reason_codes, indent=2, sort_keys=True))
        for ref in coord_telemetry_refs:
            episode_key = ref.get("episode_key", "")
            coord_ref = ref.get("coord_decisions_ref", "")
            if not episode_key or not coord_ref:
                continue
            ep = next(
                (
                    e
                    for e in episodes
                    if (e.get("episode_key") or f"{e.get('task', '')}_{e.get('episode_index', 0)}") == episode_key
                ),
                None,
            )
            if ep and ep.get("log_ref"):
                coord_path = run_dir / Path(ep["log_ref"]).parent / "coord_decisions.jsonl"
                if coord_path.is_file():
                    zf.writestr(coord_ref, coord_path.read_text(encoding="utf-8"))

    return out_zip_path
