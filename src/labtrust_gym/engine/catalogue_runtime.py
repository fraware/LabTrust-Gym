"""
Catalogue and stability policy for START_RUN gating.

- Panel lookup by panel_id (from catalogue or stability policy).
- Stability limits: pre_separation max (collection to separation), post_separation max
  (separation to run) per panel and temp band.
- Used by core_env START_RUN to gate on TIME_EXPIRED and TEMP_OUT_OF_BAND.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

TIME_EXPIRED = "TIME_EXPIRED"
TEMP_OUT_OF_BAND = "TEMP_OUT_OF_BAND"
INV_STAB_BIOCHEM_001 = "INV-STAB-BIOCHEM-001"
INV_STAB_BIOCHEM_002 = "INV-STAB-BIOCHEM-002"
INV_ZONE_006 = "INV-ZONE-006"


def load_stability_policy(path: str | Path) -> Dict[str, Any]:
    """Load stability_policy YAML. Returns dict with panel_rules."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    return data


def load_catalogue_seed(path: str | Path) -> Dict[str, Any]:
    """Load test_catalogue seed JSON. Returns dict with panels list."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    return data


def get_panel_from_catalogue(catalogue: Dict[str, Any], panel_id: str) -> Optional[Dict[str, Any]]:
    """Return panel dict by panel_id from catalogue.panels."""
    for panel in catalogue.get("panels") or []:
        if panel.get("panel_id") == panel_id:
            return panel
    return None


def get_stability_limits_for_panel(
    stability_policy: Dict[str, Any],
    panel_id: str,
) -> Dict[str, Any]:
    """
    Return stability limits for panel from stability_policy.panel_rules.
    Returns dict with: pre_separation_max_s, post_separation_ambient_max_s,
    post_separation_refrigerated_max_s, allowed_temp_bands.
    Uses default_stability_limits() when panel not in policy.
    """
    rules = (stability_policy.get("panel_rules") or {}).get(panel_id) or {}
    if not rules:
        return default_stability_limits()
    pre = rules.get("pre_separation_constraints") or {}
    post = rules.get("post_separation_storage_constraints") or {}
    pre_min = pre.get("max_time_collection_to_separation_minutes")
    pre_max_s = int(pre_min * 60) if pre_min is not None else 7200
    windows = post.get("stability_windows_minutes") or {}
    ambient_min = windows.get("AMBIENT_20_25") or windows.get("AMBIENT_15_25C")
    refrigerated_min = windows.get("REFRIGERATED_2_8")
    post_ambient_max_s = int(ambient_min * 60) if ambient_min is not None else 21600
    post_refrigerated_max_s = int(refrigerated_min * 60) if refrigerated_min is not None else 86400
    return {
        "pre_separation_max_s": pre_max_s,
        "post_separation_ambient_max_s": post_ambient_max_s,
        "post_separation_refrigerated_max_s": post_refrigerated_max_s,
        "allowed_temp_bands_pre": pre.get("allowed_temp_bands", ["AMBIENT_20_25"]),
    }


def check_stability(
    collection_ts_s: int,
    separated_ts_s: Optional[int],
    now_s: int,
    panel_id: str,
    stability_policy: Dict[str, Any],
    temp_band: str = "AMBIENT_20_25",
) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Check stability for START_RUN. Returns (ok, violation_id, reason_code, pass_invariant_id).
    - If pre_separation breached (collection to separation > max) => (False, INV-STAB-BIOCHEM-002, TIME_EXPIRED, None).
    - If post_separation breached (separation to now > max for temp band) => (False, INV-STAB-BIOCHEM-002, TIME_EXPIRED, None).
    - If ok => (True, None, None, INV-STAB-BIOCHEM-001) for biochem.
    """
    limits = get_stability_limits_for_panel(stability_policy, panel_id)
    pre_max_s = limits["pre_separation_max_s"]
    post_ambient = limits["post_separation_ambient_max_s"]
    post_refrig = limits["post_separation_refrigerated_max_s"]

    sep = separated_ts_s if separated_ts_s is not None else now_s
    if collection_ts_s is not None and sep is not None:
        collection_to_sep = sep - collection_ts_s
        if collection_to_sep > pre_max_s:
            return False, INV_STAB_BIOCHEM_002, TIME_EXPIRED, None
    if separated_ts_s is not None:
        sep_to_now = now_s - separated_ts_s
        if "REFRIGERATED" in temp_band or temp_band == "REFRIGERATED_2_8":
            max_post = post_refrig
        else:
            max_post = post_ambient
        if sep_to_now > max_post:
            return False, INV_STAB_BIOCHEM_002, TIME_EXPIRED, None
    return True, None, None, INV_STAB_BIOCHEM_001


def check_temp_out_of_band(
    storage_requirement: Optional[str],
    temp_exposure_log: Optional[List[Dict[str, Any]]],
) -> bool:
    """
    True if specimen has storage_requirement (e.g. REFRIGERATED_2_8) but temp_exposure_log
    contains out-of-band entries (e.g. AMBIENT when refrigerated required).
    """
    if not storage_requirement or not temp_exposure_log:
        return False
    req = (storage_requirement or "").upper()
    if "REFRIGERATED" in req or "2_8" in req:
        allowed = {"REFRIGERATED_2_8", "CHILLED_2_8C"}
        for entry in temp_exposure_log:
            band = (entry.get("temp_band") or "").upper().replace(" ", "_")
            if band and "AMBIENT" in band and band not in allowed:
                return True
    return False


def default_stability_limits() -> Dict[str, Any]:
    """Minimal limits when policy file missing (biochem 2h pre-spin, 6h post ambient)."""
    return {
        "pre_separation_max_s": 7200,
        "post_separation_ambient_max_s": 21600,
        "post_separation_refrigerated_max_s": 86400,
        "allowed_temp_bands_pre": ["AMBIENT_20_25"],
    }
