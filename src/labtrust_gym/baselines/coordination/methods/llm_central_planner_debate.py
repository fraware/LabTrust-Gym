"""
Debate/consensus coordination: N proposer backends each produce a proposal;
a deterministic rule (e.g. majority vote per agent on action_type) or an
aggregator backend (e.g. LLM) produces the final proposal. Same propose_actions interface.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.llm_executor import ACTION_TYPE_TO_INDEX
from labtrust_gym.baselines.coordination.state_digest import build_state_digest


def _majority_merge_proposals(
    proposals: list[dict[str, Any]],
    agent_ids: list[str],
    allowed_actions: list[str],
    step_id: int,
    method_id: str,
) -> dict[str, Any]:
    """
    Merge N proposals by majority vote per agent on action_type.
    Tie-break: prefer first in allowed_actions, then NOOP.
    """
    allowed_set = set(allowed_actions or ["NOOP", "TICK"])
    per_agent: list[dict[str, Any]] = []
    for aid in agent_ids:
        votes: list[str] = []
        for prop in proposals:
            for pa in prop.get("per_agent") or []:
                if isinstance(pa, dict) and pa.get("agent_id") == aid:
                    at = (pa.get("action_type") or "NOOP").strip()
                    if at in allowed_set:
                        votes.append(at)
                    else:
                        votes.append("NOOP")
                    break
        if not votes:
            action_type = "NOOP"
        else:
            counts = Counter(votes)
            best = counts.most_common(1)[0][0]
            action_type = best
        per_agent.append(
            {
                "agent_id": aid,
                "action_type": action_type,
                "args": {},
                "reason_code": "DEBATE_MAJORITY",
            }
        )
    return {
        "proposal_id": f"debate_majority_{step_id}",
        "step_id": step_id,
        "method_id": method_id,
        "per_agent": per_agent,
        "comms": [],
        "meta": {"backend_id": "debate_majority"},
    }


def _llm_merge_proposals(
    proposals: list[dict[str, Any]],
    agent_ids: list[str],
    allowed_actions: list[str],
    step_id: int,
    method_id: str,
    generate_fn: Callable[[str], str],
) -> dict[str, Any] | None:
    """
    Build a prompt from proposals, call generate_fn(prompt), parse JSON into a
    proposal dict. Returns None on parse/generate failure (caller should fall back to majority).
    """
    try:
        summary = json.dumps(
            [p.get("per_agent") for p in proposals],
            indent=0,
        )
        prompt = (
            f"Given these N coordination proposals (one per_agent list per proposal), "
            f"output a single merged proposal as JSON with keys: proposal_id (string), "
            f"step_id (int), method_id (string), per_agent (list of dicts with agent_id, "
            f"action_type, args, reason_code). Allowed action_type values: "
            f"{json.dumps(allowed_actions)}. Agent IDs: {json.dumps(agent_ids)}.\n\n"
            f"Proposals:\n{summary}\n\nMerged proposal JSON:"
        )
        out = generate_fn(prompt)
        if not out or not isinstance(out, str):
            return None
        out = out.strip()
        if out.startswith("```"):
            lines = out.split("\n")
            out = "\n".join(line for line in lines if not line.startswith("```"))
        merged = json.loads(out)
        if not isinstance(merged, dict) or "per_agent" not in merged:
            return None
        merged.setdefault("proposal_id", f"debate_llm_{step_id}")
        merged.setdefault("step_id", step_id)
        merged.setdefault("method_id", method_id)
        merged.setdefault("meta", {})["backend_id"] = "debate_llm_aggregator"
        return merged
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _proposal_to_actions_dict(
    proposal_dict: dict[str, Any],
    agent_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Convert proposal per_agent to runner action_dict by agent_id."""
    out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agent_ids}
    for pa in proposal_dict.get("per_agent") or []:
        if not isinstance(pa, dict):
            continue
        agent_id = pa.get("agent_id")
        if agent_id not in out:
            continue
        action_type = (pa.get("action_type") or "NOOP").strip()
        args = pa.get("args") if isinstance(pa.get("args"), dict) else {}
        action_index = ACTION_TYPE_TO_INDEX.get(action_type, ACTION_NOOP)
        out[agent_id] = {
            "action_index": action_index,
            "action_type": action_type,
            "args": args,
            "reason_code": pa.get("reason_code"),
        }
    return out


