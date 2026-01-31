"""
Benchmark tasks: initial_state generator, episode length, scripted vs external, reward_config.

Each task is deterministic given seed for reproducibility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Default agent list for PZ env (ops_0, runner_0, runner_1, qc_0, supervisor_0)
DEFAULT_AGENTS_PZ = [
    "ops_0",
    "runner_0",
    "runner_1",
    "qc_0",
    "supervisor_0",
]
DEFAULT_AGENTS_ENGINE = [
    "A_OPS_0",
    "A_RUNNER_0",
    "A_RUNNER_1",
    "A_QC_0",
    "A_SUPERVISOR_0",
]
DEFAULT_ZONES = [
    "Z_ANALYZER_HALL_A",
    "Z_SORTING_LANES",
    "Z_SORTING_LANES",
    "Z_QC_SUPERVISOR",
    "Z_QC_SUPERVISOR",
]


def _make_agents(
    zone_overrides: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    zone_overrides = zone_overrides or {}
    out = []
    for i, (eid, z) in enumerate(zip(DEFAULT_AGENTS_ENGINE, DEFAULT_ZONES)):
        zone = zone_overrides.get(DEFAULT_AGENTS_PZ[i], z)
        out.append({"agent_id": eid, "zone_id": zone})
    return out


def _specimen_template(
    specimen_id: str,
    status: str = "arrived_at_reception",
    panel_id: str = "BIOCHEM_PANEL_CORE",
    arrival_ts_s: int = 0,
) -> Dict[str, Any]:
    return {
        "specimen_id": specimen_id,
        "patient_identifiers_hash": f"pid:hash:{specimen_id}",
        "collection_ts_s": 0,
        "arrival_ts_s": arrival_ts_s,
        "panel_id": panel_id,
        "container_type": "SERUM_SST",
        "specimen_type": "SERUM",
        "integrity_flags": {
            "leak": False,
            "clot": False,
            "hemolysis": False,
            "insufficient_volume": False,
            "label_issue": False,
        },
        "fill_ratio_ok": True,
        "hazard_flag": False,
        "separated_ts_s": None,
        "temp_band": "AMBIENT_20_25",
        "status": status,
    }


@dataclass
class BenchmarkTask:
    """Task: initial_state, episode length, agents, reward_config."""

    name: str
    max_steps: int
    scripted_agents: List[str]
    reward_config: Dict[str, Any]
    sla_turnaround_s: Optional[int] = None  # for on-time rate (accept->release)
    attack_start_step: Optional[int] = None  # TaskD: first adversarial action step for detection_latency_s

    def get_initial_state(self, seed: int) -> Dict[str, Any]:
        """Deterministic initial_state given seed. Override in subclasses."""
        rng = random.Random(seed)
        n_specimens = 2 + rng.randint(0, 3)
        specimens = []
        for i in range(n_specimens):
            sid = f"S{seed}_{i}"
            specimens.append(
                _specimen_template(sid, arrival_ts_s=rng.randint(0, 100))
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
        }


class TaskA_ThroughputSLA(BenchmarkTask):
    """Throughput under SLA: routine load, measure released count and turnaround."""

    def __init__(self) -> None:
        super().__init__(
            name="TaskA_ThroughputSLA",
            max_steps=80,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={"throughput_reward": 1.0},
            sla_turnaround_s=3600,
        )

    def get_initial_state(self, seed: int) -> Dict[str, Any]:
        rng = random.Random(seed)
        n = 3 + (seed % 3)
        specimens = []
        for i in range(n):
            specimens.append(
                _specimen_template(
                    f"TA_{seed}_{i}", arrival_ts_s=rng.randint(0, 50)
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
        }


class TaskB_STATInsertionUnderLoad(BenchmarkTask):
    """STAT under load; measure prioritization."""

    def __init__(self) -> None:
        super().__init__(
            name="TaskB_STATInsertionUnderLoad",
            max_steps=120,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={
                "throughput_reward": 1.0,
                "violation_penalty": 0.1,
            },
            sla_turnaround_s=1800,
        )

    def get_initial_state(self, seed: int) -> Dict[str, Any]:
        rng = random.Random(seed)
        specimens = []
        for i in range(4 + (seed % 2)):
            sid = f"TB_{seed}_{i}"
            specimens.append(
                _specimen_template(sid, arrival_ts_s=rng.randint(0, 80))
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
        }


class TaskC_QCFailCascade(BenchmarkTask):
    """QC fail on one device; routing and cascade."""

    def __init__(self) -> None:
        super().__init__(
            name="TaskC_QCFailCascade",
            max_steps=100,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={},
            sla_turnaround_s=None,
        )

    def get_initial_state(self, seed: int) -> Dict[str, Any]:
        rng = random.Random(seed)
        specimens = []
        for i in range(2 + (seed % 2)):
            specimens.append(
                _specimen_template(f"TC_{seed}_{i}", arrival_ts_s=rng.randint(0, 30))
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
        }


def _make_agents_with_adversary(
    zone_overrides: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """Agents for TaskD: ops, runners, qc, supervisor, adversary_0."""
    base = _make_agents(zone_overrides)
    base.append({"agent_id": "A_ADVERSARY_0", "zone_id": "Z_SORTING_LANES"})
    return base


class TaskD_AdversarialDisruption(BenchmarkTask):
    """Adversarial disruption: scripted_ops + scripted_runner + adversary_0.
    Metrics: time-to-detection, blast radius, attribution (audit has agent_id + action chain).
    """

    def __init__(self) -> None:
        super().__init__(
            name="TaskD_AdversarialDisruption",
            max_steps=80,
            scripted_agents=["ops_0", "runner_0", "runner_1", "adversary_0"],
            reward_config={
                "throughput_reward": 0.5,
                "violation_penalty": 0.2,
                "blocked_penalty": 0.1,
            },
            sla_turnaround_s=3600,
            attack_start_step=2,
        )

    def get_initial_state(self, seed: int) -> Dict[str, Any]:
        rng = random.Random(seed)
        n = 3 + (seed % 2)
        specimens = []
        for i in range(n):
            specimens.append(
                _specimen_template(
                    f"TD_{seed}_{i}", arrival_ts_s=rng.randint(0, 50)
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents_with_adversary(),
            "specimens": specimens,
            "tokens": [],
        }


_TASK_REGISTRY: Dict[str, type] = {
    "TaskA": TaskA_ThroughputSLA,
    "TaskA_ThroughputSLA": TaskA_ThroughputSLA,
    "TaskB": TaskB_STATInsertionUnderLoad,
    "TaskB_STATInsertionUnderLoad": TaskB_STATInsertionUnderLoad,
    "TaskC": TaskC_QCFailCascade,
    "TaskC_QCFailCascade": TaskC_QCFailCascade,
    "TaskD": TaskD_AdversarialDisruption,
    "TaskD_AdversarialDisruption": TaskD_AdversarialDisruption,
}


def get_task(name: str) -> BenchmarkTask:
    """Return task instance by name."""
    cls = _TASK_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown task: {name}. Known: {list(_TASK_REGISTRY.keys())}"
        )
    return cls()
