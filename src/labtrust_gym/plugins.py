"""
Plugin discovery: load entry_points and register extensions (domains, coordination methods,
tasks, invariant handlers, security/safety providers, metrics aggregators).

Call load_plugins() once at CLI startup or first use of a registry so that installed
extension packages are discovered without the core explicitly importing them.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_LOADED = False


def load_plugins() -> None:
    """
    Discover and register plugins from setuptools entry_points.
    Idempotent: only runs once.
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return
    groups = (
        ("labtrust_gym.domains", _register_domain),
        ("labtrust_gym.coordination_methods", _register_coordination_method),
        ("labtrust_gym.tasks", _register_task),
        ("labtrust_gym.invariant_handlers", _register_invariant_handler),
        ("labtrust_gym.security_suite_providers", _register_security_suite_provider),
        ("labtrust_gym.safety_case_providers", _register_safety_case_provider),
        ("labtrust_gym.metrics_aggregators", _register_metrics_aggregator),
        ("labtrust_gym.benchmark_pack_loaders", _register_benchmark_pack_loader),
    )
    for group, register_fn in groups:
        try:
            eps = entry_points(group=group)
        except Exception:
            eps = []
        for ep in eps:
            try:
                register_fn(ep.name, ep.load())
            except Exception as e:
                logger.warning("Plugin %s %s failed to load: %s", group, ep.name, e)


def _register_domain(name: str, factory: Any) -> None:
    from labtrust_gym.domain.registry import register_domain

    register_domain(name, factory)


def _register_coordination_method(name: str, factory: Any) -> None:
    from labtrust_gym.baselines.coordination.registry import register_coordination_method

    register_coordination_method(name, factory)


def _register_task(name: str, task_class: Any) -> None:
    from labtrust_gym.benchmarks.tasks import register_task

    register_task(name, task_class)


def _register_invariant_handler(name: str, handler: Any) -> None:
    from labtrust_gym.engine.invariants_runtime import register_invariant_handler

    parts = name.split(".", 1)
    if len(parts) != 2:
        logger.warning("invariant_handlers entry point name must be 'type.check_name', got %s", name)
        return
    register_invariant_handler(parts[0], parts[1], handler)


def _register_security_suite_provider(name: str, provider: Any) -> None:
    from labtrust_gym.benchmarks.security_runner import register_security_suite_provider

    register_security_suite_provider(name, provider)


def _register_safety_case_provider(name: str, provider: Any) -> None:
    from labtrust_gym.security.safety_case import register_safety_case_provider

    register_safety_case_provider(name, provider)


def _register_metrics_aggregator(name: str, aggregator: Any) -> None:
    from labtrust_gym.benchmarks.metrics import register_metrics_aggregator

    register_metrics_aggregator(name, aggregator)


def _register_benchmark_pack_loader(name: str, loader: Any) -> None:
    from labtrust_gym.benchmarks.official_pack import register_benchmark_pack_loader

    register_benchmark_pack_loader(name, loader)

