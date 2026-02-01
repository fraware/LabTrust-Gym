"""
Equipment capacity and cycle-time models v0.1.

- Device state machine: IDLE / RUNNING / FAULT / MAINT.
- Per-device active run: run_id, end_ts; completions drive END_RUN semantics.
- Service times sampled via single RNG wrapper (deterministic).
- Integrates with queues: START_RUN consumes queue head and schedules completion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

import yaml

from labtrust_gym.engine.rng import RNG

DeviceState = Literal["IDLE", "RUNNING", "FAULT", "MAINT"]


@dataclass
class ActiveRun:
    """A run in progress on a device."""

    run_id: str
    work_id: Optional[str]
    specimen_ids: List[str]
    start_ts_s: int
    end_ts_s: int
    panel_id: Optional[str] = None


@dataclass
class DeviceRecord:
    """Per-device state: state machine + active run."""

    device_id: str
    device_type: str
    zone_id: str
    state: DeviceState = "IDLE"
    active_run: Optional[ActiveRun] = None
    type_config: Dict[str, Any] = field(default_factory=dict)


def _resolve_service_time_s(
    type_cfg: Dict[str, Any],
    device_type: str,
    panel_id: Optional[str],
    rng: RNG,
) -> float:
    """
    Sample service time in seconds from device type config.
    Prefers service_time_model; falls back to timing_model. Deterministic dist uses value.
    """
    model = type_cfg.get("service_time_model") or type_cfg.get("timing_model") or {}
    # Analyzer: per_panel_s or run_s / per_test_s
    if device_type in ("CHEM_ANALYZER", "COAG_ANALYZER", "HAEM_ANALYZER"):
        per_panel = model.get("per_panel_s") or {}
        if panel_id and isinstance(per_panel, dict) and panel_id in per_panel:
            p = per_panel[panel_id]
            if isinstance(p, dict) and p.get("dist") == "deterministic":
                return float(p.get("value", 30.0))
        run_s = model.get("run_s")
        if isinstance(run_s, dict) and run_s.get("dist") == "deterministic":
            return float(run_s.get("value", 30.0))
        per_test = model.get("per_test_s")
        if isinstance(per_test, dict) and per_test.get("dist") == "deterministic":
            return float(per_test.get("value", 1.8)) * 14  # default ~25s
        return 30.0
    # Centrifuge: spin_time_s or run_s
    if device_type == "CENTRIFUGE_BANK":
        spin = model.get("spin_time_s") or model.get("run_s")
        if isinstance(spin, dict) and spin.get("dist") == "deterministic":
            return float(spin.get("value", 600.0))
        setup = model.get("setup_s") or {}
        teardown = model.get("teardown_s") or {}
        setup_s = float(setup.get("value", 60)) if isinstance(setup, dict) else 60.0
        run_s = float(spin.get("value", 600)) if isinstance(spin, dict) else 600.0
        teardown_s = float(teardown.get("value", 60)) if isinstance(teardown, dict) else 60.0
        return setup_s + run_s + teardown_s
    # Aliquoter: per_tube + per_aliquot (single sample ≈ 1 tube, 1 aliquot)
    if device_type == "ALIQUOTER":
        per_tube = model.get("per_tube_overhead_s") or {}
        per_aliquot = model.get("per_aliquot_s") or {}
        a = float(per_tube.get("value", 3)) if isinstance(per_tube, dict) else 3.0
        b = float(per_aliquot.get("value", 2)) if isinstance(per_aliquot, dict) else 2.0
        return a + b
    # Default
    run_s = model.get("run_s")
    if isinstance(run_s, dict) and run_s.get("dist") == "deterministic":
        return float(run_s.get("value", 60.0))
    return 60.0


def load_equipment_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load equipment registry YAML; return top-level dict."""
    path = path or Path("policy/equipment/equipment_registry.v0.1.yaml")
    if not path.exists():
        return {"device_types": {}, "device_instances": []}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("equipment_registry", data) if isinstance(data, dict) else {}


