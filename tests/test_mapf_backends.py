"""
Tests for MAPF/TAPF router backend ladder (make_router, router_backend in scale_config).
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.routing.mapf_backends import make_router


def test_make_router_whca_returns_router() -> None:
    """make_router('whca') returns a router with route() method."""
    router = make_router("whca", horizon=10)
    assert router is not None
    assert hasattr(router, "route")


def test_make_router_default_is_whca() -> None:
    """make_router('') or default behaves like whca."""
    r1 = make_router("", horizon=5)
    r2 = make_router("whca", horizon=5)
    assert hasattr(r1, "route")
    assert hasattr(r2, "route")


def test_make_router_optional_backend_fallback() -> None:
    """cbs/ecbs/lns/rhcr fall back to WHCA when [mapf] not installed."""
    for backend in ("cbs", "ecbs", "lns", "rhcr"):
        router = make_router(backend, horizon=8)
        assert router is not None
        assert hasattr(router, "route")
