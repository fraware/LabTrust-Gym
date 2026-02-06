"""
PettingZoo Parallel API wrapper for LabTrust-Gym.

Uses the existing CoreEnv under the hood; deterministic seeding via seed() and reset(seed=).
Agent set: ops_0 (scheduler), runner_0..runner_k, qc_0, supervisor_0.
Observation: aggregated (zone, doors, queues, specimen counts, qc, alarms, token counts).
Action: discrete action type + optional args; translation layer -> engine events.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from labtrust_gym.baselines.llm.shield import LLM_ACTION_FILTERED
from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.security.adversarial_detection import (
    detect_adversarial,
    load_adversarial_detection_policy,
)

# Optional: PettingZoo and Gymnasium (install with pip install -e ".[env]")
try:
    from gymnasium import spaces
    from pettingzoo.utils.env import ParallelEnv

    _pettingzoo_import_error: BaseException | None = None
except ImportError as _e:
    ParallelEnv = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]
    _pettingzoo_import_error = _e

# Default zone/device lists aligned with engine default layout (zones._default_layout)
DEFAULT_ZONE_IDS: list[str] = [
    "Z_SRA_RECEPTION",
    "Z_ACCESSIONING",
    "Z_SORTING_LANES",
    "Z_PREANALYTICS",
    "Z_CENTRIFUGE_BAY",
    "Z_ALIQUOT_LABEL",
    "Z_ANALYZER_HALL_A",
    "Z_ANALYZER_HALL_B",
    "Z_QC_SUPERVISOR",
    "Z_RESTRICTED_BIOHAZARD",
]
DEFAULT_DEVICE_IDS: list[str] = [
    "DEV_CENTRIFUGE_BANK_01",
    "DEV_ALIQUOTER_01",
    "DEV_CHEM_A_01",
    "DEV_CHEM_B_01",
    "DEV_HAEM_01",
    "DEV_COAG_01",
]
RESTRICTED_DOOR_ID = "D_RESTRICTED_AIRLOCK"
RESTRICTED_ZONE_ID = "Z_RESTRICTED_BIOHAZARD"

# Action type indices: NOOP, TICK, QUEUE_RUN (ops), MOVE, OPEN_DOOR, START_RUN (runner)
NUM_ACTION_TYPES = 6
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN_PLACEHOLDER = 2
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5


def _zone_to_index(zone_id: str | None, zone_ids: list[str]) -> int:
    if not zone_id:
        return 0
    try:
        return zone_ids.index(zone_id) + 1
    except ValueError:
        return 0


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


if ParallelEnv is None:
    raise ImportError(
        "LabTrustParallelEnv requires pettingzoo and gymnasium. "
        'Install with: pip install -e ".[env]"'
    ) from _pettingzoo_import_error


class LabTrustParallelEnv(ParallelEnv):  # type: ignore[misc]
    """
    PettingZoo Parallel environment wrapping CoreEnv.

    Agents: ops_0, runner_0..runner_{num_runners-1}, qc_0, supervisor_0.
    Deterministic: seed(seed) and reset(seed=seed) supported.
    """

    metadata = {"name": "LabTrustParallelEnv", "is_parallelizable": True}

    def __init__(
        self,
        num_runners: int = 2,
        num_adversaries: int = 0,
        num_insiders: int = 0,
        dt_s: int = 10,
        reward_config: dict[str, Any] | None = None,
        policy_dir: Path | None = None,
        log_path: Path | None = None,
        scale_agents: list[dict[str, str]] | None = None,
        scale_device_ids: list[str] | None = None,
        scale_zone_ids: list[str] | None = None,
    ) -> None:
        if ParallelEnv is None or spaces is None:
            raise ImportError(
                'PettingZoo and Gymnasium are required for LabTrustParallelEnv. Install with: pip install -e ".[env]"'
            )
        super().__init__()
        self._num_runners = max(0, num_runners)
        self._num_adversaries = max(0, num_adversaries)
        self._num_insiders = max(0, num_insiders)
        self._dt_s = max(1, dt_s)
        self._reward_config = reward_config or {}
        self._policy_dir = Path(policy_dir) if policy_dir else Path("policy")
        self._repo_root: Path | None = None
        if self._policy_dir.is_dir():
            self._repo_root = self._policy_dir.resolve().parent
        self._log_path = Path(log_path) if log_path else None
        self._episode_logger: Any | None = None
        self._last_observations: dict[str, Any] = {}
        self._observation_text_override: dict[str, Any] | None = None
        if self._log_path:
            from labtrust_gym.logging.episode_log import EpisodeLogger

            self._episode_logger = EpisodeLogger(self._log_path)

        if scale_agents and len(scale_agents) > 0:
            self.possible_agents = [f"worker_{i}" for i in range(len(scale_agents))]
            self._pz_to_engine = {
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
            }
            self._default_agent_zones = {
                f"worker_{i}": scale_agents[i].get("zone_id", "Z_SORTING_LANES")
                for i in range(len(scale_agents))
            }
            self._zone_ids = list(scale_zone_ids or DEFAULT_ZONE_IDS)
            self._device_ids = list(scale_device_ids or DEFAULT_DEVICE_IDS)
        else:
            self.possible_agents = ["ops_0"]
            for i in range(self._num_runners):
                self.possible_agents.append(f"runner_{i}")
            self.possible_agents.extend(["qc_0", "supervisor_0"])
            for i in range(self._num_adversaries):
                self.possible_agents.append(f"adversary_{i}")
            for i in range(self._num_insiders):
                self.possible_agents.append(f"adversary_insider_{i}")
            self._pz_to_engine = {}
            self._pz_to_engine["ops_0"] = "A_OPS_0"
            for i in range(self._num_runners):
                self._pz_to_engine[f"runner_{i}"] = f"A_RUNNER_{i}"
            self._pz_to_engine["qc_0"] = "A_QC_0"
            self._pz_to_engine["supervisor_0"] = "A_SUPERVISOR_0"
            for i in range(self._num_adversaries):
                self._pz_to_engine[f"adversary_{i}"] = f"A_ADVERSARY_{i}"
            for i in range(self._num_insiders):
                self._pz_to_engine[f"adversary_insider_{i}"] = f"A_INSIDER_{i}"
            self._default_agent_zones = {
                "ops_0": "Z_ANALYZER_HALL_A",
                "qc_0": "Z_QC_SUPERVISOR",
                "supervisor_0": "Z_QC_SUPERVISOR",
            }
            for i in range(self._num_runners):
                self._default_agent_zones[f"runner_{i}"] = "Z_SORTING_LANES"
            for i in range(self._num_adversaries):
                self._default_agent_zones[f"adversary_{i}"] = "Z_SORTING_LANES"
            for i in range(self._num_insiders):
                self._default_agent_zones[f"adversary_insider_{i}"] = "Z_SORTING_LANES"
            self._zone_ids = DEFAULT_ZONE_IDS
            self._device_ids = DEFAULT_DEVICE_IDS

        n_z = len(self._zone_ids) + 1
        n_d = len(self._device_ids)
        n_status = 8

        # Observation: dict of arrays (stable, compact)
        self.observation_spaces = {
            a: spaces.Dict(
                {
                    "my_zone_idx": spaces.Discrete(n_z),
                    "door_restricted_open": spaces.Discrete(2),
                    "door_restricted_duration_s": spaces.Box(
                        0.0, 1e6, (1,), dtype=np.float32
                    ),
                    "restricted_zone_frozen": spaces.Discrete(2),
                    "queue_lengths": spaces.Box(0, 100, (n_d,), dtype=np.int32),
                    "queue_has_head": spaces.Box(0, 1, (n_d,), dtype=np.int8),
                    "specimen_status_counts": spaces.Box(
                        0, 1000, (n_status,), dtype=np.int32
                    ),
                    "device_qc_pass": spaces.Box(0, 1, (n_d,), dtype=np.int8),
                    "log_frozen": spaces.Discrete(2),
                    "token_count_override": spaces.Box(0, 100, (1,), dtype=np.int32),
                    "token_count_restricted": spaces.Box(0, 100, (1,), dtype=np.int32),
                }
            )
            for a in self.possible_agents
        }

        # Action: discrete action type (MVP)
        self.action_spaces: dict[str, Any] = {
            a: spaces.Discrete(NUM_ACTION_TYPES) for a in self.possible_agents
        }

        self._engine = CoreEnv()
        self._step_count = 0
        self._seed_value: int | None = None
        self.agents = list(self.possible_agents)

    def seed(self, seed: int | None = None) -> None:
        """Set seed for deterministic behavior. Use with reset(seed=...)."""
        self._seed_value = seed

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if seed is not None:
            self._seed_value = seed
        rng_seed = self._seed_value if self._seed_value is not None else 0
        self._step_count = 0

        options = options or {}
        if options.get("initial_state"):
            initial_state = dict(options["initial_state"])
            if "agents" not in initial_state or not initial_state["agents"]:
                agents_list = [
                    {
                        "agent_id": self._pz_to_engine[a],
                        "zone_id": self._default_agent_zones[a],
                    }
                    for a in self.possible_agents
                ]
                initial_state["agents"] = agents_list
            initial_state.setdefault("system", {"now_s": 0, "downtime_active": False})
            initial_state.setdefault("specimens", [])
            initial_state.setdefault("tokens", [])
        else:
            agents_list = [
                {
                    "agent_id": self._pz_to_engine[a],
                    "zone_id": self._default_agent_zones[a],
                }
                for a in self.possible_agents
            ]
            initial_state = {
                "system": {"now_s": 0, "downtime_active": False},
                "agents": agents_list,
                "specimens": [],
                "tokens": [],
            }
        self._initial_state = initial_state
        self._observation_text_override = initial_state.get("_observation_text")
        self._engine.reset(
            initial_state,
            deterministic=True,
            rng_seed=rng_seed,
        )
        if self._episode_logger is not None:
            self._episode_logger.set_episode_meta(
                partner_id=initial_state.get("partner_id"),
                policy_fingerprint=initial_state.get("policy_fingerprint"),
                tool_registry_fingerprint=initial_state.get(
                    "tool_registry_fingerprint"
                ),
                rbac_policy_fingerprint=initial_state.get("rbac_policy_fingerprint"),
            )
        self.agents = list(self.possible_agents)
        observations = self._collect_observations()
        self._last_observations = dict(observations)
        infos: dict[str, dict[str, Any]] = {a: {} for a in self.agents}
        return observations, infos

    def _collect_observations(self) -> dict[str, Any]:
        obs = {}
        for agent in self.agents:
            engine_id = self._pz_to_engine.get(agent, agent)
            zone = self._engine.query(f"agent_zone('{engine_id}')")
            my_zone_idx = _zone_to_index(zone, self._zone_ids)

            try:
                door = self._engine.query(f"door_state('{RESTRICTED_DOOR_ID}')")
            except ValueError:
                door = {"open": False, "open_duration_s": 0}
            door_open = 1 if door.get("open") else 0
            door_duration = np.array(
                [float(door.get("open_duration_s", 0))], dtype=np.float32
            )

            try:
                zstate = self._engine.query(f"zone_state('{RESTRICTED_ZONE_ID}')")
            except ValueError:
                zstate = "normal"
            restricted_frozen = 1 if (zstate == "frozen") else 0

            queue_lengths = np.zeros(len(self._device_ids), dtype=np.int32)
            queue_has_head = np.zeros(len(self._device_ids), dtype=np.int8)
            queue_by_device: list[dict[str, Any]] = []
            for i, dev in enumerate(self._device_ids):
                try:
                    qlen = _safe_int(self._engine.query(f"queue_length('{dev}')"))
                    queue_lengths[i] = qlen
                    head = self._engine.query(f"queue_head('{dev}')")
                    queue_has_head[i] = 1 if head else 0
                    queue_by_device.append(
                        {
                            "device_id": dev,
                            "queue_head": str(head) if head else "",
                            "queue_len": qlen,
                        }
                    )
                except ValueError:
                    queue_by_device.append(
                        {
                            "device_id": dev,
                            "queue_head": "",
                            "queue_len": 0,
                        }
                    )

            try:
                counts = self._engine.query("specimen_counts")
            except ValueError:
                counts = {}
            status_order = [
                "arrived_at_reception",
                "accessioning",
                "accepted",
                "held",
                "rejected",
                "in_transit",
                "separated",
                "unknown",
            ]
            specimen_counts = np.zeros(len(status_order), dtype=np.int32)
            for i, st in enumerate(status_order):
                specimen_counts[i] = _safe_int(counts.get(st, 0))

            device_qc_pass = np.ones(len(self._device_ids), dtype=np.int8)
            for i, dev in enumerate(self._device_ids):
                try:
                    qc = self._engine.query(f"device_qc_state('{dev}')")
                    device_qc_pass[i] = 1 if (qc == "pass") else 0
                except ValueError:
                    pass

            try:
                log_frozen = self._engine.query("system_state('log_frozen')")
            except ValueError:
                log_frozen = "false"
            log_frozen_int = 1 if (log_frozen == "true") else 0

            try:
                active = self._engine.query("token_active")
            except ValueError:
                active = []
            if not isinstance(active, list):
                active = [active] if active else []
            token_count_override = sum(1 for t in active if "OVERRIDE" in str(t))
            token_count_restricted = sum(1 for t in active if "RESTRICTED" in str(t))

            t_s = self._step_count * self._dt_s
            transport_required = list(
                getattr(self, "_initial_state", {}).get("transport_required") or []
            )
            try:
                transport_consignments = self._engine.query("transport_consignments")
            except ValueError:
                transport_consignments = []
            try:
                prev_hash = self._engine.query("last_event_hash")
            except ValueError:
                prev_hash = ""
            next_step = self._step_count + 1
            next_event_id = f"pz_{agent}_{next_step}"
            next_t_s = next_step * self._dt_s
            role_id_obs = ""
            try:
                role_id_obs = (
                    self._engine.get_agent_role(engine_id)
                    if hasattr(self._engine, "get_agent_role")
                    else ""
                ) or ""
            except Exception:
                pass
            work_list: list[dict[str, Any]] = []
            releasable_result_ids: list[str] = []
            try:
                accepted_ids = self._engine.query("accepted_specimen_ids_not_in_queue")
                default_dev = ""
                if self._device_ids:
                    default_dev = self._device_ids[0]
                    for d in self._device_ids:
                        if "CHEM" in d or "HAEM" in d or "COAG" in d:
                            default_dev = d
                            break
                for sid in accepted_ids or []:
                    work_list.append(
                        {
                            "work_id": str(sid),
                            "device_id": default_dev,
                            "priority": "ROUTINE",
                            "deadline_s": 0,
                            "stability_ok": True,
                            "temp_ok": True,
                        }
                    )
            except ValueError:
                pass
            try:
                releasable_result_ids = list(
                    self._engine.query("releasable_result_ids") or []
                )
            except ValueError:
                pass
            obs[agent] = {
                "my_zone_idx": my_zone_idx,
                "door_restricted_open": door_open,
                "door_restricted_duration_s": door_duration,
                "restricted_zone_frozen": restricted_frozen,
                "queue_lengths": queue_lengths,
                "queue_has_head": queue_has_head,
                "specimen_status_counts": specimen_counts,
                "device_qc_pass": device_qc_pass,
                "log_frozen": log_frozen_int,
                "work_list": work_list,
                "releasable_result_ids": releasable_result_ids,
                "token_count_override": np.array(
                    [token_count_override], dtype=np.int32
                ),
                "token_count_restricted": np.array(
                    [token_count_restricted], dtype=np.int32
                ),
                "t_s": t_s,
                "transport_required": transport_required,
                "transport_consignments": transport_consignments,
                # State summary v0.2 (bounded, injection-hardened) for LLM
                "zone_id": zone or "",
                "site_id": getattr(self, "_site_id", None) or "SITE_HUB",
                "queue_by_device": queue_by_device,
                "prev_hash": prev_hash,
                "next_event_id": next_event_id,
                "next_t_s": np.array([next_t_s], dtype=np.int32),
                "role_id": role_id_obs,
            }
        return obs

    def _action_to_event(
        self,
        agent: str,
        action: int,
        action_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Translate discrete action (and optional action_info) to engine event."""
        engine_id = self._pz_to_engine.get(agent, agent)
        t_s = self._step_count * self._dt_s
        event_id = f"pz_{agent}_{self._step_count}"

        # Strip shield and LLM audit meta so not sent to engine (used in step() to augment result)
        _SHIELD_META_KEYS = ("_shield_filtered", "_shield_reason_code")
        _LLM_AUDIT_KEYS = (
            "_prompt_hash",
            "_policy_summary_hash",
            "_allowed_actions_hash",
            "_decoder_version",
            "_llm_decision",
        )
        _META_KEYS_STRIP = _SHIELD_META_KEYS + _LLM_AUDIT_KEYS
        info = {
            k: v for k, v in (action_info or {}).items() if k not in _META_KEYS_STRIP
        }
        # Custom event from action_info (e.g. insider adversary, LLM safe: RELEASE_RESULT, MOVE with signature, etc.)
        if info.get("action_type"):
            ev: dict[str, Any] = {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": str(info["action_type"]),
                "args": dict(info.get("args") or {}),
                "reason_code": info.get("reason_code"),
                "token_refs": list(info.get("token_refs") or []),
            }
            if info.get("key_id") is not None:
                ev["key_id"] = info["key_id"]
            if info.get("signature") is not None:
                ev["signature"] = info["signature"]
            return ev

        if action == ACTION_NOOP:
            return {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": "NOOP",
                "args": {},
                "reason_code": None,
                "token_refs": [],
            }
        if action == ACTION_TICK:
            return {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": "TICK",
                "args": {},
                "reason_code": None,
                "token_refs": [],
            }
        if action == ACTION_QUEUE_RUN_PLACEHOLDER:
            info = action_info or {}
            device_id = info.get("device_id") or (
                self._device_ids[0] if self._device_ids else ""
            )
            work_id = info.get("work_id", "OBS_PLACEHOLDER")
            prio = info.get("priority") or info.get("priority_class") or "ROUTINE"
            prio = (
                str(prio).upper()
                if str(prio).upper() in ("STAT", "URGENT", "ROUTINE")
                else "ROUTINE"
            )
            return {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": "QUEUE_RUN",
                "args": {
                    "device_id": device_id,
                    "work_id": work_id,
                    "priority_class": prio,
                },
                "reason_code": None,
                "token_refs": [],
            }
        if action == ACTION_MOVE:
            to_zone = info.get("to_zone", "")
            try:
                from_zone = self._engine.query(f"agent_zone('{engine_id}')")
            except ValueError:
                from_zone = ""
            return {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": "MOVE",
                "args": {"from_zone": from_zone, "to_zone": to_zone},
                "reason_code": None,
                "token_refs": [],
            }
        if action == ACTION_OPEN_DOOR:
            info = action_info or {}
            door_id = info.get("door_id", RESTRICTED_DOOR_ID)
            token_refs = info.get("token_refs")
            if not isinstance(token_refs, list):
                token_refs = []
            return {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": "OPEN_DOOR",
                "args": {"door_id": door_id},
                "reason_code": None,
                "token_refs": token_refs,
            }
        if action == ACTION_START_RUN:
            device_id = info.get("device_id", "")
            work_id = info.get("work_id", "")
            return {
                "event_id": event_id,
                "t_s": t_s,
                "agent_id": engine_id,
                "action_type": "START_RUN",
                "args": {"device_id": device_id, "work_id": work_id},
                "reason_code": None,
                "token_refs": [],
            }
        return {
            "event_id": event_id,
            "t_s": t_s,
            "agent_id": engine_id,
            "action_type": "NOOP",
            "args": {},
            "reason_code": None,
            "token_refs": [],
        }

    def step(
        self,
        actions: dict[str, Any],
        action_infos: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[
        dict[str, Any],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, dict[str, Any]],
    ]:
        self._step_count += 1
        self._step_count * self._dt_s

        rewards = {a: 0.0 for a in self.agents}
        violation_count = 0
        blocked_count = 0
        result_released = False
        action_infos = action_infos or {}
        step_results: list[dict[str, Any]] = []

        for agent in self.agents:
            action = actions.get(agent, ACTION_NOOP)
            if isinstance(action, np.integer | np.int64 | np.int32):
                action = int(action)
            event = self._action_to_event(
                agent, action, action_info=action_infos.get(agent)
            )
            # Adversarial detector: run on observation context (previous obs + LLM output)
            obs_ctx: dict[str, Any] = {}
            last_obs = (getattr(self, "_last_observations", None) or {}).get(
                agent
            ) or {}
            ai = action_infos.get(agent) or {}
            if last_obs.get("specimen_notes") is not None:
                obs_ctx["specimen_notes"] = last_obs["specimen_notes"]
            if last_obs.get("scenario_notes") is not None:
                obs_ctx["scenario_notes"] = last_obs["scenario_notes"]
            llm_dec = ai.get("_llm_decision")
            if isinstance(llm_dec, dict):
                prop = llm_dec.get("action_proposal")
                if isinstance(prop, dict) and prop.get("rationale"):
                    obs_ctx["llm_output_text"] = str(prop.get("rationale", ""))
            try:
                repo_root = getattr(self, "_repo_root", None)
                if repo_root is None and getattr(self, "_policy_dir", None):
                    pd = Path(self._policy_dir).resolve()
                    if pd.is_dir():
                        repo_root = pd.parent
                adv_policy = load_adversarial_detection_policy(repo_root=repo_root)
                det = detect_adversarial(obs_ctx, policy=adv_policy)
                threshold = int(adv_policy.get("severity_threshold", 1))
                if det.severity >= threshold and det.flags:
                    result = dict(self._engine.step(event))
                    result["emits"] = list(result.get("emits", [])) + [
                        "SECURITY_ALERT",
                        "SECURITY_EVENT",
                    ]
                    result["security_event"] = {
                        "detection_flags": det.flags,
                        "severity": det.severity,
                        "suggested_action": det.suggested_action,
                        "reason_code": det.reason_code,
                        "matched_pattern_ids": det.matched_pattern_ids,
                    }
                else:
                    result = self._engine.step(event)
            except Exception:
                result = self._engine.step(event)
            # LLM shield: if this agent's action was filtered, augment result with LLM_ACTION_FILTERED
            ai = action_infos.get(agent) or {}
            if ai.get("_shield_filtered") and ai.get("_shield_reason_code"):
                result = dict(result)
                result["emits"] = list(result.get("emits", [])) + [LLM_ACTION_FILTERED]
                result["blocked_reason_code"] = ai.get("_shield_reason_code")
                result["status"] = "BLOCKED"
            # LLM audit: add prompt_hash, policy_summary_hash, allowed_actions_hash, decoder_version to step output
            if any(
                ai.get(k) is not None
                for k in (
                    "_prompt_hash",
                    "_policy_summary_hash",
                    "_allowed_actions_hash",
                    "_decoder_version",
                )
            ):
                result = dict(result)
                if ai.get("_prompt_hash") is not None:
                    result["prompt_hash"] = ai["_prompt_hash"]
                if ai.get("_policy_summary_hash") is not None:
                    result["policy_summary_hash"] = ai["_policy_summary_hash"]
                if ai.get("_allowed_actions_hash") is not None:
                    result["allowed_actions_hash"] = ai["_allowed_actions_hash"]
                if ai.get("_decoder_version") is not None:
                    result["decoder_version"] = ai["_decoder_version"]
            # LLM_DECISION audit event: include in result and emits for episode log / evidence bundle
            if ai.get("_llm_decision") is not None:
                result = dict(result)
                llm_decision = dict(ai["_llm_decision"])
                llm_decision["event_id"] = event.get("event_id", "")
                result["llm_decision"] = llm_decision
                result["emits"] = list(result.get("emits", [])) + ["LLM_DECISION"]
            step_results.append(result)
            if self._episode_logger is not None:
                self._episode_logger.log_step(event, result)
            if result.get("status") == "BLOCKED":
                blocked_count += 1
            violation_count += len(result.get("violations", []))
            if "RELEASE_RESULT" in result.get("emits", []):
                result_released = True

        if self._reward_config.get("throughput_reward") and result_released:
            for a in self.agents:
                rewards[a] = float(self._reward_config.get("throughput_reward", 1.0))
        if self._reward_config.get("violation_penalty"):
            p = float(self._reward_config["violation_penalty"])
            for a in self.agents:
                rewards[a] -= p * violation_count
        if self._reward_config.get("blocked_penalty"):
            p = float(self._reward_config["blocked_penalty"])
            for a in self.agents:
                rewards[a] -= p * blocked_count

        observations = self._collect_observations()
        self._last_observations = dict(observations)
        terminations = {a: False for a in self.agents}
        truncations = {a: False for a in self.agents}
        infos = {
            a: {
                "violation_count": violation_count,
                "blocked_count": blocked_count,
                "step": self._step_count,
                "result_released": result_released,
                "_benchmark_step_results": step_results,
            }
            for a in self.agents
        }
        return observations, rewards, terminations, truncations, infos

    def observation_space(self, agent: str) -> Any:
        return self.observation_spaces[agent]

    def action_space(self, agent: str) -> Any:
        return self.action_spaces[agent]

    def close(self) -> None:
        if self._episode_logger is not None:
            self._episode_logger.close()
            self._episode_logger = None

    def get_timing_summary(self) -> dict[str, Any]:
        """Return timing_mode, episode_time_s, device_busy_s from engine. For benchmark utilization metrics."""
        return self._engine.get_timing_summary()

    def get_episode_time_s(self) -> int | None:
        """Episode duration in seconds: engine clock (simulated) or step_count * dt_s (explicit)."""
        summary = self._engine.get_timing_summary()
        ep_s = summary.get("episode_time_s")
        if ep_s is not None and isinstance(ep_s, int):
            return int(ep_s)
        return (self._step_count * self._dt_s) if self._step_count else None


def _hash_obs(obs: dict[str, Any]) -> str:
    """Stable hash of observation dict for determinism tests."""

    def _enc(o: Any) -> Any:
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, dict):
            return {k: _enc(v) for k, v in sorted(o.items())}
        return o

    return hashlib.sha256(json.dumps(_enc(obs), sort_keys=True).encode()).hexdigest()