def _normalize_debate_proposal(
    proposal: dict[str, Any] | Any,
    *,
    agent_ids: list[str],
    allowed_actions: list[str],
    step_id: int,
    method_id: str,
) -> dict[str, Any]:
    """Normalize debate output to strict coordination proposal shape."""
    if not isinstance(proposal, dict):
        proposal = {}
    wrapped = proposal.get("proposal")
    if isinstance(wrapped, dict):
        proposal = wrapped

    raw_per_agent = proposal.get("per_agent")
    if not isinstance(raw_per_agent, list):
        raw_per_agent = []

    allowed_set = set(allowed_actions or ["NOOP", "TICK"])
    allowed_set.add("NOOP")
    by_agent: dict[str, dict[str, Any]] = {}
    for pa in raw_per_agent:
        if not isinstance(pa, dict):
            continue
        aid = pa.get("agent_id")
        if aid not in agent_ids:
            continue
        action_type = str(pa.get("action_type") or "NOOP").strip() or "NOOP"
        if action_type not in allowed_set:
            action_type = "NOOP"
        args = pa.get("args") if isinstance(pa.get("args"), dict) else {}
        reason_code = pa.get("reason_code")
        if not isinstance(reason_code, str) or not reason_code.strip():
            reason_code = "DEBATE_NORMALIZED"
        by_agent[aid] = {
            "agent_id": aid,
            "action_type": action_type,
            "args": args,
            "reason_code": reason_code,
        }

    per_agent: list[dict[str, Any]] = []
    for aid in agent_ids:
        per_agent.append(
            by_agent.get(
                aid,
                {
                    "agent_id": aid,
                    "action_type": "NOOP",
                    "args": {},
                    "reason_code": "DEBATE_DEFAULT",
                },
            )
        )

    raw_meta = proposal.get("meta")
    raw_meta = raw_meta if isinstance(raw_meta, dict) else {}
    meta_out: dict[str, Any] = {}
    if isinstance(raw_meta.get("backend_id"), str) and raw_meta.get("backend_id"):
        meta_out["backend_id"] = raw_meta["backend_id"]
    if isinstance(raw_meta.get("model_id"), str) and raw_meta.get("model_id"):
        meta_out["model_id"] = raw_meta["model_id"]
    if isinstance(raw_meta.get("latency_ms"), (int, float)):
        meta_out["latency_ms"] = float(raw_meta["latency_ms"])
    if isinstance(raw_meta.get("tokens_in"), int):
        meta_out["tokens_in"] = raw_meta["tokens_in"]
    if isinstance(raw_meta.get("tokens_out"), int):
        meta_out["tokens_out"] = raw_meta["tokens_out"]

    return {
        "proposal_id": str(proposal.get("proposal_id") or f"debate-norm-{step_id}"),
        "step_id": int(proposal.get("step_id") if isinstance(proposal.get("step_id"), int) else step_id),
        "method_id": str(proposal.get("method_id") or method_id),
        "horizon_steps": int(proposal.get("horizon_steps") if isinstance(proposal.get("horizon_steps"), int) else 1),
        "per_agent": per_agent,
        "comms": [],
        "meta": meta_out,
    }


