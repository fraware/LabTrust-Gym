"""
Agent baselines: scripted, adversary, LLM, and MARL.

ScriptedOpsAgent, ScriptedRunnerAgent, ScriptedQcAgent, and ScriptedSupervisorAgent
are deterministic policy baselines. AdversaryAgent is a sloppy/adversarial baseline
for security benchmarks. LLM (large language model) and MARL (multi-agent reinforcement
learning) baselines live in baselines/llm and baselines/marl. Coordination methods
are in baselines/coordination.
"""

from __future__ import annotations

from labtrust_gym.baselines.adversary import AdversaryAgent
from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
from labtrust_gym.baselines.scripted_qc import ScriptedQcAgent
from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
from labtrust_gym.baselines.scripted_supervisor import ScriptedSupervisorAgent

__all__ = [
    "ScriptedOpsAgent",
    "ScriptedRunnerAgent",
    "ScriptedQcAgent",
    "ScriptedSupervisorAgent",
    "AdversaryAgent",
]
