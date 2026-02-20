"""
Blackboard and view replicas harness for coordination tasks.

Derives facts from engine step outputs and optional environment queries, appends
them to BlackboardLog, and delivers updates to ViewReplicas via CommsModel.
KernelContext exposes global_log and view_snapshots for coordination methods
that need a shared view of lab state.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.coordination.blackboard import BlackboardLog
from labtrust_gym.coordination.clock_model import ClockModel
from labtrust_gym.coordination.comms_model import CommsConfig, CommsModel
from labtrust_gym.coordination.views import (
    TYPE_AGENT_ZONE,
    TYPE_DEVICE_STATUS,
    TYPE_QUEUE_HEAD,
    TYPE_SPECIMEN_STATUS,
    TYPE_ZONE_OCCUPANCY,
    ViewReplica,
)


def derive_facts_from_step(
    step_results: list[dict[str, Any]],
    env: Any,
    t: int,
    device_ids: list[str] | None = None,
    zone_ids: list[str] | None = None,
    agent_ids: list[str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Derive blackboard facts from step_results and env state.
    Returns list of (event_type, payload) for BlackboardLog.append.
    """
    facts: list[tuple[str, dict[str, Any]]] = []
    engine = getattr(env, "_engine", None)
    if engine is None:
        return facts

    device_ids = device_ids or []
    zone_ids = zone_ids or []
    agent_ids = agent_ids or []

    for dev in device_ids:
        try:
            head = engine.query(f"queue_head('{dev}')")
            facts.append(
                (
                    TYPE_QUEUE_HEAD,
                    {
                        "device_id": dev,
                        "queue_head_work_id": str(head) if head else None,
                    },
                )
            )
        except (ValueError, TypeError):
            pass

    pz_to_engine = getattr(env, "_pz_to_engine", {}) or {}
    for aid in agent_ids:
        engine_id = pz_to_engine.get(aid, aid)
        try:
            zone = engine.query(f"agent_zone('{engine_id}')")
            facts.append(
                (
                    TYPE_AGENT_ZONE,
                    {"agent_id": aid, "zone_id": str(zone) if zone else ""},
                )
            )
        except (ValueError, TypeError):
            pass

    for zid in zone_ids:
        try:
            state = engine.query(f"zone_state('{zid}')")
            facts.append(
                (
                    TYPE_ZONE_OCCUPANCY,
                    {"zone_id": zid, "state": str(state), "agent_ids": []},
                )
            )
        except (ValueError, TypeError):
            pass

    for dev in device_ids:
        try:
            qc = engine.query(f"device_qc_state('{dev}')")
            status = str(qc) if qc is not None else "idle"
            facts.append((TYPE_DEVICE_STATUS, {"device_id": dev, "status": status}))
        except (ValueError, TypeError):
            pass

    try:
        counts = engine.query("specimen_counts")
        if isinstance(counts, dict):
            for spec_id, count in list(counts.items())[:50]:
                facts.append(
                    (
                        TYPE_SPECIMEN_STATUS,
                        {"specimen_id": spec_id, "count": count},
                    )
                )
    except (ValueError, TypeError):
        pass

    return facts


class BlackboardHarness:
    """
    Holds BlackboardLog, CommsModel, and one ViewReplica per agent.
    step(step_results, env, t) appends facts, delivers via comms, applies to replicas.
    """

    __slots__ = (
        "_log",
        "_comms",
        "_replicas",
        "_agent_ids",
        "_last_delivery_id",
        "_device_ids",
        "_zone_ids",
        "_clock_model",
    )

    def __init__(
        self,
        agent_ids: list[str],
        device_ids: list[str] | None = None,
        zone_ids: list[str] | None = None,
        comms_config: CommsConfig | None = None,
        seed: int = 0,
    ) -> None:
        self._agent_ids = sorted(agent_ids)
        self._log = BlackboardLog()
        self._comms = CommsModel(
            agent_ids=self._agent_ids,
            config=comms_config,
            seed=seed,
        )
        self._replicas = {aid: ViewReplica(aid) for aid in self._agent_ids}
        self._last_delivery_id = -1
        self._device_ids = device_ids or []
        self._zone_ids = zone_ids or []
        self._clock_model: ClockModel | None = None

    def reset(
        self,
        seed: int,
        clock_skew_config: tuple[dict[str, float], dict[str, float]] | None = None,
    ) -> None:
        """
        Reset log, comms, and replicas for new episode.
        clock_skew_config: optional (skew_ppm_dict, offset_ms_dict) per agent (e.g. from INJ-CLOCK-SKEW-001).
        """
        self._log = BlackboardLog()
        self._comms.reset(seed)
        self._replicas = {aid: ViewReplica(aid) for aid in self._agent_ids}
        self._last_delivery_id = -1
        if clock_skew_config is not None:
            skew_ppm, offset_ms = clock_skew_config
            self._clock_model = ClockModel(
                agent_ids=self._agent_ids,
                skew_ppm=skew_ppm,
                offset_ms=offset_ms,
                seed=seed,
            )
        else:
            self._clock_model = None

    def step(
        self,
        step_results: list[dict[str, Any]],
        env: Any,
        t: int,
    ) -> None:
        """
        Append facts derived from step_results and env to log;
        deliver new events to replicas via comms; apply to each replica.
        """
        facts = derive_facts_from_step(
            step_results,
            env,
            t,
            device_ids=self._device_ids,
            zone_ids=self._zone_ids,
            agent_ids=self._agent_ids,
        )
        for event_type, payload in facts:
            self._log.append(t, t, event_type, payload)
        new_events = self._log.events_since(self._last_delivery_id)
        deliveries = self._comms.apply(new_events, t)
        for aid in self._agent_ids:
            self._replicas[aid].apply_batch(deliveries.get(aid) or [], processing_step=t)
        if new_events:
            self._last_delivery_id = new_events[-1].id

    @property
    def global_log(self) -> BlackboardLog:
        return self._log

    def view_snapshots(self) -> dict[str, dict[str, Any]]:
        """Per-agent snapshot for KernelContext (decentralized methods)."""
        return {aid: self._replicas[aid].snapshot() for aid in self._agent_ids}

    def get_comm_metrics(self) -> dict[str, Any]:
        """Comm metrics for results coordination block."""
        return self._comms.get_metrics()
