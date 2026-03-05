"""
Default zone and device IDs for the lab layout.

Single source of truth used by lab_design (export/viewer) and pz_parallel (env).
No optional dependencies so core export and tests can import without [env].
"""

from __future__ import annotations

# Aligned with engine default layout (zones._default_layout)
DEFAULT_ZONE_IDS: list[str] = [
    "Z_SRA_RECEPTION",
    "Z_ACCESSIONING",
    "Z_SORTING_LANES",
    "Z_PREANALYTICS",
    "Z_CENTRIFUGE_BAY",
    "Z_ALIQUOT_LABEL",
    "Z_ANALYZER_HALL_A",
    "Z_ANALYZER_HALL_B",
    "Z_QC_SUPERVISOR",
    "Z_RESTRICTED_BIOHAZARD",
]
DEFAULT_DEVICE_IDS: list[str] = [
    "DEV_CENTRIFUGE_BANK_01",
    "DEV_ALIQUOTER_01",
    "DEV_CHEM_A_01",
    "DEV_CHEM_B_01",
    "DEV_HAEM_01",
    "DEV_COAG_01",
]
