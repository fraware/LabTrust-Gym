"""
Group-Evolving coordination: Variant A (Experience Sharing Deterministic) and
Variant B (Group-Evolving Study). Both use experience buffer + sharing protocol;
Variant B adds evolution loop and checkpoints.

Envelope (SOTA audit)
--------------------
steps: horizon-driven; share_interval, summary_max_items bound sharing.
llm_calls_per_step: 0.
fallback: N/A (deterministic).
max_latency_ms: bounded (local compute + neighbor message size).
"""

from __future__ import annotations

import os
import random
from collections import deque
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.group_evolving.evolution_loop import (
    default_genome,
    fitness_from_metrics,
    mutate_genome,
    recombine_genomes,
    save_checkpoint,
    select_top_k,
)
from labtrust_gym.baselines.coordination.group_evolving.experience_buffer import (
    ExperienceBuffer,
)
from labtrust_gym.baselines.coordination.group_evolving.sharing_protocol import (
    build_experience_message,
    summaries_to_routing_weights,
)
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
    log_frozen,
    queue_has_head,
)
from labtrust_gym.engine.zones import build_adjacency_set


def _bfs_one_step(
    start: str,
    goal: str,
    adjacency: set[tuple[str, str]],
) -> str | None:
    if start == goal:
        return None
    seen: set[str] = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [])])
    while queue:
        node, path = queue.popleft()
        neighbors = sorted([b for (a, b) in adjacency if a == node and b not in seen])
        for n in neighbors:
            seen.add(n)
            new_path = path + [n]
            if n == goal:
                return new_path[0]
            queue.append((n, new_path))
    return None


def _propose_actions_with_weights(
    obs: dict[str, Any],
    t: int,
    zone_ids: list[str],
    device_ids: list[str],
    device_zone: dict[str, str],
    adjacency: set[tuple[str, str]],
    routing_weights: dict[str, float],
) -> dict[str, dict[str, Any]]:
    """Kernel: greedy worklist + MOVE with zone preference by routing_weights."""
    agents = sorted(obs.keys())
    out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}
    if not device_ids or not zone_ids:
        return out

    worklist: list[tuple[int, float, str, str, str]] = []
    for agent_id in agents:
        o = obs.get(agent_id) or {}
        if log_frozen(o):
            continue
        my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
        qbd = get_queue_by_device(o)
        for idx, dev_id in enumerate(device_ids):
            if not queue_has_head(o, idx):
                continue
            dev_zone = device_zone.get(dev_id, "")
            if my_zone != dev_zone:
                continue
            head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
            prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
            w = routing_weights.get(dev_zone, 1.0)
            worklist.append((prio, w, dev_id, head or "W", dev_zone))
    worklist.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
    assigned: set[str] = set()
    used_work: set[tuple[str, str]] = set()

    for _prio, _w, device_id, work_id, zone_id in worklist:
        if (device_id, work_id) in used_work:
            continue
        for agent_id in agents:
            if agent_id in assigned:
                continue
            o = obs.get(agent_id) or {}
            my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
            if my_zone != zone_id:
                continue
            assigned.add(agent_id)
            used_work.add((device_id, work_id))
            out[agent_id] = {
                "action_index": ACTION_START_RUN,
                "action_type": "START_RUN",
                "args": {"device_id": device_id, "work_id": work_id},
            }
            break

    for agent_id in agents:
        if out[agent_id].get("action_index") != ACTION_NOOP:
            continue
        o = obs.get(agent_id) or {}
        if log_frozen(o):
            continue
        my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
        goal = zone_ids[0] if zone_ids else "Z_SORTING_LANES"
        best_weight = -1.0
        for dev_id in device_ids:
            z = device_zone.get(dev_id)
            if not z:
                continue
            qbd = get_queue_by_device(o)
            for idx, d in enumerate(device_ids):
                if d != dev_id:
                    continue
                if idx < len(qbd) and (qbd[idx].get("queue_len") or 0) > 0:
                    w = routing_weights.get(z, 1.0)
                    if w > best_weight:
                        best_weight = w
                        goal = z
                    break
        if my_zone == goal:
            continue
        next_z = _bfs_one_step(my_zone, goal, adjacency)
        if next_z:
            out[agent_id] = {
                "action_index": ACTION_MOVE,
                "action_type": "MOVE",
                "args": {"from_zone": my_zone, "to_zone": next_z},
            }

    if t > 0 and t % 3 == 0:
        for agent_id in agents:
            if out[agent_id].get("action_index") == ACTION_NOOP:
                out[agent_id] = {"action_index": ACTION_TICK}
                break
    return out


