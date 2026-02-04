"""
Deterministic partition of zones into regions (site, floor, or zone cluster).
Used by hierarchical coordination to reduce global coupling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DEFAULT_NUM_REGIONS = 3


def partition_zones_into_regions(
    zone_ids: List[str],
    policy: Optional[Dict[str, Any]] = None,
    scale_config: Optional[Dict[str, Any]] = None,
    num_regions: Optional[int] = None,
    rng: Optional[Any] = None,
) -> Dict[str, str]:
    """
    Map each zone_id to a region_id deterministically.
    Region IDs are R_0, R_1, ... R_{num_regions-1}.
    Uses zone order (sorted) and num_regions so same inputs => same partition.
    Optional: policy zone_layout.zones[].region_id or site_id overrides.
    """
    if not zone_ids:
        return {}
    ordered = sorted(zone_ids)
    n = num_regions
    if n is None and scale_config:
        n = int(scale_config.get("num_sites", 0)) or int(
            scale_config.get("num_regions", 0)
        )
    if n is None or n < 1:
        n = DEFAULT_NUM_REGIONS
    n = max(1, min(n, len(ordered)))
    out: Dict[str, str] = {}
    layout = (policy or {}).get("zone_layout") or {}
    zones_list = layout.get("zones") or []
    zone_to_meta: Dict[str, Dict[str, Any]] = {}
    for z in zones_list:
        if isinstance(z, dict) and z.get("zone_id"):
            zone_to_meta[z["zone_id"]] = z
    for i, zid in enumerate(ordered):
        meta = zone_to_meta.get(zid) or {}
        region_id = meta.get("region_id") or meta.get("site_id")
        if region_id is not None:
            out[zid] = str(region_id)
        else:
            out[zid] = f"R_{i % n}"
    return out


def zone_to_region_map(
    zone_ids: List[str],
    policy: Optional[Dict[str, Any]] = None,
    scale_config: Optional[Dict[str, Any]] = None,
    num_regions: Optional[int] = None,
) -> Dict[str, str]:
    """
    Convenience: same as partition_zones_into_regions without rng (fully deterministic from data).
    """
    return partition_zones_into_regions(
        zone_ids, policy=policy, scale_config=scale_config, num_regions=num_regions
    )
