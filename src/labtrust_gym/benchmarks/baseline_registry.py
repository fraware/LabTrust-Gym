"""
Load the official baseline registry (task -> baseline_id).

Reads benchmarks/baseline_registry.v0.1.yaml to map each task to a baseline
agent (e.g. scripted_ops_v1, adversary_v1). Used when generating official
baseline results; result filename suffix is baseline_id with _v1 stripped.
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
    If file is missing, returns default mapping: throughput_sla/stat_insertion/qc_cascade/multi_site_stat -> scripted_ops_v1,
    adversarial_disruption -> adversary_v1, insider_key_misuse -> insider_v1.
    """
    default_tasks = [
        "throughput_sla",
        "stat_insertion",
        "qc_cascade",
        "adversarial_disruption",
        "multi_site_stat",
        "insider_key_misuse",
    ]
    default_baseline: dict[str, str] = {
        "throughput_sla": "scripted_ops_v1",
        "stat_insertion": "scripted_ops_v1",
        "qc_cascade": "scripted_ops_v1",
        "adversarial_disruption": "adversary_v1",
        "multi_site_stat": "scripted_ops_v1",
        "insider_key_misuse": "insider_v1",
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
