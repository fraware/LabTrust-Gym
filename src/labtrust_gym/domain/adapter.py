"""
Domain adapter interface: factory that builds an env adapter from a workflow spec and config.

The runner (golden runner, benchmark runner) uses LabTrustEnvAdapter. A domain adapter
factory takes a workflow spec (and optional config) and returns an instance that
implements LabTrustEnvAdapter so the same runner can drive different domains
(hospital lab, warehouse, etc.) without forking the engine or runner code.
"""

from __future__ import annotations

from typing import Any, Protocol

from labtrust_gym.runner.adapter import LabTrustEnvAdapter


class DomainAdapterFactory(Protocol):
    """
    Protocol for a domain adapter factory.

    Given a workflow spec (conforming to workflow_spec.v0.1) and optional config,
    returns an environment adapter that implements LabTrustEnvAdapter (reset, step, query).
    """

    def __call__(
        self,
        workflow_spec: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> LabTrustEnvAdapter:
        """Build and return an env adapter for this domain."""
        ...
