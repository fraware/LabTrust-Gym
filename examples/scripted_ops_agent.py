"""
Example: short episode with ScriptedOpsAgent (ops_0) and random runners.

Runs LabTrustParallelEnv for a fixed number of steps; ops_0 uses
ScriptedOpsAgent (STAT/EDF, conservative stability, QC routing). Other
agents use deterministic "random" (fixed seed) actions. Prints summary
metrics: violations, blocked, throughput (result_released count).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

# Add project src for imports when run as script (package lives in src/)
_root = Path(__file__).resolve().parent.parent
_src = _root / "src"
if __name__ == "__main__" and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

try:
    from labtrust_gym.baselines.scripted_ops import (
        ACTION_QUEUE_RUN,
        ScriptedOpsAgent,
    )
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
except ImportError as e:
    print("Requires labtrust-gym and env deps. Install: pip install -e '.[env]'")
    raise SystemExit(1) from e


def inject_work_list(obs: dict, work_list: list) -> dict:
    """Return a copy of obs with work_list set (for ops agent)."""
    out = dict(obs)
    out["work_list"] = work_list
    return out


def main() -> None:
    seed = 42
    max_steps = 20
    random.seed(seed)

    env = LabTrustParallelEnv(num_runners=2)
    obs, _ = env.reset(seed=seed)
    agent = ScriptedOpsAgent(
        request_override_if_configured=True,
        max_queue_len=50,
    )

    total_violations = 0
    total_blocked = 0
    total_throughput = 0
    step = 0

    # Synthetic work list so scripted ops has something to queue (env may not expose work_list yet)
    synthetic_work = [
        {
            "work_id": "W1",
            "priority": "STAT",
            "deadline_s": 200,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": "DEV_CHEM_A_01",
        },
        {
            "work_id": "W2",
            "priority": "ROUTINE",
            "deadline_s": 500,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": "DEV_CHEM_B_01",
        },
    ]

    while step < max_steps:
        # Inject work_list for ops_0 so scripted agent can choose QUEUE_RUN
        obs_ops = inject_work_list(obs.get("ops_0", {}), synthetic_work)
        action_idx, action_info = agent.act(obs_ops, "ops_0")

        actions = {"ops_0": action_idx}
        action_infos = {}
        if action_idx == ACTION_QUEUE_RUN and action_info:
            action_infos["ops_0"] = action_info

        for a in env.agents:
            if a != "ops_0":
                actions[a] = random.randint(0, 2)  # NOOP, TICK, QUEUE_RUN

        obs, rewards, terminations, truncations, infos = env.step(actions, action_infos=action_infos)

        total_violations += infos["ops_0"].get("violation_count", 0)
        total_blocked += infos["ops_0"].get("blocked_count", 0)
        if infos["ops_0"].get("result_released"):
            total_throughput += 1
        step += 1

    env.close()

    print("Scripted ops + random runners episode summary")
    print("  steps:           ", step)
    print("  total_violations:", total_violations)
    print("  total_blocked:   ", total_blocked)
    print("  throughput (result_released count):", total_throughput)
    print("  on_time_rate:     N/A (define from specimen deadlines in full impl)")


if __name__ == "__main__":
    main()
