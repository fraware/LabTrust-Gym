"""
Domain adapter layer: map workflow/domain spec to engine or env adapter.

Forkers can add new domains (e.g. warehouse, factory) by registering
a domain_id and a factory that returns a LabTrustEnvAdapter-compatible
environment. The hospital lab is the reference implementation.
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