class DeviceStore:
    """
    Device state store: IDLE/RUNNING/FAULT/MAINT, active runs, completion times.
    Service times sampled via RNG for determinism.
    """

    def __init__(
        self,
        registry: Optional[Dict[str, Any]] = None,
        rng: Optional[RNG] = None,
    ) -> None:
        self._registry = registry or load_equipment_registry()
        self._rng = rng or RNG(0)
        self._devices: Dict[str, DeviceRecord] = {}
        self._type_config: Dict[str, Dict[str, Any]] = {}
        self._total_busy_s: Dict[str, int] = {}
        self._build()

    def _build(self) -> None:
        types = self._registry.get("device_types") or {}
        for dtype, cfg in types.items():
            self._type_config[dtype] = dict(cfg) if isinstance(cfg, dict) else {}
        instances = self._registry.get("device_instances") or []
        for inst in instances:
            if not isinstance(inst, dict):
                continue
            did = inst.get("device_id")
            dtype = inst.get("device_type")
            zone = inst.get("zone_id") or inst.get("zone") or ""
            if did and dtype:
                self._devices[did] = DeviceRecord(
                    device_id=did,
                    device_type=dtype,
                    zone_id=zone,
                    state="IDLE",
                    active_run=None,
                    type_config=self._type_config.get(dtype, {}),
                )

    def set_known_devices(self, device_ids: List[str]) -> None:
        """Ensure these devices exist; create minimal records if missing."""
        for did in device_ids:
            if did not in self._devices:
                self._devices[did] = DeviceRecord(
                    device_id=did,
                    device_type="UNKNOWN",
                    zone_id="",
                    state="IDLE",
                    active_run=None,
                    type_config={},
                )

    def device_state(self, device_id: str) -> DeviceState:
        """Return current state: IDLE, RUNNING, FAULT, MAINT."""
        d = self._devices.get(device_id)
        if not d:
            return "IDLE"
        return d.state

    def is_idle(self, device_id: str) -> bool:
        return self.device_state(device_id) == "IDLE"

    def can_start_run(self, device_id: str) -> bool:
        """True if device exists and is IDLE (and not FAULT/MAINT)."""
        return self.is_idle(device_id)

    def start_run(
        self,
        device_id: str,
        run_id: str,
        start_ts_s: int,
        work_id: Optional[str] = None,
        specimen_ids: Optional[List[str]] = None,
        panel_id: Optional[str] = None,
    ) -> bool:
        """
        Start a run on the device. Schedules completion via RNG-sampled service time.
        Returns False if device not found or not IDLE.
        """
        d = self._devices.get(device_id)
        if not d or d.state != "IDLE":
            return False
        duration_s = _resolve_service_time_s(
            d.type_config, d.device_type, panel_id, self._rng
        )
        end_ts_s = start_ts_s + max(1, int(round(duration_s)))
        d.active_run = ActiveRun(
            run_id=run_id,
            work_id=work_id,
            specimen_ids=specimen_ids or [],
            start_ts_s=start_ts_s,
            end_ts_s=end_ts_s,
            panel_id=panel_id,
        )
        d.state = "RUNNING"
        return True

    def completions(self, now_ts_s: int) -> List[Tuple[str, str]]:
        """
        Return list of (device_id, run_id) for runs that have completed by now_ts_s.
        Does not mutate state; call finish_run to clear.
        """
        out: List[Tuple[str, str]] = []
        for did, d in self._devices.items():
            if d.state == "RUNNING" and d.active_run and d.active_run.end_ts_s <= now_ts_s:
                out.append((did, d.active_run.run_id))
        return out

    def finish_run(self, device_id: str) -> Optional[ActiveRun]:
        """
        Clear the active run on the device and set state to IDLE.
        Accumulate busy time for utilization metrics.
        Returns the finished run info, or None if no run.
        """
        d = self._devices.get(device_id)
        if not d or not d.active_run:
            return None
        run = d.active_run
        duration = run.end_ts_s - run.start_ts_s
        self._total_busy_s[device_id] = self._total_busy_s.get(device_id, 0) + duration
        d.active_run = None
        d.state = "IDLE"
        return run

    def finish_completions(self, now_ts_s: int) -> List[Tuple[str, str, Optional[ActiveRun]]]:
        """
        For all devices that completed by now_ts_s, finish the run and return
        (device_id, run_id, ActiveRun) for each. Call this after advancing clock.
        """
        result: List[Tuple[str, str, Optional[ActiveRun]]] = []
        for did, run_id in self.completions(now_ts_s):
            run = self.finish_run(did)
            result.append((did, run_id, run))
        return result

    def get_active_run(self, device_id: str) -> Optional[ActiveRun]:
        d = self._devices.get(device_id)
        return d.active_run if d else None

    def set_fault(self, device_id: str) -> None:
        d = self._devices.get(device_id)
        if d:
            d.state = "FAULT"
            d.active_run = None

    def set_maint(self, device_id: str) -> None:
        d = self._devices.get(device_id)
        if d:
            d.state = "MAINT"
            d.active_run = None

    def get_total_busy_s(self, device_id: str) -> int:
        """Total seconds this device was busy (RUNNING) this episode. For utilization = busy_s / episode_time_s."""
        return self._total_busy_s.get(device_id, 0)

    def get_all_total_busy_s(self) -> Dict[str, int]:
        """Per-device total busy seconds this episode."""
        return dict(self._total_busy_s)
