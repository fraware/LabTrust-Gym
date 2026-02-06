"""
Load official baseline registry: task -> baseline_id for generate-official-baselines.

Registry file: benchmarks/baseline_registry.v0.1.yaml
Result filename suffix: baseline_id with _v1 stripped
(e.g. scripted_ops_v1 -> scripted_ops).
"""

from __future__ import annotations

from pathlib import Path


def _baseline_id_to_suffix(baseline_id: str) -> str:
    """Map baseline_id to result filename suffix (scripted_ops_v1 -> scripted_ops)."""
    if baseline_id.endswith("_v1"):
        return baseline_id[:-3]
    return baseline_id


def load_official_baseline_registry(
    repo_root: Path,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """
    Load baseline_registry.v0.1.yaml from repo_root/benchmarks/.

    Returns (tasks_in_order, task_to_baseline_id, task_to_result_suffix).
    If file is missing, returns default mapping: TaskA/B/C/E -> scripted_ops_v1,
    TaskD -> adversary_v1, TaskF -> insider_v1.
    """
    default_tasks = ["TaskA", "TaskB", "TaskC", "TaskD", "TaskE", "TaskF"]
    default_baseline: dict[str, str] = {
        "TaskA": "scripted_ops_v1",
        "TaskB": "scripted_ops_v1",
        "TaskC": "scripted_ops_v1",
        "TaskD": "adversary_v1",
        "TaskE": "scripted_ops_v1",
        "TaskF": "insider_v1",
    }
    default_suffix: dict[str, str] = {task: _baseline_id_to_suffix(bid) for task, bid in default_baseline.items()}

    registry_path = repo_root / "benchmarks" / "baseline_registry.v0.1.yaml"
    if not registry_path.exists():
        return default_tasks, default_baseline, default_suffix

    try:
        import yaml

        data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        data = data or {}
    except Exception:
        return default_tasks, default_baseline, default_suffix

    entries = data.get("official_tasks") or []
    tasks_in_order: list[str] = []
    task_to_baseline_id: dict[str, str] = {}
    for ent in entries:
        task = ent.get("task")
        baseline_id = ent.get("baseline_id")
        if task and baseline_id:
            tasks_in_order.append(str(task))
            task_to_baseline_id[str(task)] = str(baseline_id)
    task_to_suffix = {t: _baseline_id_to_suffix(bid) for t, bid in task_to_baseline_id.items()}
    if not tasks_in_order:
        return default_tasks, default_baseline, default_suffix
    return tasks_in_order, task_to_baseline_id, task_to_suffix
