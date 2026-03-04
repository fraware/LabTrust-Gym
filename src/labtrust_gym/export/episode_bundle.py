"""
Episode bundle: episode log + METHOD_TRACE + coord_decisions -> one JSON.

Produces episode_bundle.v0.1 for the simulation viewer. Groups episode JSONL
by t_s, merges METHOD_TRACE and coord_decisions by t_step, attaches lab_design.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.logging.lab_design import export_lab_design_json

BUNDLE_VERSION = "0.1"


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file; return list of dicts. Skips empty lines."""
    entries: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def load_episode_log(path: Path) -> list[dict[str, Any]]:
    """Load episode log JSONL; return list of step entries (one per agent per step)."""
    return _parse_jsonl(path)


def load_method_trace(path: Path) -> dict[int, dict[str, Any]]:
    """Load METHOD_TRACE.jsonl; return map t_step -> trace event."""
    lines = _parse_jsonl(path)
    out: dict[int, dict[str, Any]] = {}
    for ev in lines:
        t = ev.get("t_step")
        if t is not None:
            out[int(t)] = ev
    return out


def load_coord_decisions(path: Path) -> dict[int, dict[str, Any]]:
    """Load coord_decisions.jsonl; return t_step -> contract record."""
    lines = _parse_jsonl(path)
    out: dict[int, dict[str, Any]] = {}
    for i, rec in enumerate(lines):
        t = rec.get("t_step")
        if t is not None:
            out[int(t)] = rec
        else:
            out[i] = rec
    return out


def build_bundle(
    episode_entries: list[dict[str, Any]],
    method_trace_by_step: dict[int, dict[str, Any]] | None = None,
    coord_decisions_by_step: dict[int, dict[str, Any]] | None = None,
    lab_design: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build episode_bundle.v0.1 dict from parsed data.

    Groups episode_entries by t_s into steps; merges method_trace and
    coord_decision by step index (0-based). Derives agents from entries.
    """
    method_trace_by_step = method_trace_by_step or {}
    coord_decisions_by_step = coord_decisions_by_step or {}
    lab_design = lab_design or export_lab_design_json()

    # Group by t_s (stable order)
    by_ts: dict[int, list[dict[str, Any]]] = {}
    for e in episode_entries:
        t_s = int(e.get("t_s", 0))
        if t_s not in by_ts:
            by_ts[t_s] = []
        by_ts[t_s].append(e)

    sorted_ts = sorted(by_ts.keys())
    agents_set: set[str] = set()
    for e in episode_entries:
        aid = e.get("agent_id")
        if aid is not None and str(aid).strip():
            agents_set.add(str(aid))
    agents = sorted(agents_set)

    steps: list[dict[str, Any]] = []
    for step_index, t_s in enumerate(sorted_ts):
        entries = by_ts[t_s]
        step_obj: dict[str, Any] = {
            "stepIndex": step_index,
            "t_s": t_s,
            "entries": entries,
        }
        mt = method_trace_by_step.get(step_index)
        if mt is not None:
            step_obj["method_trace"] = mt
        cd = coord_decisions_by_step.get(step_index)
        if cd is not None:
            step_obj["coord_decision"] = cd
        steps.append(step_obj)

    bundle: dict[str, Any] = {
        "version": BUNDLE_VERSION,
        "lab_design": lab_design,
        "agents": agents,
        "steps": steps,
    }
    if meta:
        bundle["meta"] = meta
    return bundle


def build_bundle_from_run_dir(
    run_dir: Path,
    episode_log_path: Path | None = None,
    method_trace_path: Path | None = None,
    coord_decisions_path: Path | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build bundle from a run directory. Infers paths when not given.

    - episode_log: run_dir/episode_log.jsonl or first run_dir/logs/*.jsonl
    - method_trace: run_dir/METHOD_TRACE.jsonl
    - coord_decisions: run_dir/coord_decisions.jsonl
    """  # noqa: E501
    run_dir = Path(run_dir)
    if episode_log_path is None:
        candidate = run_dir / "episode_log.jsonl"
        if candidate.exists():
            episode_log_path = candidate
        else:
            logs = list(run_dir.glob("logs/*.jsonl"))
            if logs:
                episode_log_path = sorted(logs)[0]
            else:
                raise FileNotFoundError(
                    f"No episode log found in {run_dir}. Expected episode_log.jsonl or logs/*.jsonl"
                )
    else:
        episode_log_path = Path(episode_log_path)

    if not episode_log_path.exists():
        raise FileNotFoundError(str(episode_log_path))

    entries = load_episode_log(episode_log_path)

    mt_path = method_trace_path or run_dir / "METHOD_TRACE.jsonl"
    method_trace_by_step: dict[int, dict[str, Any]] = {}
    if Path(mt_path).exists():
        method_trace_by_step = load_method_trace(Path(mt_path))

    cd_path = coord_decisions_path or run_dir / "coord_decisions.jsonl"
    coord_by_step: dict[int, dict[str, Any]] = {}
    if Path(cd_path).exists():
        coord_by_step = load_coord_decisions(Path(cd_path))

    build_meta: dict[str, Any] = {
        "source_log": str(episode_log_path),
        "source_run_dir": str(run_dir),
    }
    if meta:
        build_meta.update(meta)

    return build_bundle(
        entries,
        method_trace_by_step=method_trace_by_step,
        coord_decisions_by_step=coord_by_step,
        meta=build_meta,
    )


def write_bundle(bundle: dict[str, Any], path: Path) -> None:
    """Write bundle as JSON to path. Creates parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(bundle, sort_keys=True, indent=2)
    path.write_text(text, encoding="utf-8")
