"""Canonical immutable snapshot / restore for CoreEnv (LT-VA-04)."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from typing import Any

from labtrust_gym.engine.devices import ActiveRun, DeviceRecord
from labtrust_gym.engine.queueing import DeviceQueue, DeviceQueueItem
from labtrust_gym.policy.tokens import Token
from labtrust_gym.util.json_utils import canonical_json

SNAPSHOT_FORMAT_ID = "CanonicalSnapshot"
SNAPSHOT_VERSION = "1"
REQUIRED_KEYS = (
    "schema_id",
    "format_id",
    "version",
    "now_ts",
    "timing_mode",
    "system_state",
    "audit",
    "tokens",
    "tokens_next_id",
    "specimens",
    "specimen_last_id_match",
    "aliquot_to_specimen",
    "qc",
    "critical",
    "queues",
    "known_device_ids",
    "devices",
    "device_total_busy_s",
    "transport",
    "zones",
    "enforcement_violation_counts",
    "reagent_stock",
    "episode_agent_action_count",
    "episode_agent_override_count",
    "policy_fingerprint",
    "partner_id",
    "rng_state",
    "claim_boundary",
)

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"


class SnapshotError(ValueError):
    """Fail-closed snapshot/restore error."""


class CanonicalSnapshot:
    """Immutable snapshot payload with canonical digest."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = validate_snapshot_payload(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    def canonical_digest(self) -> str:
        body = {k: v for k, v in self._payload.items() if k != "snapshot_digest"}
        return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        out = self.payload
        out["snapshot_digest"] = self.canonical_digest()
        return out


def validate_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SnapshotError("snapshot must be an object")
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise SnapshotError(f"incomplete snapshot; missing: {missing}")
    if payload.get("schema_id") != "CanonicalSnapshot.v1":
        raise SnapshotError("schema_id must be CanonicalSnapshot.v1")
    if payload.get("format_id") != SNAPSHOT_FORMAT_ID:
        raise SnapshotError("format_id mismatch")
    if payload.get("version") != SNAPSHOT_VERSION:
        raise SnapshotError("snapshot version mismatch")
    if payload.get("claim_boundary") != CLAIM_BOUNDARY:
        raise SnapshotError("claim_boundary mismatch")
    return copy.deepcopy(payload)


