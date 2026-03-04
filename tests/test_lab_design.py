"""
Lab design: single source of truth for zones, devices, specimen statuses.

Asserts alignment with env constants (pz_parallel) when pettingzoo available.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pettingzoo")

from labtrust_gym.envs.pz_parallel import DEFAULT_DEVICE_IDS, DEFAULT_ZONE_IDS  # noqa: E402
from labtrust_gym.logging.lab_design import (  # noqa: E402
    SPECIMEN_STATUS_ORDER,
    export_lab_design_json,
    get_device_ids,
    get_device_zone,
    get_specimen_status_order,
    get_zone_ids,
    get_zone_labels,
)


def test_get_zone_ids_matches_env() -> None:
    """get_zone_ids() returns same list as DEFAULT_ZONE_IDS (10 zones)."""
    assert get_zone_ids() == list(DEFAULT_ZONE_IDS)
    assert len(get_zone_ids()) == 10


def test_get_device_ids_matches_env() -> None:
    """get_device_ids() returns same list as DEFAULT_DEVICE_IDS (6 devices)."""
    assert get_device_ids() == list(DEFAULT_DEVICE_IDS)
    assert len(get_device_ids()) == 6


def test_get_zone_labels_has_all_zones() -> None:
    """Every zone from get_zone_ids() has a short label."""
    zone_ids = get_zone_ids()
    labels = get_zone_labels()
    for z in zone_ids:
        assert z in labels, f"Missing label for {z}"
    assert len(labels) == 10


def test_get_specimen_status_order_length() -> None:
    """Specimen status order has 8 statuses."""
    order = get_specimen_status_order()
    assert order == SPECIMEN_STATUS_ORDER
    assert len(order) == 8


def test_export_lab_design_json_has_all_keys() -> None:
    """export_lab_design_json has zones, zone_labels, devices, statuses, device_zone."""
    out = export_lab_design_json()
    assert "zones" in out
    assert "zone_labels" in out
    assert "devices" in out
    assert "specimen_status_order" in out
    assert "device_zone" in out
    assert len(out["zones"]) == 10
    assert len(out["devices"]) == 6
    assert len(out["specimen_status_order"]) == 8


def test_get_device_zone_maps_all_devices() -> None:
    """Every device has a zone in device_zone."""
    devices = get_device_ids()
    device_zone = get_device_zone()
    for d in devices:
        assert d in device_zone, f"Missing device_zone for {d}"
