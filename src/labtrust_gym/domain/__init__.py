"""
Domain adapter layer: pluggable domains (lab, warehouse, etc.) as env adapters.

Register a domain_id and a factory that returns a LabTrustEnvAdapter-compatible
environment. The hospital lab is the built-in domain; forkers can add others
(e.g. warehouse, factory) without changing the runner or benchmarks.
"""

from labtrust_gym.domain.registry import (
    get_domain_adapter_factory,
    list_domains,
    register_domain,
)

__all__ = [
    "get_domain_adapter_factory",
    "list_domains",
    "register_domain",
]
