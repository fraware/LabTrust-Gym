"""
Deterministic scale generator for coordination benchmarks.

Generates large initial_state (agents, devices, zones, sites, specimens, arrival schedule)
from a compact CoordinationScaleConfig and seed. No policy files written to disk.
Same (seed, scale_config, partner_id) yields identical output.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.engine.zones import load_zone_layout as _load_zone_layout_file
from labtrust_gym.policy.loader import load_effective_policy, load_yaml

# Default role IDs used when role_mix is applied (must exist in base RBAC).
DEFAULT_SCALE_ROLES = [
    "ROLE_RECEPTION",
    "ROLE_RUNNER",
    "ROLE_ANALYTICS",
    "ROLE_QC",
    "ROLE_SUPERVISOR",
]

# Zone IDs used for placement when scaling (subset of base layout).
DEFAULT_SCALE_ZONES = [
    "Z_SRA_RECEPTION",
    "Z_SORTING_LANES",
    "Z_PREANALYTICS",
    "Z_ANALYZER_HALL_A",
    "Z_ANALYZER_HALL_B",
    "Z_QC_SUPERVISOR",
]

# Device type prefix -> zone for deterministic placement.
DEVICE_TYPE_ZONE: dict[str, str] = {
    "CENTRIFUGE": "Z_CENTRIFUGE_BAY",
    "ALIQUOTER": "Z_ALIQUOT_LABEL",
    "CHEM": "Z_ANALYZER_HALL_A",
    "HAEM": "Z_ANALYZER_HALL_A",
    "COAG": "Z_ANALYZER_HALL_B",
}


@dataclass
class CoordinationScaleConfig:
    """Scale configuration for coordination benchmarks. Deterministic given seed."""

    num_agents_total: int
    role_mix: dict[str, float]  # role_id -> fraction, must sum to 1.0
    num_devices_per_type: dict[str, int]  # device_type -> count
    num_sites: int
    specimens_per_min: float
    horizon_steps: int
    timing_mode: str = "explicit"  # "explicit" | "simulated"
    partner_id: str | None = None

    def __post_init__(self) -> None:
        total = sum(self.role_mix.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"role_mix must sum to 1.0, got {total}")


def _specimen_template(
    specimen_id: str,
    arrival_ts_s: int = 0,
    priority_class: str = "ROUTINE",
    panel_id: str = "BIOCHEM_PANEL_CORE",
) -> dict[str, Any]:
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
        "status": "arrived_at_reception",
        "priority_class": priority_class,
    }


def _generate_agents(
    rng: random.Random,
    num_agents: int,
    role_mix: dict[str, float],
    zone_ids: list[str],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Return (agents list, agent_id -> role_id). Deterministic given rng."""
    roles_ordered = list(role_mix.keys())
    cumul = 0.0
    thresholds = []
    for r in roles_ordered:
        cumul += role_mix[r]
        thresholds.append((cumul, r))
    agents_list: list[dict[str, str]] = []
    agent_to_role: dict[str, str] = {}
    for i in range(num_agents):
        agent_id = f"A_WORKER_{i + 1:04d}"
        u = rng.random()
        role_id = roles_ordered[0]
        for thresh, r in thresholds:
            if u <= thresh:
                role_id = r
                break
        zone_id = zone_ids[i % len(zone_ids)]
        agents_list.append({"agent_id": agent_id, "zone_id": zone_id})
        agent_to_role[agent_id] = role_id
    return agents_list, agent_to_role


