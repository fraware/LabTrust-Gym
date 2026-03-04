"""
Quality control (QC) state and result release gating.

Each device has a QC state (pass or fail). Runs are associated with a device
via START_RUN. Results have status (generated, held, released) and optional
flags. QC_EVENT updates device QC state. RELEASE_RESULT is blocked with
QC_FAIL_ACTIVE when the device is in fail state (result stays held).
RELEASE_RESULT_OVERRIDE with the drift override token adds the
QC_DRIFT_DISCLAIMER_REQUIRED flag and allows release despite fail state.
"""

from __future__ import annotations

from typing import Any

QC_FAIL_ACTIVE = "QC_FAIL_ACTIVE"
QC_DRIFT_DISCLAIMER_REQUIRED = "QC_DRIFT_DISCLAIMER_REQUIRED"


class QCStore:
    """
    Device QC state and result status/flags.
    - _device_qc_state: device_id -> "pass" | "fail" (default "pass" when not set)
    - _run_device: run_id -> device_id
    - _results: result_id -> { status, run_id, device_id?, flags: list }
    """

    def __init__(self) -> None:
        self._device_qc_state: dict[str, str] = {}
        self._run_device: dict[str, str] = {}
        self._results: dict[str, dict[str, Any]] = {}

    def device_qc_state(self, device_id: str) -> str:
        """Return "pass" or "fail". Default "pass" if never set."""
        return self._device_qc_state.get(device_id, "pass")

    def set_device_qc_state(self, device_id: str, qc_outcome: str) -> None:
        """Set device qc_state from QC_EVENT (pass/fail)."""
        self._device_qc_state[device_id] = str(qc_outcome).lower()

    def register_run(self, run_id: str, device_id: str) -> None:
        """From START_RUN: run_id -> device_id."""
        self._run_device[str(run_id)] = str(device_id)

    def get_device_for_run(self, run_id: str) -> str | None:
        return self._run_device.get(str(run_id))

    def get_device_for_result(self, result_id: str) -> str | None:
        res = self._results.get(result_id)
        if not res:
            return None
        return res.get("device_id") or res.get("run_id") and self._run_device.get(str(res["run_id"]))

    def result_status(self, result_id: str) -> str | None:
        res = self._results.get(result_id)
        return res.get("status") if res else None

    def result_flags(self, result_id: str) -> list[str]:
        res = self._results.get(result_id)
        if not res:
            return []
        return list(res.get("flags", []))

    def create_result(
        self,
        result_id: str,
        run_id: str | None = None,
        device_id: str | None = None,
        qc_state: str | None = None,
    ) -> None:
        """Create result (GENERATE_RESULT). Status held if device qc fail else generated."""
        run_id = str(run_id) if run_id else ""
        did = device_id or (self._run_device.get(run_id) if run_id else None)
        status = "generated"
        if did and self.device_qc_state(did) == "fail":
            status = "held"
        self._results[str(result_id)] = {
            "result_id": str(result_id),
            "run_id": run_id,
            "device_id": did,
            "status": status,
            "flags": [],
            "qc_state": qc_state,
        }

    def hold_result(self, result_id: str) -> bool:
        """Set result status to held. Returns True if result exists."""
        if result_id not in self._results:
            return False
        self._results[result_id]["status"] = "held"
        return True

    def release_result(self, result_id: str) -> bool:
        """Set result status to released. Returns True if result exists."""
        if result_id not in self._results:
            return False
        self._results[result_id]["status"] = "released"
        return True

    def can_release_result(self, result_id: str) -> tuple[bool, str | None]:
        """
        Returns (can_release, blocked_reason_code).
        If device for this result has qc_state==fail => (False, QC_FAIL_ACTIVE).
        """
        res = self._results.get(result_id)
        if not res:
            return True, None
        did = res.get("device_id") or self._run_device.get(str(res.get("run_id", "")))
        if did and self.device_qc_state(did) == "fail":
            return False, QC_FAIL_ACTIVE
        return True, None

    def release_result_override_with_drift_flag(self, result_id: str) -> bool:
        """
        Add QC_DRIFT_DISCLAIMER_REQUIRED flag and set status released.
        Returns True if result exists.
        """
        if result_id not in self._results:
            return False
        flags = self._results[result_id].setdefault("flags", [])
        if QC_DRIFT_DISCLAIMER_REQUIRED not in flags:
            flags.append(QC_DRIFT_DISCLAIMER_REQUIRED)
        self._results[result_id]["status"] = "released"
        return True

    def list_result_ids_with_status(self, *statuses: str) -> list[str]:
        """Return result_ids whose status is in statuses. Deterministic order (sorted)."""
        st_set = set(statuses)
        out = [rid for rid, res in self._results.items() if (res.get("status") or "") in st_set]
        return sorted(out)