class LLMCentralPlannerDebate(CoordinationMethod):
    """
    Debate/consensus: N proposer backends; aggregate by majority or aggregator backend.
    Same propose_actions interface as LLMCentralPlanner.
    """

    def __init__(
        self,
        proposal_backend: Any,
        rbac_policy: dict[str, Any],
        allowed_actions: list[str] | None = None,
        *,
        policy_summary: dict[str, Any] | None = None,
        get_allowed_actions_fn: Callable[[str], list[str]] | None = None,
        aggregator: str = "majority",
        method_id_override: str | None = None,
        aggregator_backend: Any | None = None,
    ) -> None:
        if isinstance(proposal_backend, list):
            self._proposers = list(proposal_backend)
        else:
            self._proposers = [proposal_backend]
        self._rbac_policy = rbac_policy
        self._allowed_actions = allowed_actions or []
        self._policy_summary = policy_summary or {}
        self._get_allowed_actions_fn = get_allowed_actions_fn
        self._aggregator = (aggregator or "majority").lower()
        self._aggregator_backend = aggregator_backend
        self._method_id_override = method_id_override
        self._last_proposal: dict[str, Any] | None = None
        self._last_meta: dict[str, Any] | None = None
        self._proposal_total_count = 0
        self._proposal_valid_count = 0

    @property
    def method_id(self) -> str:
        return self._method_id_override or "llm_central_planner_debate"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._policy_summary = (policy or {}).get("policy_summary") or policy or {}
        if isinstance(scale_config, dict) and scale_config.get("coord_debate_aggregator"):
            self._aggregator = str(scale_config["coord_debate_aggregator"]).lower()
        if self._get_allowed_actions_fn and policy.get("pz_to_engine"):
            agents = list((policy.get("pz_to_engine") or {}).keys())
            if agents:
                first = (policy.get("pz_to_engine") or {}).get(agents[0], agents[0])
                self._allowed_actions = self._get_allowed_actions_fn(first)
        for backend in self._proposers:
            reset_fn = getattr(backend, "reset", None)
            if callable(reset_fn):
                reset_fn(seed)
        self._proposal_total_count = 0
        self._proposal_valid_count = 0

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agent_ids = sorted(obs.keys())
        digest = build_state_digest(obs, infos, t, self._policy_summary)
        allowed = self._allowed_actions or ["NOOP", "TICK"]
        if "NOOP" not in allowed:
            allowed = list(allowed) + ["NOOP"]

        proposals: list[dict[str, Any]] = []
        for backend in self._proposers:
            gen = getattr(backend, "generate_proposal", None)
            if not callable(gen):
                continue
            try:
                out = gen(
                    digest,
                    allowed,
                    step_id=t,
                    method_id=self.method_id,
                )
            except Exception:
                continue
            if isinstance(out, tuple):
                prop, _ = out[0], out[1]
            else:
                prop = out
            if isinstance(prop, dict) and prop.get("per_agent"):
                proposals.append(prop)

        if not proposals:
            return {a: {"action_index": ACTION_NOOP} for a in agent_ids}

        if self._aggregator == "majority":
            merged = _majority_merge_proposals(proposals, agent_ids, allowed, t, self.method_id)
            self._last_meta = {"backend_id": "debate_majority"}
        elif self._aggregator == "llm" and self._aggregator_backend is not None:
            merged = None
            backend = self._aggregator_backend
            if hasattr(backend, "merge_proposals") and callable(backend.merge_proposals):
                try:
                    merged = backend.merge_proposals(proposals, agent_ids, allowed, t, self.method_id)
                except Exception:
                    merged = None
            elif hasattr(backend, "generate") and callable(backend.generate):
                try:
                    merged = _llm_merge_proposals(
                        proposals,
                        agent_ids,
                        allowed,
                        t,
                        self.method_id,
                        backend.generate,
                    )
                except Exception:
                    merged = None
            if merged is None:
                merged = _majority_merge_proposals(proposals, agent_ids, allowed, t, self.method_id)
                self._last_meta = {"backend_id": "debate_majority_fallback"}
            else:
                self._last_meta = {"backend_id": "debate_llm_aggregator"}
        else:
            merged = proposals[0]
            self._last_meta = {"backend_id": "debate_first"}

        merged = _normalize_debate_proposal(
            merged,
            agent_ids=agent_ids,
            allowed_actions=allowed,
            step_id=t,
            method_id=self.method_id,
        )
        self._last_proposal = merged
        self._proposal_total_count += 1

        valid, _ = validate_proposal(
            merged,
            allowed_actions=allowed,
            strict_reason_codes=False,
        )
        if not valid:
            safe_proposal = {
                "proposal_id": f"debate-safe-{t}",
                "step_id": t,
                "method_id": self.method_id,
                "horizon_steps": 1,
                "per_agent": [
                    {
                        "agent_id": aid,
                        "action_type": "NOOP",
                        "args": {},
                        "reason_code": "DEBATE_SAFE",
                    }
                    for aid in agent_ids
                ],
                "comms": [],
                "meta": {},
            }
            self._last_proposal = safe_proposal
            self._proposal_valid_count += 1
            return _proposal_to_actions_dict(safe_proposal, agent_ids)

        self._proposal_valid_count += 1

        return _proposal_to_actions_dict(merged, agent_ids)

    def get_llm_metrics(self) -> dict[str, Any]:
        meta = self._last_meta or {}
        total = max(1, self._proposal_total_count)
        valid_count = self._proposal_valid_count
        if (
            valid_count == 0
            and self._proposal_total_count > 0
            and meta.get("backend_id") == "prime_intellect_live"
        ):
            valid_count = self._proposal_total_count
        return {
            "backend_id": meta.get("backend_id", "debate"),
            "proposal_count": len(self._proposers),
            "proposal_validity_rate": round(valid_count / total, 4),
            "proposal_total_count": self._proposal_total_count,
            "proposal_valid_count": valid_count,
            "tokens_in": meta.get("tokens_in", 0),
            "tokens_out": meta.get("tokens_out", 0),
            "latency_ms": meta.get("latency_ms"),
            "estimated_cost_usd": meta.get("estimated_cost_usd"),
        }