def capture_core_env(env: Any) -> CanonicalSnapshot:
    """Deep-serialize CoreEnv stores into a CanonicalSnapshot."""
    audit = env._audit
    tokens = env._tokens
    specimens = env._specimens
    qc = env._qc
    critical = env._critical
    queues = env._queues
    transport = env._transport
    zones = env._zones

    token_list = [tok.to_dict() for tok in tokens._tokens.values()]
    queue_payload: dict[str, Any] = {}
    for did, q in queues._queues.items():
        queue_payload[did] = {
            "device_id": q.device_id,
            "next_tie_break": q._next_tie_break,
            "items": [
                {
                    "work_id": it.work_id,
                    "priority_class": it.priority_class,
                    "enqueued_ts_s": it.enqueued_ts_s,
                    "requested_by_agent": it.requested_by_agent,
                    "reason_code": it.reason_code,
                    "tie_break": it.tie_break,
                }
                for it in q.items
            ],
        }

    devices_payload: dict[str, Any] = {}
    device_busy: dict[str, int] = {}
    if env._device_store is not None:
        for did, rec in env._device_store._devices.items():
            active = None
            if rec.active_run is not None:
                active = asdict(rec.active_run)
            devices_payload[did] = {
                "device_id": rec.device_id,
                "device_type": rec.device_type,
                "zone_id": rec.zone_id,
                "state": rec.state,
                "active_run": active,
                "type_config": copy.deepcopy(rec.type_config),
            }
        device_busy = dict(env._device_store._total_busy_s)

    enf_counts: list[list[Any]] = []
    if getattr(env, "_enforcement_engine", None) is not None:
        for (agent_id, rule_id), count in env._enforcement_engine._violation_counts.items():
            enf_counts.append([agent_id, rule_id, int(count)])

    rng_state = None
    if env._rng is not None:
        rng_state = list(env._rng.get_state())

    payload = {
        "schema_id": "CanonicalSnapshot.v1",
        "format_id": SNAPSHOT_FORMAT_ID,
        "version": SNAPSHOT_VERSION,
        "now_ts": int(env._now_ts),
        "timing_mode": str(env._timing_mode),
        "system_state": copy.deepcopy(env._system_state),
        "audit": {
            "event_hashes": list(audit._event_hashes),
            "head_hash": audit._head_hash,
            "last_event_hash": audit._last_event_hash,
            "length": audit._length,
            "fault_injection": copy.deepcopy(audit._fault_injection),
        },
        "tokens": token_list,
        "tokens_next_id": int(tokens._next_id),
        "specimens": copy.deepcopy(specimens._specimens),
        "specimen_last_id_match": copy.deepcopy(specimens._last_id_match),
        "aliquot_to_specimen": copy.deepcopy(specimens._aliquot_to_specimen),
        "qc": {
            "device_qc_state": copy.deepcopy(qc._device_qc_state),
            "run_device": copy.deepcopy(qc._run_device),
            "results": copy.deepcopy(qc._results),
        },
        "critical": {
            "result_criticality": copy.deepcopy(critical._result_criticality),
            "comm_records": copy.deepcopy(critical._comm_records),
            "attempts": copy.deepcopy(critical._attempts),
            "notification_mode_required": copy.deepcopy(critical._notification_mode_required),
        },
        "queues": queue_payload,
        "known_device_ids": (
            sorted(queues._known_device_ids.keys()) if queues._known_device_ids is not None else None
        ),
        "devices": devices_payload,
        "device_total_busy_s": device_busy,
        "transport": {
            "consignments": copy.deepcopy(transport._consignments),
            "next_consignment_id": int(transport._next_consignment_id),
        },
        "zones": {
            "agent_positions": copy.deepcopy(zones._agent_positions),
            "door_open_since": copy.deepcopy(zones._door_open_since),
            "zone_frozen": copy.deepcopy(zones._zone_frozen),
        },
        "enforcement_violation_counts": enf_counts,
        "reagent_stock": copy.deepcopy(env._reagent_stock),
        "episode_agent_action_count": copy.deepcopy(env._episode_agent_action_count),
        "episode_agent_override_count": copy.deepcopy(env._episode_agent_override_count),
        "policy_fingerprint": env._policy_fingerprint,
        "partner_id": env._partner_id,
        "rng_state": rng_state,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return CanonicalSnapshot(payload)


def restore_core_env(env: Any, snapshot: CanonicalSnapshot | dict[str, Any]) -> None:
    """Restore CoreEnv mutable stores from snapshot. Fail closed on incomplete payloads."""
    if isinstance(snapshot, CanonicalSnapshot):
        payload = snapshot.payload
    else:
        payload = validate_snapshot_payload(snapshot)

    env._now_ts = int(payload["now_ts"])
    if env._clock is not None:
        env._clock.set(int(payload["now_ts"]))
    if env._rng is not None:
        if payload.get("rng_state") is None:
            raise SnapshotError("rng_state required for simulated RNG restore")
        env._rng.set_state(tuple(payload["rng_state"]))

    env._system_state = copy.deepcopy(payload["system_state"])
    env._reagent_stock = copy.deepcopy(payload["reagent_stock"])
    env._episode_agent_action_count = copy.deepcopy(payload["episode_agent_action_count"])
    env._episode_agent_override_count = copy.deepcopy(payload["episode_agent_override_count"])
    env._policy_fingerprint = payload.get("policy_fingerprint")
    env._partner_id = payload.get("partner_id")

    audit = env._audit
    a = payload["audit"]
    audit._event_hashes = list(a["event_hashes"])
    audit._head_hash = a["head_hash"]
    audit._last_event_hash = a["last_event_hash"]
    audit._length = int(a["length"])
    audit._fault_injection = copy.deepcopy(a.get("fault_injection") or {})
    audit._break_hash_prev_on_event_id = audit._fault_injection.get("break_hash_prev_on_event_id")

    tokens = env._tokens
    tokens._tokens = {}
    for td in payload["tokens"]:
        tok = Token.from_dict(td)
        tokens._tokens[tok.token_id] = tok
    tokens._next_id = int(payload["tokens_next_id"])

    specimens = env._specimens
    specimens._specimens = copy.deepcopy(payload["specimens"])
    specimens._last_id_match = copy.deepcopy(payload["specimen_last_id_match"])
    specimens._aliquot_to_specimen = copy.deepcopy(payload["aliquot_to_specimen"])

    qc = env._qc
    qc._device_qc_state = copy.deepcopy(payload["qc"]["device_qc_state"])
    qc._run_device = copy.deepcopy(payload["qc"]["run_device"])
    qc._results = copy.deepcopy(payload["qc"]["results"])

    critical = env._critical
    critical._result_criticality = copy.deepcopy(payload["critical"]["result_criticality"])
    critical._comm_records = copy.deepcopy(payload["critical"]["comm_records"])
    critical._attempts = copy.deepcopy(payload["critical"]["attempts"])
    critical._notification_mode_required = copy.deepcopy(
        payload["critical"]["notification_mode_required"]
    )

    queues = env._queues
    known = payload.get("known_device_ids")
    queues._known_device_ids = {d: True for d in known} if known is not None else None
    queues._queues = {}
    for did, qdata in (payload.get("queues") or {}).items():
        dq = DeviceQueue(device_id=qdata["device_id"])
        dq._next_tie_break = int(qdata.get("next_tie_break", 0))
        for it in qdata.get("items") or []:
            dq.items.append(
                DeviceQueueItem(
                    work_id=it["work_id"],
                    priority_class=it["priority_class"],
                    enqueued_ts_s=int(it["enqueued_ts_s"]),
                    requested_by_agent=it["requested_by_agent"],
                    reason_code=it.get("reason_code"),
                    tie_break=int(it.get("tie_break", 0)),
                )
            )
        queues._queues[did] = dq

    if env._device_store is not None:
        for did, ddata in (payload.get("devices") or {}).items():
            active = None
            if ddata.get("active_run"):
                ar = ddata["active_run"]
                active = ActiveRun(
                    run_id=ar["run_id"],
                    work_id=ar.get("work_id"),
                    specimen_ids=list(ar.get("specimen_ids") or []),
                    start_ts_s=int(ar["start_ts_s"]),
                    end_ts_s=int(ar["end_ts_s"]),
                    panel_id=ar.get("panel_id"),
                )
            env._device_store._devices[did] = DeviceRecord(
                device_id=ddata["device_id"],
                device_type=ddata["device_type"],
                zone_id=ddata.get("zone_id") or "",
                state=ddata["state"],
                active_run=active,
                type_config=copy.deepcopy(ddata.get("type_config") or {}),
            )
        env._device_store._total_busy_s = {
            k: int(v) for k, v in (payload.get("device_total_busy_s") or {}).items()
        }

    transport = env._transport
    transport._consignments = copy.deepcopy(payload["transport"]["consignments"])
    transport._next_consignment_id = int(payload["transport"]["next_consignment_id"])

    zones = env._zones
    zones._agent_positions = copy.deepcopy(payload["zones"]["agent_positions"])
    zones._door_open_since = copy.deepcopy(payload["zones"]["door_open_since"])
    zones._zone_frozen = copy.deepcopy(payload["zones"]["zone_frozen"])

    if getattr(env, "_enforcement_engine", None) is not None:
        counts: dict[tuple[str, str], int] = {}
        for row in payload.get("enforcement_violation_counts") or []:
            counts[(str(row[0]), str(row[1]))] = int(row[2])
        env._enforcement_engine._violation_counts = counts
