"""
Zone layout and door rules for the simulated lab.

Zones are connected by an adjacency graph (from policy graph_edges). Agents can
only MOVE along these edges. Doors track when they were opened (open_since_ts).
Restricted doors require a specific token (TOKEN_RESTRICTED_ENTRY); this is
enforced in core_env. If a door stays open longer than max_open_s seconds,
an alarm is raised and the zone is frozen (KILL_SWITCH_ZONE). The query
zone_state(zone_id) returns 'frozen' or 'normal'.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

RC_ILLEGAL_MOVE = "RC_ILLEGAL_MOVE"
INV_ZONE_001 = "INV-ZONE-001"
INV_ZONE_004 = "INV-ZONE-004"
INV_ZONE_005 = "INV-ZONE-005"
ALARM = "ALARM"
KILL_SWITCH_ZONE = "KILL_SWITCH_ZONE"

# Default agent positions from golden suite fixtures (used when no initial_state.agents).
DEFAULT_AGENT_ZONES: dict[str, str] = {
    "A_RECEPTION": "Z_SRA_RECEPTION",
    "A_RUNNER": "Z_SORTING_LANES",
    "A_PREAN": "Z_PREANALYTICS",
    "A_ANALYTICS": "Z_ANALYZER_HALL_A",
    "A_QC": "Z_QC_SUPERVISOR",
    "A_SUPERVISOR": "Z_QC_SUPERVISOR",
    "A_CLINSCI": "Z_QC_SUPERVISOR",
    "A_SECURITY": "Z_QC_SUPERVISOR",
}


def load_zone_layout(path: str | Path) -> dict[str, Any]:
    """Load zone_layout_policy YAML. Returns dict with zones, doors, graph_edges."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    layout = data.get("zone_layout_policy")
    if layout is None:
        raise PolicyLoadError(p, "missing top-level key 'zone_layout_policy'")
    return cast(dict[str, Any], layout)


