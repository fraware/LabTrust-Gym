"""
Agent-driven episode driver: the agent (LLM) decides when to call step_lab to advance the env.

This module provides an alternative to the simulation-centric run_episode: the driver holds
the environment and exposes step_lab (and optionally get_current_obs, end_episode) as tools.
Time advances only when the agent calls step_lab. Same BenchmarkEnv, safety (shield, RBAC),
and risk injector semantics as the runner; only the loop owner changes.

See docs/architecture/simulation_llm_agentic.md and the agent-driven loop implementation plan.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.interface import action_dict_to_index_and_info
from labtrust_gym.baselines.coordination.llm_contract import validate_proposal
from labtrust_gym.baselines.coordination.llm_executor import (
    get_actions_from_proposal,
    shield_outcome_hash_from_step_results,
)
from labtrust_gym.baselines.coordination.telemetry import (
    build_contract_record,
    serialize_contract_record,
    validate_contract_record,
)
from labtrust_gym.benchmarks.env_protocol import BenchmarkEnv
from labtrust_gym.benchmarks.metrics import compute_episode_metrics, get_metrics_aggregator
from labtrust_gym.benchmarks.tasks import BenchmarkTask
from labtrust_gym.envs.action_contract import ACTION_INDEX_TO_TYPE

_LOG = logging.getLogger(__name__)


# --- Tool schema (for backends) ------------------------------------------------------------

STEP_LAB_TOOL_NAME = "step_lab"
GET_CURRENT_OBS_TOOL_NAME = "get_current_obs"
END_EPISODE_TOOL_NAME = "end_episode"
SUBMIT_MY_ACTION_TOOL_NAME = "submit_my_action"


def step_lab_tool_schema() -> dict[str, Any]:
    """OpenAI-style tool definition for step_lab(proposal). Proposal = coordinator per_agent format."""
    return {
        "type": "function",
        "function": {
            "name": STEP_LAB_TOOL_NAME,
            "description": "Advance the lab simulation by one step with the given coordination proposal (per_agent actions). Returns observations, rewards, terminations, truncations, and done.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal": {
                        "type": "object",
                        "description": "Coordination proposal with per_agent: list of {agent_id, action_type, args, reason_code}",
                        "properties": {
                            "per_agent": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "action_type": {"type": "string"},
                                        "args": {"type": "object"},
                                        "reason_code": {"type": "string"},
                                    },
                                },
                            },
                            "proposal_id": {"type": "string"},
                            "step_id": {"type": "integer"},
                            "comms": {"type": "array"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
        },
    }


def get_current_obs_tool_schema() -> dict[str, Any]:
    """OpenAI-style tool definition for get_current_obs(). No parameters."""
    return {
        "type": "function",
        "function": {
            "name": GET_CURRENT_OBS_TOOL_NAME,
            "description": "Return current observations (and infos) without advancing the simulation.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }


def end_episode_tool_schema() -> dict[str, Any]:
    """OpenAI-style tool definition for end_episode(). No parameters."""
    return {
        "type": "function",
        "function": {
            "name": END_EPISODE_TOOL_NAME,
            "description": "Mark the episode as done and stop stepping. Use when you want to finish early.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }


def submit_my_action_tool_schema() -> dict[str, Any]:
    """OpenAI-style tool definition for submit_my_action (multi-agentic mode)."""
    return {
        "type": "function",
        "function": {
            "name": SUBMIT_MY_ACTION_TOOL_NAME,
            "description": "Submit this agent's action for the current step (multi-agentic). When all agents have submitted, the coordinator combines and steps the env.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "This agent's ID (e.g. worker_0)."},
                    "action_type": {"type": "string", "description": "Action type: NOOP, TICK, MOVE, START_RUN, etc."},
                    "args": {"type": "object", "description": "Action arguments (e.g. from_zone, to_zone for MOVE)."},
                    "reason_code": {"type": "string", "description": "Optional reason code for the action."},
                },
                "required": ["agent_id", "action_type"],
                "additionalProperties": False,
            },
        },
    }


def submit_bid_tool_schema() -> dict[str, Any]:
    """OpenAI-style tool for submit_bid (multi-agentic with auction methods)."""
    return {
        "type": "function",
        "function": {
            "name": "submit_bid",
            "description": "Submit this agent's bid for the current step (auction methods).",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "bid": {
                        "type": "object",
                        "description": "Bid payload: cost, device_id, work_id, zone_id.",
                    },
                },
                "required": ["agent_id", "bid"],
                "additionalProperties": False,
            },
        },
    }


def agent_driven_tool_definitions(
    include_optional: bool = True,
    multi_agentic: bool = False,
) -> list[dict[str, Any]]:
    """Return list of tool definitions for agent-driven backends (OpenAI, etc.)."""
    if multi_agentic:
        out = [submit_my_action_tool_schema()]
        if include_optional:
            out.extend([get_current_obs_tool_schema(), end_episode_tool_schema()])
        return out
    out = [step_lab_tool_schema()]
    if include_optional:
        out.extend([get_current_obs_tool_schema(), end_episode_tool_schema()])
    return out


# --- AgentDrivenDriver ---------------------------------------------------------------------


class AgentDrivenDriver:
    """
    Holds the env and implements step_lab, get_current_obs, end_episode for the agent.
    Same safety (validate_proposal, get_actions_from_proposal/shield, risk_injector) as runner.
    """

    def __init__(
        self,
        env: BenchmarkEnv,
        task: BenchmarkTask,
        *,
        risk_injector: Any | None = None,
        blackboard_harness: Any | None = None,
        rbac_policy: dict[str, Any],
        policy_summary: dict[str, Any],
        allowed_actions: list[str],
        apply_shield: Callable[..., tuple[dict[str, Any], bool, str | None]],
        method_id: str = "agent_driven",
        log_path: Path | None = None,
        coord_decisions_path: Path | None = None,
        episode_logger_llm: Any | None = None,
        capability_profile: dict[str, Any] | None = None,
        mode: str = "single",
        coord_method: Any | None = None,
        round_timeout_s: float = 60.0,
    ) -> None:
        self._env = env
        self._task = task
        self._risk_injector = risk_injector
        self._blackboard_harness = blackboard_harness
        self._rbac_policy = rbac_policy
        self._policy_summary = policy_summary
        self._allowed_actions = allowed_actions or ["NOOP", "TICK"]
        self._apply_shield = apply_shield
        self._method_id = method_id
        self._log_path = log_path
        self._coord_decisions_path = coord_decisions_path
        self._episode_logger_llm = episode_logger_llm
        self._capability_profile = capability_profile or {}
        self._mode = str(mode).strip().lower() if mode else "single"
        if self._mode not in ("single", "multi_agentic"):
            self._mode = "single"
        self._coord_method = coord_method
        self._round_timeout_s = max(0.0, float(round_timeout_s))
        if self._mode == "multi_agentic" and self._coord_method is None:
            raise ValueError("coord_method is required when mode is multi_agentic")

        self._step_index = 0
        self._done = False
        self._obs: dict[str, Any] = {}
        self._infos: dict[str, dict[str, Any]] = {}
        self._dt_s = env.get_dt_s()
        self.step_results_per_step: list[list[dict[str, Any]]] = []
        self.t_s_list: list[int] = []
        self._queue_lengths_per_step: list[dict[str, int]] = []
        self._timing_mode = "explicit"
        self._pending_submissions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._round_start: float = 0.0

    @property
    def max_steps(self) -> int:
        return self._task.max_steps

    @property
    def agent_ids(self) -> list[str]:
        """Current list of agent IDs (from env). Use for building proposals when observations are not yet available."""
        return list(getattr(self._env, "agents", []) or [])

    def reset(self, episode_seed: int, initial_state: dict[str, Any]) -> None:
        """Reset env and driver state for a new episode."""
        self._obs, self._infos = self._env.reset(
            seed=episode_seed,
            options={"initial_state": initial_state},
        )
        if self._risk_injector is not None:
            self._risk_injector.reset(episode_seed, None)
            self._obs, _ = self._risk_injector.mutate_obs(self._obs)
        if self._blackboard_harness is not None:
            self._blackboard_harness.reset(episode_seed, clock_skew_config=None)
        self._step_index = 0
        self._done = False
        self.step_results_per_step = []
        self.t_s_list = []
        self._queue_lengths_per_step = []
        self._timing_mode = str(initial_state.get("timing_mode", "explicit")).strip().lower()
        if self._timing_mode not in ("explicit", "simulated"):
            self._timing_mode = "explicit"
        with self._lock:
            self._pending_submissions = {}
            self._round_start = time.monotonic()
        if self._coord_decisions_path is not None:
            self._coord_decisions_path.write_text("", encoding="utf-8")

    def is_done(self) -> bool:
        with self._lock:
            return self._done

    def get_current_obs(self) -> dict[str, Any]:
        """Return current observations (and optionally infos summary) without stepping."""
        obs = dict(self._obs)
        if self._risk_injector is not None:
            obs, _ = self._risk_injector.mutate_obs(obs)
        return {
            "observations": obs,
            "infos_summary": {k: type(v).__name__ for k, v in self._infos.items()},
            "step_index": self._step_index,
            "done": self._done,
        }

    def end_episode(self) -> dict[str, Any]:
        """Mark episode done; no env step."""
        self._done = True
        return {"done": True, "message": "Episode ended by agent."}

    def submit_my_action(
        self,
        agent_id: str,
        action_type: str,
        args: dict[str, Any] | None = None,
        reason_code: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit this agent's action for the current step (multi-agentic only).
        Store in pending_submissions; use try_advance_step() to run combine and env.step.
        """
        if self._mode != "multi_agentic":
            return {
                "received": False,
                "error": "multi_agentic_only",
                "message": "submit_my_action is only valid when driver mode is multi_agentic",
            }
        agent_ids = list(self._env.agents)
        if agent_id not in agent_ids:
            return {
                "received": False,
                "error": "unknown_agent",
                "message": f"agent_id {agent_id!r} not in env.agents",
            }
        with self._lock:
            if len(self._pending_submissions) == 0:
                self._round_start = time.monotonic()
            self._pending_submissions[agent_id] = {
                "action_type": (action_type or "NOOP").strip(),
                "args": dict(args or {}),
                "reason_code": (reason_code if isinstance(reason_code, str) else "") or "",
            }
            pending_count = len(self._pending_submissions)
        return {
            "received": True,
            "pending_count": pending_count,
            "required": len(agent_ids),
        }

    def submit_bid(
        self,
        agent_id: str,
        bid: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Submit this agent's bid for the current step (multi-agentic, auction methods).
        Stores pending_submissions[agent_id] = {"bid": bid} for coord_method.combine_submissions.
        """
        if self._mode != "multi_agentic":
            return {
                "received": False,
                "error": "multi_agentic_only",
                "message": "submit_bid is only valid when driver mode is multi_agentic",
            }
        agent_ids = list(self._env.agents)
        if agent_id not in agent_ids:
            return {
                "received": False,
                "error": "unknown_agent",
                "message": f"agent_id {agent_id!r} not in env.agents",
            }
        with self._lock:
            if len(self._pending_submissions) == 0:
                self._round_start = time.monotonic()
            self._pending_submissions[agent_id] = {"bid": dict(bid) if bid else {}}
            pending_count = len(self._pending_submissions)
        return {
            "received": True,
            "pending_count": pending_count,
            "required": len(agent_ids),
        }

    def try_advance_step(self, force: bool = False) -> dict[str, Any]:
        """
        In multi-agentic mode: if all agents have submitted (or force), run
        combine_submissions, mutate_actions, env.step; clear pending; return step result.
        Otherwise return stepped=False and list of pending agents.
        """
        if self._mode != "multi_agentic":
            return {"stepped": False, "error": "multi_agentic_only"}
        with self._lock:
            if self._done:
                return {"stepped": False, "reason": "already_done"}
            if self._step_index >= self.max_steps:
                self._done = True
                return {"stepped": False, "reason": "max_steps"}
        agent_ids = list(self._env.agents)
        with self._lock:
            if not force and len(self._pending_submissions) < len(agent_ids):
                elapsed = time.monotonic() - self._round_start
                if self._round_timeout_s > 0 and elapsed >= self._round_timeout_s:
                    force = True
                    missing = [aid for aid in agent_ids if aid not in self._pending_submissions]
                    _LOG.warning(
                        "round_timeout_s (%.1fs) exceeded (elapsed %.1fs); forcing advance; missing agents: %s",
                        self._round_timeout_s,
                        elapsed,
                        missing,
                    )
                else:
                    return {
                        "stepped": False,
                        "pending": list(self._pending_submissions.keys()),
                        "pending_count": len(self._pending_submissions),
                        "required": len(agent_ids),
                    }
            # Fill missing with NOOP
            for aid in agent_ids:
                if aid not in self._pending_submissions:
                    self._pending_submissions[aid] = {
                        "action_type": "NOOP",
                        "args": {},
                        "reason_code": "",
                    }
            if not hasattr(self._coord_method, "combine_submissions"):
                self._pending_submissions = {}
                return {"stepped": False, "error": "coord_method has no combine_submissions"}
            submissions_copy = dict(self._pending_submissions)
            self._pending_submissions = {}
            self._round_start = time.monotonic()
        actions_dict = self._coord_method.combine_submissions(
            submissions_copy,
            self._obs,
            self._infos,
            self._step_index,
        )
        try:
            per_agent = []
            for aid in self._env.agents:
                ad = actions_dict.get(aid, {"action_index": 0})
                idx = int(ad.get("action_index", 0))
                action_type = ad.get("action_type") or ACTION_INDEX_TO_TYPE.get(idx, "NOOP")
                per_agent.append(
                    {
                        "agent_id": aid,
                        "action_type": str(action_type).strip() or "NOOP",
                        "args": dict(ad.get("args") or {}),
                        "reason_code": (ad.get("reason_code") if isinstance(ad.get("reason_code"), str) else "") or "",
                    }
                )
            proposal_for_shield = {
                "proposal_id": f"multi_agentic-{self._step_index}",
                "step_id": self._step_index,
                "method_id": self._method_id,
                "per_agent": per_agent,
                "comms": [],
                "meta": {},
            }
            actions, action_infos = get_actions_from_proposal(
                self._env,
                proposal_for_shield,
                self._apply_shield,
                self._rbac_policy,
                self._policy_summary,
                self._capability_profile,
            )
            actions_dict = {
                aid: {"action_index": actions[aid], **(action_infos.get(aid) or {})} for aid in self._env.agents
            }
        except Exception as e:
            _LOG.warning("get_actions_from_proposal in try_advance_step failed: %s", e)
        if self._risk_injector is not None:
            actions_dict, _audit = self._risk_injector.mutate_actions(actions_dict)
        step_actions = {}
        step_action_infos = {}
        for aid in self._env.agents:
            ad = actions_dict.get(aid, {"action_index": 0})
            idx, info = action_dict_to_index_and_info(ad)
            step_actions[aid] = idx
            if info:
                step_action_infos[aid] = dict(info)
        obs, rewards, term, trunc, infos = self._env.step(step_actions, action_infos=step_action_infos)
        first_agent = list(self._env.agents)[0] if self._env.agents else None
        step_results = list((infos.get(first_agent) or {}).get("_benchmark_step_results", []) if first_agent else [])
        self.step_results_per_step.append(step_results)
        self.t_s_list.append(len(self.step_results_per_step) * self._dt_s)
        self._obs = obs
        self._infos = infos
        if self._risk_injector is not None:
            self._obs, _ = self._risk_injector.mutate_obs(self._obs)
        with self._lock:
            self._step_index += 1
            if any(term.values()) or any(trunc.values()) or self._step_index >= self.max_steps:
                self._done = True
            done = self._done
            step_index = self._step_index
        return {
            "stepped": True,
            "result": {
                "observations": self._obs,
                "rewards": rewards,
                "terminations": term,
                "truncations": trunc,
                "done": done,
                "step_index": step_index,
            },
        }

    def step_lab(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """
        Execute one env step with the given proposal. Validates, applies shield, risk_injector, then env.step.
        Returns step result dict for the agent (observations, rewards, terminations, truncations, done, step_index).
        """
        if self._done:
            return self._step_result_done(reason="already_done")
        if self._step_index >= self.max_steps:
            self._done = True
            return self._step_result_done(reason="max_steps")

        # Normalize to coordination proposal schema (required: proposal_id, step_id, method_id, per_agent, comms, meta)
        proposal_normalized = dict(proposal)
        proposal_normalized.setdefault("proposal_id", proposal.get("proposal_id") or f"agent_driven-{self._step_index}")
        proposal_normalized.setdefault("step_id", self._step_index)
        proposal_normalized.setdefault("method_id", self._method_id)
        proposal_normalized.setdefault("comms", proposal.get("comms") or [])
        proposal_normalized.setdefault("meta", proposal.get("meta") or {})
        # Schema requires per_agent[].reason_code to be string; allow null -> ""
        per_agent = proposal_normalized.get("per_agent") or []
        proposal_normalized["per_agent"] = [
            {**pa, "reason_code": pa.get("reason_code") if isinstance(pa.get("reason_code"), str) else ""}
            for pa in per_agent
            if isinstance(pa, dict)
        ]

        # Validate proposal
        valid, errors = validate_proposal(
            proposal_normalized,
            allowed_actions=self._allowed_actions,
            strict_reason_codes=False,
        )
        if not valid:
            return {
                "done": False,
                "step_index": self._step_index,
                "error": "validation_failed",
                "validation_errors": errors[:10],
                "observations": self._obs,
                "rewards": {},
                "terminations": {},
                "truncations": {},
            }
        # Ensure per_agent covers all env.agents (fill missing with NOOP)
        per_agent = proposal_normalized.get("per_agent") or []
        agent_ids = list(self._env.agents)
        per_agent_ids = sorted(
            pa.get("agent_id") for pa in per_agent if isinstance(pa, dict) and pa.get("agent_id") is not None
        )
        if not per_agent or per_agent_ids != sorted(agent_ids):
            by_id = {pa["agent_id"]: pa for pa in per_agent if isinstance(pa, dict) and pa.get("agent_id")}
            proposal_normalized["per_agent"] = []
            for aid in agent_ids:
                pa = by_id.get(aid) or {}
                rc = pa.get("reason_code")
                proposal_normalized["per_agent"].append(
                    {
                        "agent_id": aid,
                        "action_type": (pa.get("action_type") or "NOOP").strip(),
                        "args": dict(pa.get("args") or {}),
                        "reason_code": rc if isinstance(rc, str) else "",
                    }
                )

        # Convert to actions via shield
        try:
            actions, action_infos = get_actions_from_proposal(
                self._env,
                proposal_normalized,
                self._apply_shield,
                self._rbac_policy,
                self._policy_summary,
                self._capability_profile,
            )
        except Exception as e:
            _LOG.warning("get_actions_from_proposal failed: %s", e)
            return {
                "done": False,
                "step_index": self._step_index,
                "error": "shield_error",
                "message": str(e)[:200],
                "observations": self._obs,
                "rewards": {},
                "terminations": {},
                "truncations": {},
            }
        actions_dict = {
            aid: {"action_index": actions[aid], **(action_infos.get(aid) or {})} for aid in self._env.agents
        }
        if self._risk_injector is not None:
            actions_dict, audit_actions = self._risk_injector.mutate_actions(actions_dict)
        else:
            audit_actions = []
        # Build (actions, action_infos) for env.step
        step_actions: dict[str, int] = {}
        step_action_infos: dict[str, dict[str, Any]] = {}
        for aid in self._env.agents:
            ad = actions_dict.get(aid, {"action_index": 0})
            idx, info = action_dict_to_index_and_info(ad)
            step_actions[aid] = idx
            if info:
                step_action_infos[aid] = dict(info)

        obs, rewards, term, trunc, infos = self._env.step(step_actions, action_infos=step_action_infos)
        first_agent = list(self._env.agents)[0] if self._env.agents else None
        step_results = list((infos.get(first_agent) or {}).get("_benchmark_step_results", []) if first_agent else [])
        agent_list_step = list(self._env.agents)
        shield_outcome_hash = ""
        if agent_list_step:
            shield_outcome_hash = shield_outcome_hash_from_step_results(
                step_results[: len(agent_list_step)],
                agent_list_step,
            )
        if self._episode_logger_llm is not None and hasattr(self._episode_logger_llm, "log_llm_coord_proposal"):
            from labtrust_gym.baselines.coordination.llm_executor import _proposal_hash
            from labtrust_gym.logging.episode_log import build_llm_coord_proposal_entry

            record = build_llm_coord_proposal_entry(
                proposal_id=proposal_normalized.get("proposal_id", ""),
                step_id=self._step_index,
                canonical_proposal_hash=_proposal_hash(proposal_normalized),
                meta={},
                shield_outcome_hash=shield_outcome_hash or None,
                assurance_evidence=None,
            )
            self._episode_logger_llm.log_llm_coord_proposal(record)
        step_results.extend(audit_actions)
        if self._risk_injector is not None:
            extra = self._risk_injector.observe_step(step_results)
            step_results.extend(extra)
        self.step_results_per_step.append(step_results)
        self.t_s_list.append((len(self.step_results_per_step)) * self._dt_s)
        if self._timing_mode == "simulated" and hasattr(self._env, "get_device_queue_lengths"):
            q = self._env.get_device_queue_lengths()
            if q:
                self._queue_lengths_per_step.append(q)
        # Coord decisions log (same format as runner)
        if self._coord_decisions_path is not None:
            _shield_emits: list[dict[str, Any]] = []
            contract_record = build_contract_record(
                method_id=self._method_id,
                t_step=self._step_index,
                actions_dict=actions_dict,
                view_age_ms=None,
                view_age_ms_per_agent=None,
                plan_time_ms=None,
                invariants_considered=None,
                safety_shield_applied=bool(shield_outcome_hash),
                safety_shield_details=({"count": 1} if shield_outcome_hash else None),
            )
            if os.environ.get("LABTRUST_STRICT_COORD_CONTRACT") == "1":
                errs = validate_contract_record(contract_record)
                if errs:
                    raise ValueError(f"Coord contract validation failed at step {self._step_index}: {errs}")
            with self._coord_decisions_path.open("a", encoding="utf-8") as f:
                f.write(serialize_contract_record(contract_record))
        self._obs = obs
        self._infos = infos
        if self._risk_injector is not None:
            self._obs, _ = self._risk_injector.mutate_obs(self._obs)
        self._step_index += 1
        if any(term.values()) or any(trunc.values()) or self._step_index >= self.max_steps:
            self._done = True
        return {
            "observations": self._obs,
            "rewards": rewards,
            "terminations": term,
            "truncations": trunc,
            "infos_summary": {k: type(v).__name__ for k, v in infos.items()},
            "done": self._done,
            "step_index": self._step_index,
        }

    def _step_result_done(self, reason: str) -> dict[str, Any]:
        return {
            "observations": self._obs,
            "rewards": {},
            "terminations": {},
            "truncations": {},
            "infos_summary": {},
            "done": True,
            "step_index": self._step_index,
            "skip_reason": reason,
        }

    def get_metrics_inputs(self) -> dict[str, Any]:
        """Return inputs for compute_episode_metrics (step_results_per_step, t_s_list, timing_summary, etc.)."""
        timing_summary: dict[str, Any] = {}
        if hasattr(self._env, "get_timing_summary"):
            timing_summary = self._env.get_timing_summary()
        return {
            "step_results_per_step": self.step_results_per_step,
            "t_s_list": self.t_s_list,
            "timing_summary": timing_summary,
            "timing_mode": self._timing_mode,
            "queue_lengths_per_step": self._queue_lengths_per_step if self._queue_lengths_per_step else None,
        }


# --- run_episode_agent_driven ---------------------------------------------------------------


def run_episode_agent_driven(
    task: BenchmarkTask,
    episode_seed: int,
    env_factory: Any,
    agent_driven_backend: Any,
    *,
    log_path: Path | None = None,
    initial_state_overrides: dict[str, Any] | None = None,
    risk_injector: Any | None = None,
    comms_config: Any | None = None,
    episode_id: int = 0,
    run_dir: Path | None = None,
    metrics_aggregator_id: str | None = None,
    repo_root: Path | None = None,
    rbac_policy: dict[str, Any] | None = None,
    policy_summary: dict[str, Any] | None = None,
    allowed_actions: list[str] | None = None,
    apply_shield: Any | None = None,
    method_id: str = "agent_driven",
    env: BenchmarkEnv | None = None,
    mode: str = "single",
    coord_method: Any | None = None,
    round_timeout_s: float = 60.0,
) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    """
    Run one episode in agent-driven mode: backend.run_episode(driver) runs until driver.is_done().
    Returns (metrics, step_results_per_step) like run_episode.
    """
    from labtrust_gym.baselines.llm.shield import apply_shield as default_apply_shield
    from labtrust_gym.logging.episode_log import EpisodeLogger

    calibration = (initial_state_overrides or {}).get("calibration")
    initial_state = task.get_initial_state(episode_seed, calibration=calibration, policy_root=repo_root)
    if initial_state_overrides:
        initial_state = {**initial_state, **initial_state_overrides}
    if env is None:
        env = env_factory(
            initial_state=initial_state,
            reward_config=task.reward_config,
            log_path=log_path,
        )
        env.reset(seed=episode_seed, options={"initial_state": initial_state})
    else:
        env.reset(seed=episode_seed, options={"initial_state": initial_state})
    effective_policy = initial_state.get("effective_policy") or initial_state.get("policy_summary") or {}
    rbac = rbac_policy or effective_policy.get("rbac") or {}
    policy_psum = policy_summary or effective_policy.get("policy_summary") or effective_policy
    allowed = allowed_actions or effective_policy.get("allowed_actions") or ["NOOP", "TICK"]
    shield_fn = apply_shield if apply_shield is not None else default_apply_shield
    coord_decisions_path: Path | None = None
    episode_logger_llm: Any | None = None
    if log_path is not None:
        coord_decisions_path = log_path.parent / "coord_decisions.jsonl"
        episode_logger_llm = EpisodeLogger(path=log_path)
    blackboard_harness = None
    if comms_config is not None and hasattr(task, "scale_config") and task.scale_config is not None:
        from labtrust_gym.coordination.harness import BlackboardHarness

        agent_ids = list(env.agents)
        device_ids = env.get_device_ids()
        zone_ids = env.get_zone_ids()
        cfg = comms_config
        blackboard_harness = BlackboardHarness(
            agent_ids=agent_ids,
            device_ids=device_ids,
            zone_ids=zone_ids,
            comms_config=cfg,
            seed=episode_seed,
        )
        blackboard_harness.reset(episode_seed, clock_skew_config=None)
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=risk_injector,
        blackboard_harness=blackboard_harness,
        rbac_policy=rbac,
        policy_summary=policy_psum,
        allowed_actions=allowed,
        apply_shield=shield_fn,
        method_id=method_id,
        log_path=log_path,
        coord_decisions_path=coord_decisions_path,
        episode_logger_llm=episode_logger_llm,
        mode=mode,
        coord_method=coord_method,
        round_timeout_s=round_timeout_s,
    )
    driver.reset(episode_seed, initial_state)
    run_fn = getattr(agent_driven_backend, "run_episode", None)
    if not callable(run_fn):
        raise ValueError("agent_driven_backend must implement run_episode(driver)")
    run_fn(driver)
    timing_summary = driver.get_metrics_inputs()
    step_results_per_step = timing_summary["step_results_per_step"]
    t_s_list = timing_summary["t_s_list"]
    timing_mode = timing_summary.get("timing_mode", "explicit")
    episode_time_s = (timing_summary.get("timing_summary") or {}).get("episode_time_s")
    device_busy_s = (timing_summary.get("timing_summary") or {}).get("device_busy_s")
    queue_lengths = timing_summary.get("queue_lengths_per_step")
    injection_metrics = None
    injection_id = None
    if risk_injector is not None:
        injection_metrics = risk_injector.get_metrics()
        injection_id = getattr(risk_injector, "injection_id", None)
    env.close()
    aggregator = get_metrics_aggregator(metrics_aggregator_id) if metrics_aggregator_id else None
    compute_fn = aggregator if aggregator is not None else compute_episode_metrics
    metrics = compute_fn(
        step_results_per_step,
        t_s_per_step=t_s_list,
        sla_turnaround_s=task.sla_turnaround_s,
        attack_start_step=getattr(task, "attack_start_step", None),
        insider_attack_steps=getattr(task, "insider_attack_steps", None),
        timing_mode=timing_mode,
        episode_time_s=episode_time_s,
        device_busy_s=device_busy_s,
        queue_lengths_per_step=queue_lengths,
        injection_metrics=injection_metrics,
        injection_id=injection_id,
    )
    if coord_method is not None:
        from labtrust_gym.benchmarks.result_builder import normalize_llm_economics

        llm_metrics = getattr(coord_method, "get_llm_metrics", lambda: None)()
        llm_repair_metrics = getattr(coord_method, "get_llm_repair_metrics", lambda: None)()
        if llm_repair_metrics is not None:
            metrics.setdefault("coordination", {})["llm_repair"] = llm_repair_metrics
        if llm_metrics is not None or llm_repair_metrics is not None:
            steps_count = metrics.get("steps", 1)
            metrics.setdefault("coordination", {})["llm"] = normalize_llm_economics(
                llm_metrics, llm_repair_metrics, steps_count
            )
    if episode_logger_llm is not None and hasattr(episode_logger_llm, "close"):
        episode_logger_llm.close()
    return metrics, step_results_per_step


# --- Deterministic backend (for testing) ---------------------------------------------------


class DeterministicAgentDrivenBackend:
    """
    Minimal agent-driven backend for tests: calls step_lab with NOOP proposal
    until driver.is_done() or max_steps. No LLM.
    """

    def __init__(self, max_steps_to_run: int | None = None) -> None:
        self._max_steps_to_run = max_steps_to_run

    def run_episode(self, driver: AgentDrivenDriver) -> None:
        """Call step_lab with NOOP per agent until done or max_steps."""
        limit = self._max_steps_to_run if self._max_steps_to_run is not None else driver.max_steps
        agent_ids = driver.agent_ids
        if not agent_ids:
            return
        noop_proposal = {
            "proposal_id": "deterministic-noop",
            "step_id": 0,
            "per_agent": [
                {"agent_id": aid, "action_type": "NOOP", "args": {}, "reason_code": None} for aid in agent_ids
            ],
            "comms": [],
        }
        for step in range(limit):
            if driver.is_done():
                break
            noop_proposal["step_id"] = step
            driver.step_lab(noop_proposal)


class DeterministicMultiAgenticBackend:
    """
    Multi-agentic backend for tests: each step, each agent submits NOOP via
    submit_my_action; then try_advance_step runs combine and env.step.
    Use with driver mode=multi_agentic and coord_method.
    """

    def __init__(self, max_steps_to_run: int | None = None) -> None:
        self._max_steps_to_run = max_steps_to_run

    def run_episode(self, driver: AgentDrivenDriver) -> None:
        """Per step: submit_my_action for each agent, then try_advance_step until done."""
        limit = self._max_steps_to_run if self._max_steps_to_run is not None else driver.max_steps
        for _ in range(limit):
            if driver.is_done():
                break
            for aid in driver.agent_ids:
                driver.submit_my_action(aid, "NOOP", {}, None)
            out = driver.try_advance_step(force=False)
            if not out.get("stepped") and out.get("error"):
                break


class ParallelMultiAgenticBackend:
    """
    Multi-agentic backend that runs N agent workers in parallel per step.
    Each worker is produced by agent_backend_factory(agent_id); the callable
    receives (driver, agent_id) and must call driver.submit_my_action (or
    submit_bid) before returning. After timeout or all submitted, try_advance_step
    is called (force=True on timeout to fill missing with NOOP).
    """

    def __init__(
        self,
        agent_backend_factory: Callable[[str], Callable[[AgentDrivenDriver, str], None]],
        max_workers: int | None = None,
        round_timeout_s: float = 60.0,
        max_steps_to_run: int | None = None,
    ) -> None:
        self._agent_backend_factory = agent_backend_factory
        self._max_workers = max(1, max_workers if max_workers is not None else 64)
        self._round_timeout_s = max(0.0, float(round_timeout_s))
        self._max_steps_to_run = max_steps_to_run

    def _run_one_agent(self, driver: AgentDrivenDriver, agent_id: str) -> None:
        """Run one agent for the current step; agent must call driver.submit_my_action or submit_bid."""
        fn = self._agent_backend_factory(agent_id)
        fn(driver, agent_id)

    def run_episode(self, driver: AgentDrivenDriver) -> None:
        """Per step: launch one thread per agent, wait up to round_timeout_s, then try_advance_step(force=True if timeout)."""
        limit = self._max_steps_to_run if self._max_steps_to_run is not None else driver.max_steps
        agent_ids = driver.agent_ids
        if not agent_ids:
            return
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(agent_ids))) as pool:
            for _ in range(limit):
                if driver.is_done():
                    break
                futures = {pool.submit(self._run_one_agent, driver, aid): aid for aid in agent_ids}
                done_set, not_done_set = wait(
                    list(futures.keys()),
                    timeout=self._round_timeout_s if self._round_timeout_s > 0 else None,
                )
                for f in not_done_set:
                    f.cancel()
                out = driver.try_advance_step(force=True)
                if not out.get("stepped") and out.get("error"):
                    break
