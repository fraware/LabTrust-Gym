"""
Hub planner: macro-level assignment of work to regions (not to agents).
SLA targets: deadline_step per assignment for local controllers.
Deterministic; operates on global obs or aggregated summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

MacroAssignment = Tuple[str, str, str, str, int, int]
# (region_id, work_id, device_id, zone_id, priority, deadline_step)


@dataclass
class HubPlanner:
    """
    Assigns work items to regions. Local controllers then assign to agents within region.
    SLA: deadline_step = t + sla_horizon (default 20).
    """

    sla_horizon: int = 20

    def assign(
        self,
        obs: Dict[str, Any],
        zone_to_region: Dict[str, str],
        device_zone: Dict[str, str],
        device_ids: List[str],
        t: int,
        rng: Any,
    ) -> List[MacroAssignment]:
        """
        From global obs, build work list (device, work_id, zone) and assign each to its region.
        Work in zone Z goes to region zone_to_region[Z]. Deterministic: stable sort by priority then device/work.
        """
        worklist: List[Tuple[int, str, str, str]] = []
        for agent_id, o in obs.items():
            if not isinstance(o, dict):
                continue
            if o.get("log_frozen"):
                continue
            qbd = o.get("queue_by_device") or []
            for idx, dev_id in enumerate(device_ids):
                if idx >= len(qbd):
                    continue
                d = qbd[idx] if isinstance(qbd[idx], dict) else {}
                if not d.get("queue_head"):
                    continue
                head = d.get("queue_head", "W")
                zone_id = device_zone.get(dev_id, "")
                if not zone_id:
                    continue
                prio = (
                    2
                    if "STAT" in str(head).upper()
                    else (1 if "URGENT" in str(head).upper() else 0)
                )
                worklist.append((prio, dev_id, head or "W", zone_id))
        worklist.sort(key=lambda x: (-x[0], x[1], x[2]))
        seen: set = set()
        out: List[MacroAssignment] = []
        deadline = t + self.sla_horizon
        for prio, device_id, work_id, zone_id in worklist:
            key = (device_id, work_id)
            if key in seen:
                continue
            seen.add(key)
            region_id = zone_to_region.get(zone_id, "R_0")
            out.append((region_id, work_id, device_id, zone_id, prio, deadline))
        return out
