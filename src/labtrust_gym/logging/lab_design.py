"""
Canonical hospital lab design: zones, devices, specimen statuses.

Single source of truth for the episode bundle builder and viewer.
Zone and device lists align with pz_parallel; specimen status order
matches the observation status_order used in _collect_observations.
"""

from __future__ import annotations

from typing import Any

# Import from env to keep a single source of truth; lab_design re-exports
# for bundle builder and viewer. If env is not installed, callers get
# ImportError when loading this module.
from labtrust_gym.envs.pz_parallel import DEFAULT_DEVICE_IDS, DEFAULT_ZONE_IDS

# Specimen status order used in observation specimen_status_counts (same as
# pz_parallel._collect_observations status_order). Not exported as a constant
# from pz_parallel, so defined here as the canonical list for export.
SPECIMEN_STATUS_ORDER: list[str] = [
    "arrived_at_reception",
    "accessioning",
    "accepted",
    "held",
    "rejected",
    "in_transit",
    "separated",
    "unknown",
]

# Short labels for UI (pipeline strip, zone-centric view). All zones present.
ZONE_LABELS: dict[str, str] = {
    "Z_SRA_RECEPTION": "Reception",
    "Z_ACCESSIONING": "Accessioning",
    "Z_SORTING_LANES": "Sorting",
    "Z_PREANALYTICS": "Preanalytics",
    "Z_CENTRIFUGE_BAY": "Centrifuge",
    "Z_ALIQUOT_LABEL": "Aliquot",
    "Z_ANALYZER_HALL_A": "Analyzer A",
    "Z_ANALYZER_HALL_B": "Analyzer B",
    "Z_QC_SUPERVISOR": "QC",
    "Z_RESTRICTED_BIOHAZARD": "Restricted",
}

# Device to zone for zone-centric view (engine convention: centrifuge/aliquot
# in their zones; analyzers in hall A/B).
DEVICE_ZONE: dict[str, str] = {
    "DEV_CENTRIFUGE_BANK_01": "Z_CENTRIFUGE_BAY",
    "DEV_ALIQUOTER_01": "Z_ALIQUOT_LABEL",
    "DEV_CHEM_A_01": "Z_ANALYZER_HALL_A",
    "DEV_CHEM_B_01": "Z_ANALYZER_HALL_B",
    "DEV_HAEM_01": "Z_ANALYZER_HALL_A",
    "DEV_COAG_01": "Z_ANALYZER_HALL_B",
}


def get_zone_ids() -> list[str]:
    """Return zone IDs in workflow order (10 zones)."""
    return list(DEFAULT_ZONE_IDS)


def get_zone_labels() -> dict[str, str]:
    """Return zone_id -> short label for UI. All 10 zones have a label."""
    return dict(ZONE_LABELS)


def get_device_ids() -> list[str]:
    """Return device IDs in stable order (6 devices)."""
    return list(DEFAULT_DEVICE_IDS)


def get_specimen_status_order() -> list[str]:
    """Return specimen status order (8 statuses) for lifecycle display."""
    return list(SPECIMEN_STATUS_ORDER)


def get_device_zone() -> dict[str, str]:
    """Return device_id -> zone_id for mapping QUEUE_RUN/START_RUN to zones."""
    return dict(DEVICE_ZONE)


def export_lab_design_json() -> dict[str, Any]:
    """
    Return a dict for JSON embedding in episode_bundle or lab_design.json.

    Keys: zones, zone_labels, devices, specimen_status_order, device_zone.
    """
    return {
        "zones": get_zone_ids(),
        "zone_labels": get_zone_labels(),
        "devices": get_device_ids(),
        "specimen_status_order": get_specimen_status_order(),
        "device_zone": get_device_zone(),
    }