class ExperienceSharingDeterministic(CoordinationMethod):
    """
    Variant A: CI-safe. Experience buffer within episode; summarize at fixed
    intervals; share summaries and derive routing weights; use weights in
    job routing. Deterministic given seed.
    """

    def __init__(
        self,
        share_interval: int = 5,
        summary_max_items: int = 50,
    ) -> None:
        self._share_interval = max(1, share_interval)
        self._summary_max_items = summary_max_items
        self._buffer = ExperienceBuffer()
        self._shared_summaries: list[dict[str, Any]] = []
        self._routing_weights: dict[str, float] = {}
        self._seed = 0
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._last_obs: dict[str, Any] = {}
        self._last_actions: dict[str, str] = {}
        self._last_agent_order: list[str] = []
        self._step = 0

    @property
    def method_id(self) -> str:
        return "group_evolving_experience_sharing"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._seed = seed
        self._buffer.clear()
        self._shared_summaries = []
        self._routing_weights = {}
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
        layout = (policy or {}).get("zone_layout") or {}
        self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        self._step = 0
        self._last_obs = {}
        self._last_actions = {}
        self._last_agent_order = []

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        if not self._zone_ids and obs:
            sample = obs.get(agents[0]) if agents else {}
            self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids({}, obs_sample=sample)
        self._last_agent_order = agents
        self._last_obs = dict(obs)
        self._step = t

        if t > 0 and t % self._share_interval == 0 and len(self._buffer) > 0:
            summaries = self._buffer.summarize(seed=self._seed, max_items=self._summary_max_items)
            msg = build_experience_message(summaries, step=t)
            self._shared_summaries.append(msg)
            self._routing_weights = summaries_to_routing_weights(
                self._shared_summaries,
                default_weight=1.0,
            )

        out = _propose_actions_with_weights(
            obs,
            t,
            self._zone_ids,
            self._device_ids,
            self._device_zone,
            self._adjacency,
            self._routing_weights,
        )
        for aid, ad in out.items():
            idx = ad.get("action_index", ACTION_NOOP)
            self._last_actions[aid] = (
                "START_RUN"
                if idx == ACTION_START_RUN
                else ("MOVE" if idx == ACTION_MOVE else ("TICK" if idx == ACTION_TICK else "NOOP"))
            )
        return out

    def on_step_result(self, step_outputs: list[dict[str, Any]]) -> None:
        agents = self._last_agent_order
        if not agents or not self._last_obs:
            return
        n = min(len(step_outputs), len(agents))
        for i in range(n):
            agent_id = agents[i]
            result = step_outputs[i]
            o = self._last_obs.get(agent_id) or {}
            zone_id = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or "_"
            action_type = self._last_actions.get(agent_id) or "NOOP"
            reward = 1.0 if "RELEASE_RESULT" in (result.get("emits") or []) else 0.0
            violations_count = len(result.get("violations") or [])
            blocked = result.get("blocked_reason_code")
            self._buffer.append(
                agent_id=agent_id,
                step=self._step,
                zone_id=zone_id,
                action_type=action_type,
                reward=reward,
                violations_count=violations_count,
                blocked_reason_code=blocked,
            )


