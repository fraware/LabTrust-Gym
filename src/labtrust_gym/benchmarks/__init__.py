"""
Benchmark harness: tasks, metrics, runner, and official pack.

Provides benchmark tasks (e.g. throughput, STAT insertion, QC cascade),
per-episode metrics, run_benchmark to execute N episodes and write
results.json, and the official benchmark pack for release. Used by the
CLI (run-benchmark, package-release) and by studies.
"""

from __future__ import annotations

from labtrust_gym.benchmarks.metrics import compute_episode_metrics
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.benchmarks.tasks import (
    QcFailCascade,
    StatInsertionUnderLoad,
    ThroughputSla,
    get_task,
    list_tasks,
    register_task,
)

__all__ = [
    "QcFailCascade",
    "StatInsertionUnderLoad",
    "ThroughputSla",
    "get_task",
    "list_tasks",
    "register_task",
    "compute_episode_metrics",
    "run_benchmark",
]