def build_adjacency_set(graph_edges: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Build set of (from_zone, to_zone) for legal movement (bidirectional)."""
    adj: set[tuple[str, str]] = set()
    for e in graph_edges or []:
        f = e.get("from")
        t = e.get("to")
        if f and t:
            adj.add((str(f), str(t)))
            adj.add((str(t), str(f)))
    return adj


def build_device_zone_map(device_placement: list[dict[str, Any]]) -> dict[str, str]:
    """Build device_id -> zone_id from zone_layout_policy device_placement (or equipment registry)."""
    out: dict[str, str] = {}
    for d in device_placement or []:
        dev_id = d.get("device_id")
        zone_id = d.get("zone_id")
        if dev_id and zone_id:
            out[str(dev_id)] = str(zone_id)
    return out


def build_doors_map(doors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build door_id -> { from_zone, to_zone, max_open_s, restricted, requires_token }."""
    out: dict[str, dict[str, Any]] = {}
    for d in doors or []:
        door_id = d.get("door_id")
        if not door_id:
            continue
        kind = (d.get("kind") or "").upper()
        restricted = "RESTRICTED" in kind or "RESTRICTED_AIRLOCK" in kind or bool(d.get("requires_token"))
        out[str(door_id)] = {
            "from_zone": str(d.get("from_zone", "")),
            "to_zone": str(d.get("to_zone", "")),
            "max_open_s": int(d.get("max_open_s", 600)),
            "restricted": restricted,
            "requires_token": d.get("requires_token") or ("TOKEN_RESTRICTED_ENTRY" if restricted else None),
            "alarm_on_breach": d.get("alarm_on_breach", True),
        }
    return out


class ZoneState:
    """
    Maintains agent positions, door open state, and zone frozen state.
    Used by core_env for MOVE, OPEN_DOOR, TICK and query(zone_state(...)).
    """

    def __init__(self, layout: dict[str, Any] | None = None) -> None:
        if layout is None:
            layout = _default_layout()
        self._adjacency = build_adjacency_set(layout.get("graph_edges", []))
        self._doors = build_doors_map(layout.get("doors", []))
        self._agent_positions: dict[str, str] = dict(DEFAULT_AGENT_ZONES)
        self._door_open_since: dict[str, int | None] = {did: None for did in self._doors}
        self._zone_frozen: dict[str, bool] = {}

    def reset(
        self,
        agent_positions: dict[str, str] | None = None,
    ) -> None:
        """Reset positions and door/zone state. Agent positions default from DEFAULT_AGENT_ZONES."""
        self._agent_positions = dict(agent_positions) if agent_positions else dict(DEFAULT_AGENT_ZONES)
        self._door_open_since = {did: None for did in self._doors}
        self._zone_frozen = {}

    def set_agent_position(self, agent_id: str, zone_id: str) -> None:
        self._agent_positions[agent_id] = zone_id

    def get_agent_zone(self, agent_id: str) -> str | None:
        return self._agent_positions.get(agent_id)

    def is_adjacent(self, from_zone: str, to_zone: str) -> bool:
        if from_zone == to_zone:
            return True
        return (from_zone, to_zone) in self._adjacency

    def move(
        self,
        agent_id: str,
        from_zone: str,
        to_zone: str,
    ) -> tuple[bool, list[dict[str, str]], str | None]:
        """
        Attempt move. Returns (ok, violations, blocked_reason_code).
        If not adjacent: BLOCKED with INV-ZONE-001, RC_ILLEGAL_MOVE.
        If to_zone is restricted: caller must enforce token (INV-ZONE-004 in core_env).
        """
        violations: list[dict[str, str]] = []
        current = self._agent_positions.get(agent_id)
        if current and current != from_zone:
            violations.append({"invariant_id": INV_ZONE_001, "status": "VIOLATION"})
            return False, violations, RC_ILLEGAL_MOVE
        if not self.is_adjacent(from_zone, to_zone):
            violations.append({"invariant_id": INV_ZONE_001, "status": "VIOLATION"})
            if to_zone == "Z_RESTRICTED_BIOHAZARD":
                violations.append({"invariant_id": INV_ZONE_004, "status": "VIOLATION"})
            return False, violations, RC_ILLEGAL_MOVE
        self._agent_positions[agent_id] = to_zone
        return True, [], None

    def open_door(self, door_id: str, t_s: int) -> bool:
        """Record door open at t_s. Returns True if door exists."""
        if door_id not in self._doors:
            return False
        self._door_open_since[door_id] = t_s
        return True

    def is_door_restricted(self, door_id: str) -> bool:
        info = self._doors.get(door_id)
        return bool(info and info.get("restricted")) if info else False

    def tick(self, t_s: int) -> tuple[list[dict[str, str]], list[str]]:
        """
        Check door-open-too-long. Returns (violations, emits).
        For each door open beyond max_open_s: INV-ZONE-005, ALARM, KILL_SWITCH_ZONE; freeze zones.
        """
        violations: list[dict[str, str]] = []
        emits: list[str] = []
        for door_id, open_ts in self._door_open_since.items():
            if open_ts is None:
                continue
            info = self._doors.get(door_id)
            if not info or not info.get("alarm_on_breach"):
                continue
            max_s = info.get("max_open_s", 600)
            if t_s - open_ts <= max_s:
                continue
            violations.append({"invariant_id": INV_ZONE_005, "status": "VIOLATION"})
            emits.append(ALARM)
            emits.append(KILL_SWITCH_ZONE)
            for z in (info.get("from_zone"), info.get("to_zone")):
                if z:
                    self._zone_frozen[z] = True
            self._door_open_since[door_id] = None
        return violations, emits

    def zone_state(self, zone_id: str) -> str:
        """Return 'frozen' or 'normal' for state_assertions."""
        return "frozen" if self._zone_frozen.get(zone_id) else "normal"

    def get_door_state(self, door_id: str) -> tuple[bool, int | None]:
        """Return (is_open, open_since_ts). open_since_ts is None when closed."""
        if door_id not in self._doors:
            return False, None
        open_since = self._door_open_since.get(door_id)
        return (open_since is not None, open_since)


def get_default_device_zone_map() -> dict[str, str]:
    """Device id -> zone_id when no zone layout policy is loaded (e.g. tests)."""
    return build_device_zone_map(_default_layout().get("device_placement", []))


def _default_layout() -> dict[str, Any]:
    """Minimal layout when policy file not found: graph_edges and doors for GS-008, GS-009, GS-020."""
    return {
        "graph_edges": [
            {"from": "Z_SRA_RECEPTION", "to": "Z_ACCESSIONING"},
            {"from": "Z_ACCESSIONING", "to": "Z_SORTING_LANES"},
            {"from": "Z_SORTING_LANES", "to": "Z_PREANALYTICS"},
            {"from": "Z_SORTING_LANES", "to": "Z_CENTRIFUGE_BAY"},
            {"from": "Z_PREANALYTICS", "to": "Z_CENTRIFUGE_BAY"},
            {"from": "Z_CENTRIFUGE_BAY", "to": "Z_ALIQUOT_LABEL"},
            {"from": "Z_ALIQUOT_LABEL", "to": "Z_ANALYZER_HALL_A"},
            {"from": "Z_ALIQUOT_LABEL", "to": "Z_ANALYZER_HALL_B"},
            {"from": "Z_ANALYZER_HALL_A", "to": "Z_QC_SUPERVISOR"},
            {"from": "Z_ANALYZER_HALL_B", "to": "Z_QC_SUPERVISOR"},
            {
                "from": "Z_SRA_RECEPTION",
                "to": "Z_RESTRICTED_BIOHAZARD",
                "via_door": "D_RESTRICTED_AIRLOCK",
            },
            {"from": "Z_RESTRICTED_BIOHAZARD", "to": "Z_WASTE_DISPOSAL", "via_door": "D_WASTE"},
        ],
        "doors": [
            {
                "door_id": "D_RESTRICTED_AIRLOCK",
                "from_zone": "Z_SRA_RECEPTION",
                "to_zone": "Z_RESTRICTED_BIOHAZARD",
                "kind": "RESTRICTED_AIRLOCK",
                "max_open_s": 200,
                "alarm_on_breach": True,
                "requires_token": "TOKEN_RESTRICTED_ENTRY",
            },
        ],
        "device_placement": [
            {"device_id": "DEV_CENTRIFUGE_BANK_01", "zone_id": "Z_CENTRIFUGE_BAY"},
            {"device_id": "DEV_ALIQUOTER_01", "zone_id": "Z_ALIQUOT_LABEL"},
            {"device_id": "DEV_CHEM_A_01", "zone_id": "Z_ANALYZER_HALL_A"},
            {"device_id": "DEV_CHEM_B_01", "zone_id": "Z_ANALYZER_HALL_B"},
            {"device_id": "DEV_HAEM_01", "zone_id": "Z_ANALYZER_HALL_A"},
            {"device_id": "DEV_COAG_01", "zone_id": "Z_ANALYZER_HALL_B"},
        ],
    }
