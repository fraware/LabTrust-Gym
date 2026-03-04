"""
Benchmark task definitions: initial state, episode length, and reward config.

Each task supplies a deterministic initial_state generator (given seed),
episode length, and whether agents are scripted or external. Used by the
benchmark runner to run N episodes per task and collect metrics.
Reproducibility: same seed yields the same initial state and episode layout.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from labtrust_gym.benchmarks.coordination_scale import (
    CoordinationScaleConfig,
    generate_scaled_initial_state,
)

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
    zone_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
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
    priority_class: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
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
    if priority_class is not None:
        out["priority_class"] = priority_class
    return out


def _sample_arrival_and_n_from_calibration(
    rng: random.Random,
    calibration: dict[str, Any] | None,
    default_n_min: int,
    default_n_max: int,
    default_arrival_max: int,
) -> tuple[int, list[int]]:
    """Return (n_specimens, list of arrival_ts_s). Uses calibration workload_priors when present."""
    if not calibration or not isinstance(calibration.get("workload_priors"), dict):
        n = rng.randint(default_n_min, default_n_max)
        return n, [rng.randint(0, default_arrival_max) for _ in range(n)]
    wp = calibration["workload_priors"]
    n_min = wp.get("n_specimens_min", default_n_min)
    n_max = wp.get("n_specimens_max", default_n_max)
    n = rng.randint(max(0, n_min), max(n_min, n_max))
    mean = wp.get("arrival_mean_s", default_arrival_max // 2)
    scale = max(0.0, wp.get("arrival_scale_s", default_arrival_max // 4))
    arrival_max = wp.get("arrival_max_s")
    if arrival_max is None:
        arrival_max = default_arrival_max
    arrivals = []
    for _ in range(n):
        # Uniform(mean - scale, mean + scale) clamped to [0, arrival_max]
        a = mean + (rng.random() * 2 - 1) * scale
        a = max(0, min(int(a), arrival_max))
        arrivals.append(a)
    return n, arrivals


def _stat_rate_from_calibration(calibration: dict[str, Any] | None) -> float:
    """Return stat_rate in [0, 1] from calibration or 0.0."""
    if not calibration or not isinstance(calibration.get("workload_priors"), dict):
        return 0.0
    rate = calibration["workload_priors"].get("stat_rate", 0.0)
    return max(0.0, min(1.0, float(rate)))


def _default_scale_config() -> CoordinationScaleConfig:
    """Small default scale for CoordinationScale smoke (10 agents, 2 CHEM, 1 site)."""
    return CoordinationScaleConfig(
        num_agents_total=10,
        role_mix={
            "ROLE_RUNNER": 0.4,
            "ROLE_ANALYTICS": 0.3,
            "ROLE_RECEPTION": 0.2,
            "ROLE_QC": 0.05,
            "ROLE_SUPERVISOR": 0.05,
        },
        num_devices_per_type={"CHEM_ANALYZER": 2, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=2.0,
        horizon_steps=200,
        timing_mode="explicit",
        partner_id=None,
    )


@dataclass
class BenchmarkTask:
    """Task: initial_state, episode length, agents, reward_config. timing_mode can be overridden by CLI/spec."""

    name: str
    max_steps: int
    scripted_agents: list[str]
    reward_config: dict[str, Any]
    sla_turnaround_s: int | None = None  # for on-time rate (accept->release)
    attack_start_step: int | None = None  # AdversarialDisruption: first adversarial action step for detection_latency_s
    insider_attack_steps: list[int] | None = (
        None  # InsiderAndKeyMisuse: step indices of insider attack attempts for containment metrics
    )
    timing_mode: str | None = None  # "explicit" | "simulated"; None => use CLI/spec override
    scale_config: CoordinationScaleConfig | None = None  # CoordinationScale / CoordinationRisk

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        """Deterministic initial_state given seed. calibration optional (workload priors)."""
        scale = self.scale_config
        if scale is not None:
            if policy_root is not None:
                root = Path(policy_root)
            else:
                try:
                    from labtrust_gym.config import get_repo_root

                    root = Path(get_repo_root())
                except Exception:
                    root = Path.cwd()
            return generate_scaled_initial_state(scale, root, seed)
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=2, default_n_max=5, default_arrival_max=100
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            sid = f"S{seed}_{i}"
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    sid,
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 100)),
                    priority_class=prio,
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
        }


class ThroughputSla(BenchmarkTask):
    """Throughput under SLA: routine load, measure released count and turnaround."""

    def __init__(self) -> None:
        super().__init__(
            name="throughput_sla",
            max_steps=80,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={
                "throughput_reward": 1.0,
                "schedule_reward": 0.1,
            },
            sla_turnaround_s=3600,
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=3, default_n_max=6, default_arrival_max=50
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TA_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 50)),
                    priority_class=prio,
                    status="accepted",
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
            "reagent_initial_stock": {
                "R_CHEM_CORE": 1000.0,
                "R_HAEM_CORE": 500.0,
                "R_COAG_CORE": 400.0,
            },
        }


class StatInsertionUnderLoad(BenchmarkTask):
    """STAT under load; measure prioritization."""

    def __init__(self) -> None:
        super().__init__(
            name="stat_insertion",
            max_steps=120,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={
                "throughput_reward": 1.0,
                "violation_penalty": 0.1,
            },
            sla_turnaround_s=1800,
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=4, default_n_max=6, default_arrival_max=80
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TB_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 80)),
                    priority_class=prio,
                    status="accepted",
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
            "reagent_initial_stock": {
                "R_CHEM_CORE": 1000.0,
                "R_HAEM_CORE": 500.0,
                "R_COAG_CORE": 400.0,
            },
        }


class QcFailCascade(BenchmarkTask):
    """QC fail on one device; routing and cascade."""

    def __init__(self) -> None:
        super().__init__(
            name="qc_cascade",
            max_steps=100,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={},
            sla_turnaround_s=None,
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=2, default_n_max=4, default_arrival_max=30
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TC_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 30)),
                    priority_class=prio,
                    status="accepted",
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
            "reagent_initial_stock": {
                "R_CHEM_CORE": 1000.0,
                "R_HAEM_CORE": 500.0,
                "R_COAG_CORE": 400.0,
            },
        }


def _make_agents_with_adversary(
    zone_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Agents for AdversarialDisruption: ops, runners, qc, supervisor, adversary_0."""
    base = _make_agents(zone_overrides)
    base.append({"agent_id": "A_ADVERSARY_0", "zone_id": "Z_SORTING_LANES"})
    return base


