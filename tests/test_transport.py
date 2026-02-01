"""
Multi-site transport: route legality, determinism, chain-of-custody invariants.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.engine.transport import (
    TRANSPORT_ROUTE_FORBIDDEN,
    TRANSPORT_TEMP_EXCURSION,
    TransportStore,
    load_sites_policy,
    _route_allowed,
    _get_route,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_sites_policy() -> None:
    """Load sites_policy.v0.1.yaml; has sites and routes."""
    root = _repo_root()
    path = root / "policy" / "sites" / "sites_policy.v0.1.yaml"
    if not path.exists():
        pytest.skip("sites_policy.v0.1.yaml not found")
    policy = load_sites_policy(path)
    assert "sites" in policy
    assert "routes" in policy
    assert len(policy["sites"]) >= 2
    assert len(policy["routes"]) >= 1


def test_route_legality() -> None:
    """ACUTE->HUB allowed; HUB->ACUTE disabled => route_allowed false."""
    policy = {
        "site_graph": [
            {"from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "enabled": True},
            {"from_site": "SITE_HUB", "to_site": "SITE_ACUTE", "enabled": False},
        ],
        "routes": [
            {"route_id": "ACUTE_TO_HUB", "from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "transport_time_mean_s": 600},
        ],
    }
    assert _route_allowed(policy, "SITE_ACUTE", "SITE_HUB") is True
    assert _route_allowed(policy, "SITE_HUB", "SITE_ACUTE") is False
    assert _get_route(policy, "SITE_ACUTE", "SITE_HUB") is not None
    assert _get_route(policy, "SITE_HUB", "SITE_ACUTE") is None


def test_dispatch_forbidden_route() -> None:
    """DISPATCH to forbidden route => TRANSPORT_ROUTE_FORBIDDEN."""
    policy = {
        "site_graph": [{"from_site": "SITE_HUB", "to_site": "SITE_ACUTE", "enabled": False}],
        "routes": [],
    }
    store = TransportStore(policy=policy)
    cid, reason = store.dispatch(["S1"], "SITE_HUB", "SITE_ACUTE", 100, "A1")
    assert cid is None
    assert reason == TRANSPORT_ROUTE_FORBIDDEN


def test_dispatch_receive_determinism() -> None:
    """Same seed + dispatch + receive => same consignment_id and received_ts."""
    class SimpleRNG:
        def __init__(self, seed: int):
            self._v = seed
        def randint(self, a: int, b: int) -> int:
            self._v = (self._v * 31 + 17) % 1000
            return a + (self._v % max(1, b - a + 1))
    policy = {
        "site_graph": [{"from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "enabled": True}],
        "routes": [
            {"route_id": "A2H", "from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "transport_time_mean_s": 100, "transport_time_std_s": 0, "temp_drift_max_c": 1.0},
        ],
    }
    rng = SimpleRNG(42)
    store = TransportStore(policy=policy, rng=rng)
    cid1, _ = store.dispatch(["S1"], "SITE_ACUTE", "SITE_HUB", 0, "A1")
    assert cid1 is not None
    ok, _ = store.receive(cid1, 101, "A2")
    assert ok is True
    c = store.get_consignment(cid1)
    assert c is not None
    assert c["status"] == "arrived"
    assert c["received_ts"] == 101

    store2 = TransportStore(policy=policy, rng=SimpleRNG(42))
    cid2, _ = store2.dispatch(["S1"], "SITE_ACUTE", "SITE_HUB", 0, "A1")
    assert cid2 == cid1


def test_chain_of_custody_sign() -> None:
    """CHAIN_OF_CUSTODY_SIGN marks consignment signed; dispatch_has_receive_or_token true."""
    policy = {
        "site_graph": [{"from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "enabled": True}],
        "routes": [
            {"route_id": "A2H", "from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "transport_time_mean_s": 100, "transport_time_std_s": 0, "temp_drift_max_c": 2.0},
        ],
    }
    store = TransportStore(policy=policy)
    cid, _ = store.dispatch(["S1"], "SITE_ACUTE", "SITE_HUB", 0, "A1")
    assert cid is not None
    assert store.dispatch_has_receive_or_token(cid) is False
    ok, _ = store.chain_of_custody_sign(cid, "A_SUPERVISOR")
    assert ok is True
    assert store.dispatch_has_receive_or_token(cid) is True
    c = store.get_consignment(cid)
    assert c.get("chain_of_custody_signed") is True


def test_transport_tick_temp_excursion() -> None:
    """TRANSPORT_TICK can record temp excursion when drift exceeds bound (bounded model)."""
    class DriftRNG:
        def __init__(self):
            self._v = 0.99
        def random(self) -> float:
            self._v = (self._v + 0.1) % 1.0
            return self._v
    policy = {
        "site_graph": [{"from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "enabled": True}],
        "routes": [
            {"route_id": "A2H", "from_site": "SITE_ACUTE", "to_site": "SITE_HUB", "transport_time_mean_s": 100, "transport_time_std_s": 0, "temp_drift_max_c": 0.5},
        ],
    }
    rng = DriftRNG()
    store = TransportStore(policy=policy, rng=rng)
    cid, _ = store.dispatch(["S1"], "SITE_ACUTE", "SITE_HUB", 0, "A1")
    assert cid is not None
    excursions = store.tick(10)
    assert isinstance(excursions, list)
