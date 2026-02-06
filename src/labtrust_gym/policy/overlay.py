"""
Partner overlay merge: base + overlay -> effective policy.

One merge function per policy type. Rules:
- Maps (reason_codes, emits): overlay may add; may not delete base entries.
- Thresholds/stability/equipment: overlay may replace by key; required keys kept.
- Enforcement map: overlay may add/override rules by rule_id; core severities remain covered.
"""

from __future__ import annotations

from typing import Any


def merge_critical_thresholds(
    base: list[dict[str, Any]],
    overlay: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge critical threshold lists. Overlay may replace entries by (analyte_code, units);
    may add new entries. Base entries not overridden are kept.
    """

    def key_fn(e: dict[str, Any]) -> tuple[str, str]:
        return (str(e.get("analyte_code", "")), str(e.get("units", "")))

    by_key: dict[tuple[str, str], dict[str, Any]] = {key_fn(e): e for e in base}
    for e in overlay:
        by_key[key_fn(e)] = e
    base_keys = {key_fn(e) for e in base}
    result: list[dict[str, Any]] = [by_key[key_fn(e)] for e in base]
    for e in overlay:
        k = key_fn(e)
        if k not in base_keys:
            result.append(by_key[k])
    return result


def merge_stability_policy(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge stability policy. Overlay replaces top-level keys; panel_rules merged by panel_id
    (overlay panel replaces base for same panel_id). Base required structure preserved.
    """
    result = dict(base)
    for key, val in overlay.items():
        if key == "panel_rules" and isinstance(val, dict) and isinstance(result.get("panel_rules"), dict):
            merged_panels = dict(result["panel_rules"])
            for panel_id, panel_rules in val.items():
                merged_panels[panel_id] = panel_rules
            result["panel_rules"] = merged_panels
        else:
            result[key] = val
    return result


def merge_enforcement_map(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge enforcement map. Overlay rules replace base rules by rule_id; may add rules.
    Base version/enforcement_map_id overridden by overlay if present.
    """
    base_rules: list[dict[str, Any]] = list(base.get("rules") or [])
    overlay_rules: list[dict[str, Any]] = list(overlay.get("rules") or [])
    by_rule_id: dict[str, dict[str, Any]] = {r.get("rule_id", f"_i{i}"): r for i, r in enumerate(base_rules)}
    for r in overlay_rules:
        rid = r.get("rule_id", "")
        if rid:
            by_rule_id[rid] = r
    merged_rules = list(by_rule_id.values())
    return {
        "version": overlay.get("version", base.get("version", "0.1")),
        "enforcement_map_id": overlay.get("enforcement_map_id", base.get("enforcement_map_id", "")),
        "rules": merged_rules,
    }


def merge_escalation_ladder(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge escalation ladder. Overlay replaces base (full replace: version, minimum_record_fields, tiers).
    Required keys kept; overlay tiers replace base tiers when present.
    """
    if not overlay or not overlay.get("tiers"):
        return base
    return {
        "version": overlay.get("version", base.get("version", "0.2")),
        "minimum_record_fields": overlay.get("minimum_record_fields") or base.get("minimum_record_fields") or [],
        "tiers": overlay.get("tiers", base.get("tiers", [])),
    }


def merge_equipment_registry(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge equipment registry. Overlay may replace device_types by key, device_instances by key.
    Required keys (version, units, scope, global_scheduling, device_types, device_instances) kept.
    """
    result = dict(base)
    if "device_types" in overlay and isinstance(overlay["device_types"], dict):
        dt = dict(result.get("device_types") or {})
        for k, v in overlay["device_types"].items():
            dt[k] = v
        result["device_types"] = dt
    if "device_instances" in overlay and isinstance(overlay["device_instances"], list):
        base_inst = {inst.get("device_id"): inst for inst in (result.get("device_instances") or [])}
        for inst in overlay["device_instances"]:
            did = inst.get("device_id")
            if did:
                base_inst[did] = inst
        result["device_instances"] = list(base_inst.values())
    for key in ("version", "units", "scope", "global_scheduling"):
        if key in overlay:
            result[key] = overlay[key]
    return result


def merge_emits_vocab_add_only(
    base_emit_set: set[str],
    overlay_emit_list: list[str],
) -> set[str]:
    """
    Emits: overlay may add only; may not delete base. Returns union of base and overlay emits.
    """
    out = set(base_emit_set)
    for e in overlay_emit_list or []:
        out.add(str(e).strip())
    return out


def merge_reason_codes_add_only(
    base_codes: list[dict[str, Any]],
    overlay_codes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Reason codes: overlay may add only; may not delete base. Returns base + new overlay codes
    (by code string; overlay entry with same code as base is ignored to avoid deletion).
    """
    base_code_names = {c.get("code") for c in (base_codes or []) if c.get("code")}
    result = list(base_codes or [])
    for c in overlay_codes or []:
        if c.get("code") and c["code"] not in base_code_names:
            result.append(c)
            base_code_names.add(c["code"])
    return result
