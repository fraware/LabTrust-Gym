"""
Test catalogue and stability policy used to gate START_RUN.

Looks up panels by panel_id from the catalogue or stability policy. Stability
limits define maximum times: from collection to separation (pre_separation),
and from separation to run (post_separation) per panel and temperature band.
Reagent policy defines per-panel reagent needs; if stock is out, START_RUN
is blocked with reason code RC_REAGENT_STOCKOUT. The core engine uses this
module to gate START_RUN on time-expired, temperature out of band, and reagent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

TIME_EXPIRED = "TIME_EXPIRED"
TEMP_OUT_OF_BAND = "TEMP_OUT_OF_BAND"
RC_REAGENT_STOCKOUT = "RC_REAGENT_STOCKOUT"
INV_STAB_BIOCHEM_001 = "INV-STAB-BIOCHEM-001"
INV_STAB_BIOCHEM_002 = "INV-STAB-BIOCHEM-002"
INV_ZONE_006 = "INV-ZONE-006"


def load_stability_policy(path: str | Path) -> dict[str, Any]:
    """Load stability_policy YAML. Returns dict with panel_rules."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    return data


def load_catalogue_seed(path: str | Path) -> dict[str, Any]:
    """Load test_catalogue seed JSON. Returns dict with panels list."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    return cast(dict[str, Any], data)


def get_panel_from_catalogue(catalogue: dict[str, Any], panel_id: str) -> dict[str, Any] | None:
    """Return panel dict by panel_id from catalogue.panels."""
    for panel in catalogue.get("panels") or []:
        if panel.get("panel_id") == panel_id:
            return cast(dict[str, Any] | None, panel)
    return None


def get_stability_limits_for_panel(
    stability_policy: dict[str, Any],
    panel_id: str,
) -> dict[str, Any]:
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
    separated_ts_s: int | None,
    now_s: int,
    panel_id: str,
    stability_policy: dict[str, Any],
    temp_band: str = "AMBIENT_20_25",
) -> tuple[bool, str | None, str | None, str | None]:
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
    storage_requirement: str | None,
    temp_exposure_log: list[dict[str, Any]] | None,
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


def default_stability_limits() -> dict[str, Any]:
    """Minimal limits when policy file missing (biochem 2h pre-spin, 6h post ambient)."""
    return {
        "pre_separation_max_s": 7200,
        "post_separation_ambient_max_s": 21600,
        "post_separation_refrigerated_max_s": 86400,
        "allowed_temp_bands_pre": ["AMBIENT_20_25"],
    }


def load_reagent_policy(path: Path | None = None) -> dict[str, Any]:
    """Load reagent_policy YAML; return reagent_policy dict or empty."""
    path = path or Path("policy/reagents/reagent_policy.v0.1.yaml")
    if not path.exists():
        return {}
    try:
        data = load_yaml(path)
    except PolicyLoadError:
        return {}
    return cast(dict[str, Any], data.get("reagent_policy", data) if isinstance(data, dict) else {})


def get_panel_reagent_requirement(
    reagent_policy: dict[str, Any],
    panel_id: str,
) -> tuple[str, float, str] | None:
    """
    Return (reagent_id, quantity_per_run, stockout_action) for panel_id, or None.
    stockout_action is HOLD or REROUTE per policy.
    """
    reqs = reagent_policy.get("panel_requirements") or {}
    panel_req = reqs.get(panel_id) if isinstance(reqs, dict) else None
    if not isinstance(panel_req, dict):
        return None
    rid = panel_req.get("reagent_id")
    qty = panel_req.get("quantity_per_run")
    action = panel_req.get("stockout_action") or "HOLD"
    if rid is not None and qty is not None:
        return (str(rid), float(qty), str(action))
    return None


def build_initial_reagent_stock(reagent_policy: dict[str, Any]) -> dict[str, float]:
    """Build initial stock dict from reagent_policy.reagents (reagent_id -> initial_stock)."""
    stock: dict[str, float] = {}
    for r in reagent_policy.get("reagents") or []:
        if isinstance(r, dict) and r.get("reagent_id") is not None:
            stock[str(r["reagent_id"])] = float(r.get("initial_stock", 0))
    return stock
