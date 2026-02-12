"""
Example agents with contract_version for testing load_agent contract checks.

- AgentV01: contract_version = "0.1" (matches AGENT_CONTRACT_VERSION).
- AgentV00: contract_version = "0.0" (used to trigger ContractVersionMismatch).
"""

from __future__ import annotations

from typing import Any


class AgentV01:
    """Minimal agent with contract_version = '0.1' for version-accept tests."""

    contract_version = "0.1"

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        pass

    def act(self, observation: dict[str, Any]) -> int:
        return 0


class AgentV00:
    """Minimal agent with contract_version = '0.0' for version-mismatch tests."""

    contract_version = "0.0"

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        pass

    def act(self, observation: dict[str, Any]) -> int:
        return 0
