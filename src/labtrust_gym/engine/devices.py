"""
Equipment and device run model (v0.1).

Each device has a state: IDLE, RUNNING, FAULT, or MAINT. At most one active run
per device (run_id, end time). When the simulation clock reaches the run end
time, the run completes and END_RUN semantics apply. Service times are sampled
from policy using the shared deterministic RNG. START_RUN takes the head of the
device queue and schedules a completion at current time plus service time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from labtrust_gym.engine.rng import RNG

DeviceState = Literal["IDLE", "RUNNING", "FAULT", "MAINT"]


@dataclass
class ActiveRun:
    """A run in progress on a device."""

    run_id: str
    work_id: str | None
    specimen_ids: list[str]
    start_ts_s: int
    end_ts_s: int
    panel_id: str | None = None


@dataclass
class DeviceRecord:
    """Per-device state: state machine + active run."""

    device_id: str
    device_type: str
    zone_id: str
    state: DeviceState = "IDLE"
    active_run: ActiveRun | None = None
    type_config: dict[str, Any] = field(default_factory=dict)


def _resolve_service_time_s(
    type_cfg: dict[str, Any],
    device_type: str,
    panel_id: str | None,
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


def load_equipment_registry(path: Path | None = None) -> dict[str, Any]:
    """Load equipment registry YAML; return top-level dict."""
    path = path or Path("policy/equipment/equipment_registry.v0.1.yaml")
    if not path.exists():
        return {"device_types": {}, "device_instances": []}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("equipment_registry", data) if isinstance(data, dict) else {}


def load_failure_models(path: Path | None = None) -> dict[str, Any]:
    """Load failure_models YAML; return failure_models dict or empty."""
    path = path or Path("policy/equipment/failure_models.v0.1.yaml")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("failure_models", data) if isinstance(data, dict) else {}


class DeviceStore:
    """
    Device state store: IDLE/RUNNING/FAULT/MAINT, active runs, completion times.
    Service times sampled via RNG for determinism.
    """

    def __init__(
        self,
        registry: dict[str, Any] | None = None,
        rng: RNG | None = None,
        failure_models: dict[str, Any] | None = None,
    ) -> None:
        self._registry = registry or load_equipment_registry()
        self._rng = rng or RNG(0)
        self._failure_models = failure_models or {}
        self._devices: dict[str, DeviceRecord] = {}
        self._type_config: dict[str, dict[str, Any]] = {}
        self._total_busy_s: dict[str, int] = {}
        self._maintenance_windows: list[tuple[str, int, int]] = []
        self._build()
        self._build_maintenance_windows()

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

    def _build_maintenance_windows(self) -> None:
        """Populate _maintenance_windows from failure_models.maintenance_schedule."""
        schedule = self._failure_models.get("maintenance_schedule") or []
        for entry in schedule:
            if isinstance(entry, dict):
                did = entry.get("device_id")
                start = entry.get("start_ts_s")
                end = entry.get("end_ts_s")
                if did is not None and start is not None and end is not None:
                    self._maintenance_windows.append((str(did), int(start), int(end)))

    def apply_maintenance(self, now_ts_s: int) -> None:
        """
        Apply maintenance windows at now_ts_s: set MAINT when in window (and IDLE),
        clear to IDLE when outside all windows. Deterministic; call from core_env step.
        """
        for did, d in self._devices.items():
            if d.state == "RUNNING":
                continue
            in_window = any(
                dev_id == did and start_s <= now_ts_s < end_s for dev_id, start_s, end_s in self._maintenance_windows
            )
            if in_window:
                d.state = "MAINT"
                d.active_run = None
            else:
                d.state = "IDLE"

    def device_block_reason(self, device_id: str) -> str | None:
        """
        Reason START_RUN is blocked: MAINT, FAULT, or RUNNING. None if IDLE (can start).
        """
        d = self._devices.get(device_id)
        if not d:
            return None
        if d.state == "MAINT":
            return "MAINT"
        if d.state == "FAULT":
            return "FAULT"
        if d.state == "RUNNING":
            return "RUNNING"
        return None

    def set_known_devices(self, device_ids: list[str]) -> None:
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
        work_id: str | None = None,
        specimen_ids: list[str] | None = None,
        panel_id: str | None = None,
    ) -> bool:
        """
        Start a run on the device. Schedules completion via RNG-sampled service time.
        Returns False if device not found or not IDLE.
        """
        d = self._devices.get(device_id)
        if not d or d.state != "IDLE":
            return False
        duration_s = _resolve_service_time_s(d.type_config, d.device_type, panel_id, self._rng)
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

    def completions(self, now_ts_s: int) -> list[tuple[str, str]]:
        """
        Return list of (device_id, run_id) for runs that have completed by now_ts_s.
        Does not mutate state; call finish_run to clear.
        """
        out: list[tuple[str, str]] = []
        for did, d in self._devices.items():
            if d.state == "RUNNING" and d.active_run and d.active_run.end_ts_s <= now_ts_s:
                out.append((did, d.active_run.run_id))
        return out

    def finish_run(self, device_id: str) -> ActiveRun | None:
        """
        Clear the active run on the device and set state to IDLE (or MAINT if in window).
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

    def finish_completions(self, now_ts_s: int) -> list[tuple[str, str, ActiveRun | None]]:
        """
        For all devices that completed by now_ts_s, finish the run and return
        (device_id, run_id, ActiveRun) for each. Call this after advancing clock.
        """
        result: list[tuple[str, str, ActiveRun | None]] = []
        for did, run_id in self.completions(now_ts_s):
            run = self.finish_run(did)
            result.append((did, run_id, run))
        return result

    def get_active_run(self, device_id: str) -> ActiveRun | None:
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

    def get_all_total_busy_s(self) -> dict[str, int]:
        """Per-device total busy seconds this episode."""
        return dict(self._total_busy_s)