class GroupEvolvingStudy(CoordinationMethod):
    """
    Variant B: Study mode. Population of genomes; after each episode compute
    fitness, select top K, mutate/recombine; save checkpoint each generation.
    Requires run_dir in scale_config (or LABTRUST_GROUP_EVOLVING_RUN_DIR).
    """

    def __init__(
        self,
        share_interval: int = 5,
        summary_max_items: int = 50,
        population_size: int = 4,
        top_k: int = 2,
        episodes_per_generation: int = 2,
    ) -> None:
        self._share_interval = max(1, share_interval)
        self._summary_max_items = summary_max_items
        self._population_size = max(2, population_size)
        self._top_k = min(top_k, population_size)
        self._episodes_per_generation = max(1, episodes_per_generation)
        self._buffer = ExperienceBuffer()
        self._shared_summaries = []
        self._seed = 0
        self._zone_ids = []
        self._device_ids = []
        self._device_zone = {}
        self._adjacency = set()
        self._last_obs = {}
        self._last_actions = {}
        self._last_agent_order = []
        self._step = 0
        self._run_dir: Path | None = None
        self._population: list[dict[str, Any]] = []
        self._current_genome_idx = 0
        self._generation = 0
        self._episode_count = 0
        self._checkpoint_sha: str | None = None
        self._update_count = 0
        self._gen_fitness: list[tuple[dict[str, Any], float]] = []

    @property
    def method_id(self) -> str:
        return "group_evolving_study"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._seed = seed
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
        layout = (policy or {}).get("zone_layout") or {}
        self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        self._last_obs = {}
        self._last_actions = {}
        self._last_agent_order = []
        self._step = 0
        run_dir = scale_config.get("run_dir") or (
            scale_config.get("log_path") and str(Path(scale_config["log_path"]).parent)
        )
        if run_dir is None:
            run_dir = os.environ.get("LABTRUST_GROUP_EVOLVING_RUN_DIR")
        self._run_dir = Path(run_dir) if run_dir else None
        if self._generation == 0 and not self._population:
            self._population = [default_genome(self._zone_ids) for _ in range(self._population_size)]
            self._current_genome_idx = 0
        self._buffer.clear()
        self._shared_summaries = []

    def _routing_weights(self) -> dict[str, float]:
        if not self._population:
            return {}
        g = self._population[self._current_genome_idx]
        return g.get("routing_weights") or {}

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        if not self._zone_ids and obs:
            sample = obs.get(agents[0]) if agents else {}
            self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids({}, obs_sample=sample)
        self._last_agent_order = agents
        self._last_obs = dict(obs)
        self._step = t
        if t > 0 and t % self._share_interval == 0 and len(self._buffer) > 0:
            summaries = self._buffer.summarize(seed=self._seed, max_items=self._summary_max_items)
            msg = build_experience_message(summaries, step=t)
            self._shared_summaries.append(msg)
        weights = self._routing_weights()
        if self._shared_summaries:
            weights = summaries_to_routing_weights(self._shared_summaries, default_weight=1.0)
            for z, w in self._routing_weights().items():
                weights[z] = weights.get(z, 1.0) * 0.5 + w * 0.5
        out = _propose_actions_with_weights(
            obs,
            t,
            self._zone_ids,
            self._device_ids,
            self._device_zone,
            self._adjacency,
            weights,
        )
        for aid, ad in out.items():
            idx = ad.get("action_index", ACTION_NOOP)
            self._last_actions[aid] = (
                "START_RUN"
                if idx == ACTION_START_RUN
                else ("MOVE" if idx == ACTION_MOVE else ("TICK" if idx == ACTION_TICK else "NOOP"))
            )
        return out

    def on_step_result(self, step_outputs: list[dict[str, Any]]) -> None:
        agents = self._last_agent_order
        if not agents or not self._last_obs:
            return
        n = min(len(step_outputs), len(agents))
        for i in range(n):
            agent_id = agents[i]
            result = step_outputs[i]
            o = self._last_obs.get(agent_id) or {}
            zone_id = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or "_"
            action_type = self._last_actions.get(agent_id) or "NOOP"
            reward = 1.0 if "RELEASE_RESULT" in (result.get("emits") or []) else 0.0
            violations_count = len(result.get("violations") or [])
            blocked = result.get("blocked_reason_code")
            self._buffer.append(
                agent_id=agent_id,
                step=self._step,
                zone_id=zone_id,
                action_type=action_type,
                reward=reward,
                violations_count=violations_count,
                blocked_reason_code=blocked,
            )

    def on_episode_end(self, episode_metrics: dict[str, Any]) -> None:
        self._episode_count += 1
        episode_id = episode_metrics.get("_episode_id", self._episode_count - 1)
        fit = fitness_from_metrics(episode_metrics)
        self._gen_fitness.append((dict(self._population[self._current_genome_idx]), fit))
        if (episode_id + 1) % self._episodes_per_generation != 0:
            self._current_genome_idx = (self._current_genome_idx + 1) % len(self._population)
            return
        population_with_fitness = list(self._gen_fitness)
        self._gen_fitness = []
        top = select_top_k(population_with_fitness, self._top_k, self._seed + self._generation)
        if not top:
            self._current_genome_idx = 0
            return
        rng = random.Random(self._seed + self._generation)
        new_pop: list[dict[str, Any]] = []
        for i in range(self._population_size):
            if i < len(top):
                new_pop.append(dict(top[i]))
            else:
                g1, g2 = rng.sample(top, 2)
                child = recombine_genomes(g1, g2, self._seed + self._generation + i)
                child = mutate_genome(child, self._seed + self._generation + i * 1000)
                new_pop.append(child)
        self._population = new_pop
        self._current_genome_idx = 0
        self._generation += 1
        self._update_count += 1
        mutation_log_entries = [
            {
                "gen": self._generation,
                "episode_id": episode_id,
                "fitness_sample": population_with_fitness[0][1] if population_with_fitness else 0,
            }
        ]
        if self._run_dir and self._run_dir.is_dir():
            self._checkpoint_sha = save_checkpoint(
                self._run_dir,
                self._generation - 1,
                self._population,
                self._buffer,
                mutation_log_entries,
                self._seed,
            )

    def get_learning_metadata(self) -> dict[str, Any] | None:
        out: dict[str, Any] = {
            "enabled": True,
            "checkpoint_sha": self._checkpoint_sha,
            "update_count": self._update_count,
            "buffer_size": len(self._buffer),
        }
        if self._run_dir and (self._run_dir / "coordination_learning").is_dir():
            out["artifact_dir"] = "coordination_learning"
        return out
