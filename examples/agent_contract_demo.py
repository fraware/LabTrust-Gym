"""
Example agents with contract_version for testing load_agent contract checks.

- AgentV01: contract_version = "0.1" (matches AGENT_CONTRACT_VERSION).
- AgentV00: contract_version = "0.0" (used to trigger ContractVersionMismatch).
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.agent_api import LabTrustAgentBase


class AgentV01(LabTrustAgentBase):
    """Minimal agent with contract_version = '0.1' for version-accept tests."""

    def act(self, observation: dict[str, Any]) -> int:
        return 0


class AgentV00(LabTrustAgentBase):
    """Minimal agent with contract_version = '0.0' for version-mismatch tests."""

    contract_version = "0.0"

    def act(self, observation: dict[str, Any]) -> int:
        return 0
