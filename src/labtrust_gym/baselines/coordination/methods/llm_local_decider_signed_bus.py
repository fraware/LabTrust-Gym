"""
LLM local decider over signed bus: each worker proposes ActionProposal from bounded
local view; proposals are signed and published on SignedMessageBus; deterministic
reconciler resolves conflicts; shield executes final set. Always uses SignedMessageBus
for proposals (epoch, replay protection). Tracks invalid_sig_count, replay_drop_count,
spoof_attempt_count, conflict_rate. Relevant injections: INJ-ID-SPOOF-001 (spoof
rejected), INJ-COMMS-POISON-001 (invalid/poisoned payloads rejected), INJ-ID-REPLAY-COORD-001
(replay detected and dropped).

Envelope (SOTA audit):
  - Typical steps per episode: N/A; horizon-driven.
  - LLM calls per step: 1 per agent (action proposal).
  - Fallback on timeout/refusal: NOOP for that agent; reconciler uses others.
  - max_latency_ms: N/A for live; bounded in llm_offline by deterministic backend.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
    ACTION_TICK,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    extract_zone_and_device_ids,
    get_queue_by_device,
    get_zone_from_obs,
)
from labtrust_gym.coordination.bus import SignedMessageBus
from labtrust_gym.coordination.identity import (
    COORD_REPLAY_DETECTED,
    COORD_SIGNATURE_INVALID,
    KEY_MESSAGE_TYPE,
    KEY_PAYLOAD,
    KEY_SENDER_ID,
    build_key_store,
    sign_message,
    verify_message_find_signer,
)

MESSAGE_TYPE_ACTION_PROPOSAL = "action_proposal"
MAX_LOCAL_VIEW_BYTES = 2048


def _build_local_view(
    agent_id: str,
    obs: dict[str, Any],
    zone_ids: list[str],
    device_ids: list[str],
    t: int,
) -> dict[str, Any]:
    """Bounded local view for one agent (deterministic, strictly bounded size)."""
    o = obs.get(agent_id) or {}
    zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
    qbd = get_queue_by_device(o)
    queue_summary: list[dict[str, Any]] = []
    for idx, dev_id in enumerate(device_ids[:16]):
        if idx >= len(qbd):
            break
        d = qbd[idx] if isinstance(qbd[idx], dict) else {}
        queue_summary.append({
            "device_id": str(d.get("device_id", dev_id))[:32],
            "queue_len": min(256, max(0, int(d.get("queue_len", 0)))),
            "queue_head": str(d.get("queue_head", ""))[:48],
        })
    return {
        "agent_id": agent_id[:64],
        "step_id": t,
        "zone_id": zone[:64],
        "queue_summary": queue_summary,
    }


def _action_proposal_to_action_dict(
    proposal: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    """Map ActionProposal to runner action_dict (action_index, action_type, args)."""
    action_type = (proposal.get("action_type") or "NOOP").strip()
    args = proposal.get("args")
    if not isinstance(args, dict):
        args = {}
    if action_type == "NOOP":
        return {"action_index": ACTION_NOOP}
    if action_type == "TICK":
        return {"action_index": ACTION_TICK}
    if action_type == "MOVE":
        return {
            "action_index": ACTION_MOVE,
            "action_type": "MOVE",
            "args": {
                "from_zone": args.get("from_zone"),
                "to_zone": args.get("to_zone"),
            },
        }
    if action_type == "START_RUN":
        return {
            "action_index": ACTION_START_RUN,
            "action_type": "START_RUN",
            "args": {
                "device_id": args.get("device_id"),
                "work_id": args.get("work_id"),
            },
        }
    return {"action_index": ACTION_NOOP}


def _reconcile(
    accepted: dict[str, dict[str, Any]],
    device_zone: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], int]:
    """
    Resolve conflicts: same device or same (device, work_id) -> one winner.
    Returns (final_actions_by_agent, overridden_count).
    """
    final: dict[str, dict[str, Any]] = {}
    overridden = 0
    # Sort agents for deterministic tie-break
    for agent_id in sorted(accepted.keys()):
        prop = accepted[agent_id]
        action_type = (prop.get("action_type") or "NOOP").strip()
        args = prop.get("args") or {}
        if action_type != "START_RUN":
            final[agent_id] = prop
            continue
        device_id = args.get("device_id")
        work_id = args.get("work_id") or ""
        if not device_id:
            final[agent_id] = prop
            continue
        conflict = False
        for other_id, other_prop in final.items():
            if (other_prop.get("action_type") or "").strip() != "START_RUN":
                continue
            oargs = other_prop.get("args") or {}
            if oargs.get("device_id") == device_id and (
                not work_id or oargs.get("work_id") == work_id
            ):
                conflict = True
                break
        if conflict:
            overridden += 1
            final[agent_id] = {
                "action_type": "NOOP",
                "args": {},
                "reason_code": None,
                "token_refs": [],
                "rationale": "reconciler_override",
                "confidence": 0.0,
                "safety_notes": "",
            }
        else:
            final[agent_id] = prop
    return final, overridden


class DeterministicLocalProposalBackend:
    """Deterministic backend: same (seed, agent_id, step, view_hash) -> same ActionProposal."""

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    def reset(self, seed: int) -> None:
        self._seed = seed

    def propose_action(
        self,
        local_view: dict[str, Any],
        allowed_actions: list[str],
        agent_id: str,
        step: int,
    ) -> dict[str, Any]:
        """Return ActionProposal (action_type, args, reason_code, confidence, safety_notes)."""
        h = hash((self._seed, agent_id, step, str(local_view.get("zone_id", ""))))
        rng = (h % (2**31)) + (2**31) if h < 0 else h
        use_tick = (rng % 2) == 0 and "TICK" in allowed_actions
        action_type = "TICK" if use_tick else "NOOP"
        return {
            "action_type": action_type,
            "args": {},
            "reason_code": None,
            "token_refs": [],
            "rationale": "deterministic",
            "confidence": 0.9,
            "safety_notes": "",
        }


class LLMLocalDeciderSignedBus(CoordinationMethod):
    """
    Per-agent local view -> ActionProposal -> sign -> bus -> reconcile -> final
    actions. Rejects messages failing signature or epoch; tracks invalid_sig,
    replay_drop, spoof_attempt; exposes coordination.comm and coordination.alloc.
    """

    def __init__(
        self,
        key_store: dict[str, tuple[Any, str]],
        proposal_backend: Any,
        *,
        identity_policy: dict[str, Any] | None = None,
        allowed_actions: list[str] | None = None,
    ) -> None:
        self._key_store = key_store
        self._backend = proposal_backend
        policy = identity_policy or {}
        policy.setdefault(
            "allowed_message_types",
            [MESSAGE_TYPE_ACTION_PROPOSAL],
        )
        self._bus = SignedMessageBus(
            key_store=key_store,
            identity_policy=policy,
            epoch_fn=lambda: self._current_epoch,
        )
        self._current_epoch = 0
        self._allowed_actions = allowed_actions or [
            "NOOP", "TICK", "MOVE", "START_RUN", "QUEUE_RUN", "OPEN_DOOR",
        ]
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._msg_count = 0
        self._invalid_sig_count = 0
        self._replay_drop_count = 0
        self._spoof_attempt_count = 0
        self._total_proposals = 0
        self._overridden_count = 0

    @property
    def method_id(self) -> str:
        return "llm_local_decider_signed_bus"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._bus.reset()
        self._zone_ids, self._device_ids, self._device_zone = (
            extract_zone_and_device_ids(policy)
        )
        self._current_epoch = 0
        self._msg_count = 0
        self._invalid_sig_count = 0
        self._replay_drop_count = 0
        self._spoof_attempt_count = 0
        self._total_proposals = 0
        self._overridden_count = 0
        if hasattr(self._backend, "reset"):
            self._backend.reset(seed)

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {
            a: {"action_index": ACTION_NOOP} for a in agents
        }
        if not agents:
            return out
        if not self._zone_ids and obs:
            sample = next(iter(obs.values()))
            self._zone_ids, self._device_ids, self._device_zone = (
                extract_zone_and_device_ids({}, obs_sample=sample)
            )
        if not self._zone_ids:
            self._zone_ids = ["Z_SORTING_LANES"]
        self._current_epoch = t

        envelopes: list[dict[str, Any]] = []
        for i, agent_id in enumerate(agents):
            local_view = _build_local_view(
                agent_id, obs, self._zone_ids, self._device_ids, t
            )
            prop = self._backend.propose_action(
                local_view,
                self._allowed_actions,
                agent_id,
                t,
            )
            self._total_proposals += 1
            nonce = t * max(len(agents), 1) + i
            env = sign_message(
                MESSAGE_TYPE_ACTION_PROPOSAL,
                prop,
                agent_id,
                nonce,
                t,
                self._key_store,
            )
            if env is not None:
                envelopes.append(env)
                self._msg_count += 1

        accepted: dict[str, dict[str, Any]] = {}
        for env in envelopes:
            accepted_bus, delivered, violation = self._bus.receive(env)
            if accepted_bus and delivered:
                sid = delivered.get(KEY_SENDER_ID)
                pl = delivered.get(KEY_PAYLOAD)
                if sid and isinstance(pl, dict):
                    accepted[sid] = pl
            elif violation:
                v_list = violation.get("violations") or [{}]
                reason = (v_list[0].get("reason_code") or "") if v_list else ""
                if reason == COORD_REPLAY_DETECTED:
                    self._replay_drop_count += 1
                elif reason == COORD_SIGNATURE_INVALID:
                    self._invalid_sig_count += 1
                    ok_any, actual_sender = verify_message_find_signer(
                        env, self._key_store
                    )
                    claimed = env.get(KEY_SENDER_ID)
                    if (
                        ok_any
                        and actual_sender
                        and claimed
                        and actual_sender != claimed
                    ):
                        self._spoof_attempt_count += 1

        final_proposals, overridden = _reconcile(
            accepted, self._device_zone
        )
        self._overridden_count += overridden

        for agent_id in agents:
            prop = final_proposals.get(agent_id)
            if prop is None:
                out[agent_id].setdefault("safety_notes", []).append("no_proposal")
                continue
            out[agent_id] = _action_proposal_to_action_dict(prop, agent_id)
            reason = prop.get("reason_code")
            if reason:
                out[agent_id].setdefault("safety_notes", []).append(reason)
            inv = prop.get("invariant_ids")
            if isinstance(inv, list) and inv:
                out[agent_id].setdefault("safety_notes", []).extend(inv)
        return out

    def get_comm_metrics(self) -> dict[str, Any]:
        """Extend coordination.comm: invalid_sig_count, replay_drop_count, spoof."""
        total = self._msg_count + self._invalid_sig_count + self._replay_drop_count
        invalid_rate = (
            self._invalid_sig_count / total if total > 0 else 0.0
        )
        return {
            "msg_count": self._msg_count,
            "drop_rate": 0.0,
            "invalid_sig_count": self._invalid_sig_count,
            "replay_drop_count": self._replay_drop_count,
            "invalid_msg_rate": round(invalid_rate, 4),
            "spoof_attempt_count": self._spoof_attempt_count,
        }

    def get_alloc_metrics(self) -> dict[str, Any]:
        """conflict_rate = fraction of proposals overridden by reconciler."""
        total = max(1, self._total_proposals)
        rate = self._overridden_count / total
        return {
            "conflict_rate": round(rate, 4),
            "overridden_count": self._overridden_count,
            "total_proposals": self._total_proposals,
        }
