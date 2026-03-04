"""
Domain adapter registry: map domain_id to factory that returns LabTrustEnvAdapter.

Forkers can register a new domain (e.g. warehouse) by calling register_domain(id, factory).
The runner or entrypoint can then resolve the adapter by domain_id and run scenarios
or benchmarks against that domain without forking the engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from labtrust_gym.domain.lab_adapter import lab_domain_adapter_factory
from labtrust_gym.runner.adapter import LabTrustEnvAdapter

# Type for factory: (workflow_spec, config) -> LabTrustEnvAdapter
DomainAdapterFactoryType = Callable[
    [
        dict[str, Any],
        dict[str, Any] | None,
    ],
    LabTrustEnvAdapter,
]

_DOMAIN_REGISTRY: dict[str, DomainAdapterFactoryType] = {
    "hospital_lab": lab_domain_adapter_factory,
}


def register_domain(domain_id: str, factory: DomainAdapterFactoryType) -> None:
    """Register a domain adapter factory for domain_id. Overwrites if present."""
    _DOMAIN_REGISTRY[domain_id] = factory


def get_domain_adapter_factory(domain_id: str) -> DomainAdapterFactoryType | None:
    """Return the registered factory for domain_id, or None if not registered."""
    return _DOMAIN_REGISTRY.get(domain_id)


def list_domains() -> list[str]:
    """Return registered domain IDs (e.g. for CLI or docs)."""
    return sorted(_DOMAIN_REGISTRY.keys())
