"""
Example: short episode with ScriptedOpsAgent (ops_0) and ScriptedRunnerAgent (runners).

Runs LabTrustParallelEnv; ops_0 uses ScriptedOpsAgent; runner_0 (and optionally
runner_1) use ScriptedRunnerAgent (colocation, MOVE/TICK/OPEN_DOOR/START_RUN).
Other agents (qc_0, supervisor_0) use NOOP/TICK. Prints summary metrics.
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if __name__ == "__main__" and _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from labtrust_gym.baselines.scripted_ops import (
        ACTION_QUEUE_RUN,
        ScriptedOpsAgent,
    )
    from labtrust_gym.baselines.scripted_runner import (
        ACTION_MOVE,
        ACTION_OPEN_DOOR,
        ACTION_START_RUN,
        ScriptedRunnerAgent,
    )
    from labtrust_gym.envs.pz_parallel import (
        LabTrustParallelEnv,
        ACTION_TICK,
        DEFAULT_ZONE_IDS,
        DEFAULT_DEVICE_IDS,
    )
except ImportError as e:
    print(
        "Requires labtrust-gym and env deps. Install: pip install -e '.[env]'"
    )
    raise SystemExit(1) from e


def inject_work_list(obs: dict, work_list: list) -> dict:
    """Return a copy of obs with work_list set (for ops agent)."""
    out = dict(obs)
    out["work_list"] = work_list
    return out


def main() -> None:
    seed = 42
    max_steps = 25

    env = LabTrustParallelEnv(num_runners=2)
    obs, _ = env.reset(seed=seed)

    ops_agent = ScriptedOpsAgent(
        request_override_if_configured=True,
        max_queue_len=50,
    )
    runner_agent = ScriptedRunnerAgent(
        zone_ids=DEFAULT_ZONE_IDS,
        device_ids=DEFAULT_DEVICE_IDS,
    )

    synthetic_work = [
        {
            "work_id": "W1",
            "priority": "STAT",
            "deadline_s": 200,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": "DEV_CHEM_A_01",
        },
    ]

    total_violations = 0
    total_blocked = 0
    total_throughput = 0
    step = 0

    while step < max_steps:
        actions = {}
        action_infos = {}

        obs_ops = inject_work_list(obs.get("ops_0", {}), synthetic_work)
        a_idx, a_info = ops_agent.act(obs_ops, "ops_0")
        actions["ops_0"] = a_idx
        if a_idx == ACTION_QUEUE_RUN and a_info:
            action_infos["ops_0"] = a_info

        for agent_id in env.agents:
            if agent_id.startswith("runner_"):
                a_idx, a_info = runner_agent.act(
                    obs.get(agent_id, {}), agent_id
                )
                actions[agent_id] = a_idx
                if a_idx in (ACTION_MOVE, ACTION_OPEN_DOOR, ACTION_START_RUN):
                    if a_info:
                        action_infos[agent_id] = a_info
            elif agent_id not in actions:
                actions[agent_id] = ACTION_TICK if step % 2 == 1 else 0

        obs, rewards, term, trunc, infos = env.step(
            actions, action_infos=action_infos
        )

        total_violations += infos["ops_0"].get("violation_count", 0)
        total_blocked += infos["ops_0"].get("blocked_count", 0)
        if infos["ops_0"].get("result_released"):
            total_throughput += 1
        step += 1

    env.close()

    print("Scripted ops + scripted runners episode summary")
    print("  steps:            ", step)
    print("  total_violations:", total_violations)
    print("  total_blocked:   ", total_blocked)
    print("  throughput (result_released count):", total_throughput)


if __name__ == "__main__":
    main()