class AdversarialDisruption(BenchmarkTask):
    """Adversarial disruption: scripted_ops + scripted_runner + adversary_0.
    Metrics: time-to-detection, blast radius, attribution (audit has agent_id + action chain).
    """

    def __init__(self) -> None:
        super().__init__(
            name="adversarial_disruption",
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

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=3, default_n_max=5, default_arrival_max=50
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TD_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 50)),
                    priority_class=prio,
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents_with_adversary(),
            "specimens": specimens,
            "tokens": [],
        }


def _make_agents_with_insider(
    zone_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Agents for InsiderAndKeyMisuse: ops, runner_0, qc, supervisor, adversary_insider_0 (A_INSIDER_0 with limited RBAC)."""
    zone_overrides = zone_overrides or {}
    out = [
        {
            "agent_id": "A_OPS_0",
            "zone_id": zone_overrides.get("ops_0", "Z_ANALYZER_HALL_A"),
        },
        {
            "agent_id": "A_RUNNER_0",
            "zone_id": zone_overrides.get("runner_0", "Z_SORTING_LANES"),
        },
        {
            "agent_id": "A_QC_0",
            "zone_id": zone_overrides.get("qc_0", "Z_QC_SUPERVISOR"),
        },
        {
            "agent_id": "A_SUPERVISOR_0",
            "zone_id": zone_overrides.get("supervisor_0", "Z_QC_SUPERVISOR"),
        },
        {
            "agent_id": "A_INSIDER_0",
            "zone_id": zone_overrides.get("adversary_insider_0", "Z_SORTING_LANES"),
        },
    ]
    return out


class InsiderAndKeyMisuse(BenchmarkTask):
    """Insider + key misuse: adversary_insider_0 with limited RBAC; phases: forbidden action, forged sig, replay, token misuse.
    Metrics: time_to_first_detected_security_violation, fraction_of_attacks_contained, forensic_quality_score.
    """

    def __init__(self) -> None:
        super().__init__(
            name="insider_key_misuse",
            max_steps=50,
            scripted_agents=["ops_0", "runner_0", "adversary_insider_0"],
            reward_config={
                "throughput_reward": 0.3,
                "violation_penalty": 0.2,
                "blocked_penalty": 0.1,
            },
            sla_turnaround_s=3600,
            attack_start_step=2,
            insider_attack_steps=[
                2,
                5,
                8,
                11,
                14,
            ],  # phases 1–5 (forbidden, forged, replay, revoked key, token misuse)
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=2, default_n_max=4, default_arrival_max=50
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TF_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 50)),
                    priority_class=prio,
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents_with_insider(),
            "specimens": specimens,
            "tokens": [],
            "strict_signatures": True,  # so forged/revoked key phases are BLOCKED
        }


class CoordinationScale(BenchmarkTask):
    """Coordination at scale under nominal conditions. Uses scale_config for agents/devices/sites."""

    def __init__(self) -> None:
        scale = _default_scale_config()
        super().__init__(
            name="coord_scale",
            max_steps=scale.horizon_steps,
            scripted_agents=[],  # Filled from scale agents (worker_0, worker_1, ...)
            reward_config={"throughput_reward": 1.0, "violation_penalty": 0.1},
            sla_turnaround_s=3600,
            timing_mode=scale.timing_mode,
            scale_config=scale,
        )


class CoordinationRisk(BenchmarkTask):
    """Coordination under injected risks. Uses scale_config; risk injection via study spec."""

    def __init__(self) -> None:
        scale = _default_scale_config()
        super().__init__(
            name="coord_risk",
            max_steps=scale.horizon_steps,
            scripted_agents=[],
            reward_config={
                "throughput_reward": 0.5,
                "violation_penalty": 0.2,
                "blocked_penalty": 0.1,
            },
            sla_turnaround_s=3600,
            timing_mode=scale.timing_mode,
            scale_config=scale,
        )


class MultiSiteStat(BenchmarkTask):
    """Multi-site: acute node STAT specimens, hub routine queue; transport mandatory and audited.
    At least one specimen originates at SITE_ACUTE and requires dispatch to SITE_HUB.
    Scripted policy: DISPATCH_TRANSPORT -> TRANSPORT_TICK -> CHAIN_OF_CUSTODY_SIGN -> RECEIVE_TRANSPORT.
    """

    def __init__(self) -> None:
        super().__init__(
            name="multi_site_stat",
            max_steps=150,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={
                "throughput_reward": 1.0,
                "violation_penalty": 0.1,
            },
            sla_turnaround_s=2400,
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=3, default_n_max=5, default_arrival_max=100
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TE_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 100)),
                    priority_class=prio,
                )
            )
        transport_required = [
            {
                "specimen_ids": [f"TE_{seed}_0"],
                "origin_site": "SITE_ACUTE",
                "dest_site": "SITE_HUB",
            }
        ]
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
            "transport_required": transport_required,
        }


class DeviceOutageSurge(BenchmarkTask):
    """
    Surge workload + one analyzer outage (maintenance window).
    failure_models.v0.1 defines maintenance; timing_mode simulated.
    Measures p95 TAT impact and RC_DEVICE_MAINT blocks.
    """

    def __init__(self) -> None:
        super().__init__(
            name="device_outage_surge",
            max_steps=200,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={
                "throughput_reward": 1.0,
                "violation_penalty": 0.1,
            },
            sla_turnaround_s=3600,
            timing_mode="simulated",
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        if policy_root is not None:
            root = Path(policy_root)
        else:
            try:
                from labtrust_gym.config import get_repo_root

                root = Path(get_repo_root())
            except Exception:
                root = Path(".")
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=8, default_n_max=12, default_arrival_max=200
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TI_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 150)),
                    priority_class=prio,
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
            "timing_mode": "simulated",
            "policy_root": str(root),
        }


class ReagentStockout(BenchmarkTask):
    """
    Forced reagent shortage: low initial stock causes RC_REAGENT_STOCKOUT,
    hold or reroute per reagent_policy; measures delays and violations.
    """

    def __init__(self) -> None:
        super().__init__(
            name="reagent_stockout",
            max_steps=150,
            scripted_agents=["ops_0", "runner_0", "runner_1"],
            reward_config={
                "throughput_reward": 0.8,
                "violation_penalty": 0.15,
            },
            sla_turnaround_s=3600,
            timing_mode="explicit",
        )

    def get_initial_state(
        self,
        seed: int,
        calibration: dict[str, Any] | None = None,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        if policy_root is not None:
            root = Path(policy_root)
        else:
            try:
                from labtrust_gym.config import get_repo_root

                root = Path(get_repo_root())
            except Exception:
                root = Path(".")
        n, arrivals = _sample_arrival_and_n_from_calibration(
            rng, calibration, default_n_min=5, default_n_max=8, default_arrival_max=80
        )
        stat_rate = _stat_rate_from_calibration(calibration)
        specimens = []
        for i in range(n):
            prio = "STAT" if rng.random() < stat_rate else "ROUTINE"
            specimens.append(
                _specimen_template(
                    f"TJ_{seed}_{i}",
                    arrival_ts_s=(arrivals[i] if i < len(arrivals) else rng.randint(0, 60)),
                    priority_class=prio,
                )
            )
        return {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": _make_agents(),
            "specimens": specimens,
            "tokens": [],
            "policy_root": str(root),
            "reagent_initial_stock": {"R_CHEM_CORE": 20},
        }


_TASK_REGISTRY: dict[str, type] = {
    "throughput_sla": ThroughputSla,
    "stat_insertion": StatInsertionUnderLoad,
    "qc_cascade": QcFailCascade,
    "adversarial_disruption": AdversarialDisruption,
    "multi_site_stat": MultiSiteStat,
    "insider_key_misuse": InsiderAndKeyMisuse,
    "coord_scale": CoordinationScale,
    "coord_risk": CoordinationRisk,
    "device_outage_surge": DeviceOutageSurge,
    "reagent_stockout": ReagentStockout,
}


def register_task(name: str, task_class: type[BenchmarkTask]) -> None:
    """Register a benchmark task by name. Overwrites if present."""
    _TASK_REGISTRY[name] = task_class


def list_tasks() -> list[str]:
    """Return registered task names."""
    return sorted(_TASK_REGISTRY.keys())


def get_task(name: str) -> BenchmarkTask:
    """Return task instance by name."""
    cls = _TASK_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown task: {name}. Known: {list_tasks()}")
    if not callable(cls):
        raise TypeError(
            f"Task {name!r} maps to non-callable {type(cls).__name__!r}; registry entry must be a BenchmarkTask class."
        )
    return cast(BenchmarkTask, cls())