def _generate_device_placement(
    num_devices_per_type: dict[str, int],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Deterministic device_id list and device_placement (order stable)."""
    placement: list[dict[str, Any]] = []
    device_ids: list[str] = []
    for device_type, count in sorted(num_devices_per_type.items()):
        prefix = device_type.split("_")[0] if "_" in device_type else device_type
        base_zone = DEVICE_TYPE_ZONE.get(prefix, "Z_ANALYZER_HALL_A")
        for k in range(count):
            dev_id = f"DEV_{device_type}_{k + 1:04d}"
            device_ids.append(dev_id)
            placement.append(
                {
                    "device_id": dev_id,
                    "zone_id": base_zone,
                    "device_type": device_type,
                }
            )
    return placement, device_ids


def _generate_sites(num_sites: int) -> dict[str, Any]:
    """Deterministic sites_policy for num_sites (SITE_001, ...)."""
    sites = []
    for i in range(num_sites):
        site_id = f"SITE_{i + 1:03d}"
        sites.append(
            {
                "site_id": site_id,
                "name": f"Site {i + 1}",
                "zone_ids": DEFAULT_SCALE_ZONES[:],
            }
        )
    site_graph = []
    for i in range(num_sites):
        for j in range(num_sites):
            if i != j:
                site_graph.append(
                    {
                        "from_site": sites[i]["site_id"],
                        "to_site": sites[j]["site_id"],
                        "enabled": True,
                    }
                )
    routes = []
    for i in range(num_sites):
        for j in range(num_sites):
            if i != j:
                routes.append(
                    {
                        "route_id": f"{sites[i]['site_id']}_TO_{sites[j]['site_id']}",
                        "from_site": sites[i]["site_id"],
                        "to_site": sites[j]["site_id"],
                        "transport_time_mean_s": 600,
                        "transport_time_std_s": 60,
                        "temp_drift_model": "bounded",
                        "temp_drift_max_c": 2.0,
                        "temp_band": "AMBIENT_20_25",
                    }
                )
    return {
        "version": "0.1",
        "sites": sites,
        "site_graph": site_graph,
        "routes": routes,
    }


def _generate_specimens_and_arrival(
    rng: random.Random,
    seed: int,
    specimens_per_min: float,
    horizon_steps: int,
    dt_s: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Initial backlog + arrival schedule. Deterministic given rng."""
    total_time_s = horizon_steps * dt_s
    # Expected number of arrivals over horizon
    n_expected = max(0, int(specimens_per_min * (total_time_s / 60.0)))
    n_backlog = rng.randint(max(0, n_expected // 4), max(1, n_expected))
    n_arrivals = max(0, n_expected - n_backlog)
    specimens: list[dict[str, Any]] = []
    for i in range(n_backlog):
        sid = f"S_COORD_{seed}_{i}"
        arrival_ts_s = rng.randint(0, min(100, total_time_s))
        prio = "STAT" if rng.random() < 0.1 else "ROUTINE"
        specimens.append(_specimen_template(sid, arrival_ts_s=arrival_ts_s, priority_class=prio))
    arrival_schedule: list[dict[str, Any]] = []
    for i in range(n_arrivals):
        t_s = rng.randint(0, total_time_s)
        sid = f"S_COORD_{seed}_{n_backlog + i}"
        prio = "STAT" if rng.random() < 0.1 else "ROUTINE"
        arrival_schedule.append(
            {
                "specimen_id": sid,
                "arrival_t_s": t_s,
                "priority_class": prio,
            }
        )
    return specimens, arrival_schedule


def _build_zone_layout_with_placement(
    base_policy_root: Path,
    device_placement: list[dict[str, str]],
) -> dict[str, Any]:
    """Load base zone layout and override device_placement; or minimal layout."""
    zone_path = base_policy_root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if zone_path.exists():
        try:
            data = _load_zone_layout_file(zone_path)
            layout = dict(data)
            layout["device_placement"] = device_placement
            return layout
        except Exception:
            pass
    # Minimal layout: zones only, no doors; graph_edges minimal
    zones = [{"zone_id": z, "name": z, "kind": "STAGING", "temp_band": "AMBIENT_20_25"} for z in DEFAULT_SCALE_ZONES]
    edges = []
    for i in range(len(DEFAULT_SCALE_ZONES) - 1):
        edges.append(
            {
                "from": DEFAULT_SCALE_ZONES[i],
                "to": DEFAULT_SCALE_ZONES[i + 1],
                "travel_s": 20,
            }
        )
    return {
        "version": "0.1",
        "zones": zones,
        "doors": [],
        "graph_edges": edges,
        "device_placement": device_placement,
    }


def _build_equipment_registry(
    base_policy_root: Path,
    num_devices_per_type: dict[str, int],
    device_placement: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge base device_types with generated device_instances."""
    equip_path = base_policy_root / "policy" / "equipment" / "equipment_registry.v0.1.yaml"
    device_types: dict[str, Any] = {}
    if equip_path.exists():
        try:
            data = load_yaml(equip_path)
            reg = data.get("equipment_registry") or {}
            device_types = dict(reg.get("device_types") or {})
        except Exception:
            pass
    device_instances = []
    for d in device_placement:
        dev_id = d["device_id"]
        device_type = str(d.get("device_type", "CHEM_ANALYZER"))
        zone_id = str(d.get("zone_id", "Z_ANALYZER_HALL_A"))
        device_instances.append(
            {
                "device_id": dev_id,
                "device_type": device_type,
                "zone_id": zone_id,
                "zone": zone_id,
                "capacity": 1,
                "parallel_units": 1,
            }
        )
    return {
        "version": "0.1",
        "device_types": device_types,
        "device_instances": device_instances,
    }


def _sanitize_scale_config(scale: CoordinationScaleConfig) -> dict[str, Any]:
    """Return a JSON-serializable, sanitized copy for emit/log (no Path, stable)."""
    return {
        "num_agents_total": scale.num_agents_total,
        "role_mix": dict(scale.role_mix),
        "num_devices_per_type": dict(scale.num_devices_per_type),
        "num_sites": scale.num_sites,
        "specimens_per_min": scale.specimens_per_min,
        "horizon_steps": scale.horizon_steps,
        "timing_mode": scale.timing_mode,
        "partner_id": scale.partner_id,
    }


def generate_scaled_initial_state(
    scale: CoordinationScaleConfig,
    base_policy_root: Path,
    seed: int,
) -> dict[str, Any]:
    """
    Generate deterministic initial_state for coordination-at-scale benchmarks.

    Creates agents (A_WORKER_0001, ...), device IDs and placement, sites graph,
    initial specimen backlog and arrival schedule. Does not write policy files.
    Returns initial_state suitable for core_env reset; includes effective_policy
    overlay (zone_layout, equipment_registry, rbac_policy.agents, sites_policy)
    and _scale_config_sanitized for COORD_SCALE_CONFIG emit.
    """
    rng = random.Random(seed)
    base_policy_root = Path(base_policy_root)

    # Agents and RBAC mapping
    agents_list, agent_to_role = _generate_agents(
        rng,
        scale.num_agents_total,
        scale.role_mix,
        DEFAULT_SCALE_ZONES,
    )

    # Devices: placement and IDs
    device_placement, device_ids = _generate_device_placement(
        scale.num_devices_per_type,
    )

    # Zone layout with placement
    zone_layout = _build_zone_layout_with_placement(base_policy_root, device_placement)

    # Equipment registry
    equipment_registry = _build_equipment_registry(
        base_policy_root,
        scale.num_devices_per_type,
        device_placement,
    )

    # Sites
    sites_policy = _generate_sites(scale.num_sites)

    # Specimens and arrival schedule
    specimens, arrival_schedule = _generate_specimens_and_arrival(
        rng,
        seed,
        scale.specimens_per_min,
        scale.horizon_steps,
    )

    # Effective policy: load base (or partner) and overlay scale-generated bits
    effective_policy: dict[str, Any] = {}
    if scale.partner_id:
        try:
            effective_policy, _, _, _ = load_effective_policy(base_policy_root, partner_id=scale.partner_id)
        except Exception:
            effective_policy = {}
    if not effective_policy:
        crit_path = base_policy_root / "policy" / "critical" / "critical_thresholds.v0.1.yaml"
        if crit_path.exists():
            try:
                from labtrust_gym.engine.critical import load_critical_thresholds

                effective_policy["critical_thresholds"] = load_critical_thresholds(crit_path)
            except Exception:
                pass
        enf_path = base_policy_root / "policy" / "enforcement" / "enforcement_map.v0.1.yaml"
        if enf_path.exists():
            try:
                data = load_yaml(enf_path)
                effective_policy["enforcement_map"] = data.get("enforcement_map", data)
            except Exception:
                pass
        rbac_path = base_policy_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
        if rbac_path.exists():
            try:
                data = load_yaml(rbac_path)
                rbac = data.get("rbac_policy") or data
                roles = dict(rbac.get("roles") or {})
                effective_policy["rbac_policy"] = {
                    "version": rbac.get("version", "0.1"),
                    "roles": roles,
                    "agents": agent_to_role,
                    "action_constraints": dict(rbac.get("action_constraints") or {}),
                }
            except Exception:
                effective_policy["rbac_policy"] = {
                    "version": "0.1",
                    "roles": {},
                    "agents": agent_to_role,
                    "action_constraints": {},
                }
        else:
            effective_policy["rbac_policy"] = {
                "version": "0.1",
                "roles": {},
                "agents": agent_to_role,
                "action_constraints": {},
            }
    else:
        effective_policy["rbac_policy"] = {
            **(effective_policy.get("rbac_policy") or {}),
            "agents": agent_to_role,
        }
    effective_policy["zone_layout"] = zone_layout
    effective_policy["equipment_registry"] = equipment_registry
    effective_policy["sites_policy"] = sites_policy

    initial_state: dict[str, Any] = {
        "system": {"now_s": 0, "downtime_active": False},
        "agents": agents_list,
        "specimens": specimens,
        "tokens": [],
        "timing_mode": scale.timing_mode,
        "effective_policy": effective_policy,
        "arrival_schedule": arrival_schedule,
        "_scale_config_sanitized": _sanitize_scale_config(scale),
        "_scale_device_ids": device_ids,
        "_scale_zone_ids": list(DEFAULT_SCALE_ZONES),
    }
    if scale.partner_id:
        initial_state["partner_id"] = scale.partner_id
    return initial_state
