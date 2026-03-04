"""
FHIR terminology validation: check coded elements in a Bundle against value sets.

Used by validate-fhir CLI. Not part of the minimal benchmark contract.
"""

from __future__ import annotations

from typing import Any


def _collect_codings(resource: dict[str, Any], path_prefix: str) -> list[tuple[str, str, str]]:
    """Collect (path, system, code) from a FHIR resource. path_prefix e.g. 'Observation'."""
    out: list[tuple[str, str, str]] = []
    if not isinstance(resource, dict):
        return out
    # Observation.code, DiagnosticReport.code
    for key in ("code",):
        code_obj = resource.get(key)
        if isinstance(code_obj, dict) and "coding" in code_obj:
            for c in code_obj.get("coding") or []:
                if isinstance(c, dict):
                    system = c.get("system") or ""
                    code = c.get("code")
                    if code is not None:
                        out.append((f"{path_prefix}.{key}", system, str(code)))
    # Observation.interpretation (array of CodeableConcept)
    interp = resource.get("interpretation")
    if isinstance(interp, list):
        for i, item in enumerate(interp):
            if isinstance(item, dict) and "coding" in item:
                for c in item.get("coding") or []:
                    if isinstance(c, dict):
                        system = c.get("system") or ""
                        code = c.get("code")
                        if code is not None:
                            out.append((f"{path_prefix}.interpretation[{i}]", system, str(code)))
    return out


def validate_bundle_against_value_sets(
    bundle: dict[str, Any],
    value_sets: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """
    Validate every coded element in Bundle.entry[].resource against value_sets.

    value_sets: map of system URI -> list of allowed code strings.
    Returns list of violations: [{ "resourceType", "id", "path", "system", "code", "value_set" }].
    """
    violations: list[dict[str, Any]] = []
    if bundle.get("resourceType") != "Bundle":
        return violations
    entries = bundle.get("entry") or []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue
        rt = resource.get("resourceType")
        rid = resource.get("id", "")
        if rt in ("Observation", "DiagnosticReport"):
            path_prefix = rt
            for path, system, code in _collect_codings(resource, path_prefix):
                allowed = value_sets.get(system)
                if allowed is None:
                    continue  # no value set for this system: skip (don't fail)
                if code not in allowed:
                    violations.append(
                        {
                            "resourceType": rt,
                            "id": rid,
                            "path": path,
                            "system": system,
                            "code": code,
                            "value_set": system,
                        }
                    )
    return violations
