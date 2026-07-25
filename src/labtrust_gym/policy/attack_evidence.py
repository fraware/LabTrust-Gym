"""
Attack-suite evidence contract resolution (LTG-PR5 / LTG-06).

Suite YAML may declare suite-level evidence_contract_defaults and named
evidence_contract_templates. Each attack may set evidence_contract_ref and/or a
partial evidence_contract overlay. Resolution merges defaults -> template ->
overlay into a full evidence_contract before JSON Schema validation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Canonical keys for the per-attack evidence contract (must match schema).
EVIDENCE_CONTRACT_KEYS: tuple[str, ...] = (
    "threat_model",
    "attacker_capability",
    "success_condition",
    "budget",
    "baseline",
    "optimized_attack",
    "expected_detection_point",
    "residual_risk",
    "reproducible_fixture",
)

_BUDGET_KEYS = frozenset({"mode", "max_rounds", "requires_live_llm", "notes"})


def _merge_budget(base: Any, overlay: Any) -> Any:
    """Merge budget objects (overlay wins); non-dicts replace."""
    if not isinstance(overlay, dict):
        return deepcopy(overlay) if overlay is not None else deepcopy(base)
    if not isinstance(base, dict):
        return deepcopy(overlay)
    out = deepcopy(base)
    out.update(overlay)
    return out


def merge_evidence_contract(
    defaults: dict[str, Any] | None,
    template: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Merge evidence contract layers: defaults -> template -> overlay.
    budget is deep-merged when both sides are objects.
    """
    out: dict[str, Any] = {}
    for layer in (defaults, template, overlay):
        if not layer:
            continue
        for key, value in layer.items():
            if key not in EVIDENCE_CONTRACT_KEYS:
                continue
            if key == "budget":
                out[key] = _merge_budget(out.get(key), value)
            else:
                out[key] = deepcopy(value)
    return out


def resolve_suite_evidence_contracts(suite: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of suite where every attack has a fully merged evidence_contract
    and evidence_contract_ref is removed (resolved). Does not mutate the input.
    """
    if not isinstance(suite, dict):
        return suite
    out = deepcopy(suite)
    defaults = out.get("evidence_contract_defaults")
    if not isinstance(defaults, dict):
        defaults = {}
    templates = out.get("evidence_contract_templates")
    if not isinstance(templates, dict):
        templates = {}

    attacks_in = out.get("attacks")
    if not isinstance(attacks_in, list):
        return out

    resolved_attacks: list[dict[str, Any]] = []
    for attack in attacks_in:
        if not isinstance(attack, dict):
            resolved_attacks.append(attack)
            continue
        a = dict(attack)
        ref = a.pop("evidence_contract_ref", None)
        overlay = a.get("evidence_contract")
        if overlay is not None and not isinstance(overlay, dict):
            overlay = {}
        template: dict[str, Any] | None = None
        if ref is not None:
            tpl = templates.get(str(ref))
            if isinstance(tpl, dict):
                template = tpl
            else:
                # Leave missing ref as empty template; validator will fail required fields
                # and/or validate_security_attack_evidence_contracts will report unknown ref.
                template = None
        merged = merge_evidence_contract(
            defaults if defaults else None,
            template,
            overlay if isinstance(overlay, dict) else None,
        )
        a["evidence_contract"] = merged
        # Keep ref for debugging/audit when present originally
        if ref is not None:
            a["evidence_contract_ref"] = str(ref)
        resolved_attacks.append(a)

    out["attacks"] = resolved_attacks
    return out


def validate_resolved_evidence_contracts(suite: dict[str, Any], path_label: str = "") -> list[str]:
    """
    Structural checks beyond JSON Schema: unknown template refs, smoke/CI offline rule.
    Returns list of error messages (empty if ok).
    """
    errors: list[str] = []
    prefix = f"{path_label}: " if path_label else ""
    templates = suite.get("evidence_contract_templates") or {}
    if not isinstance(templates, dict):
        templates = {}

    for i, attack in enumerate(suite.get("attacks") or []):
        if not isinstance(attack, dict):
            continue
        aid = attack.get("attack_id") or f"attacks[{i}]"
        ref = attack.get("evidence_contract_ref")
        if ref is not None and str(ref) not in templates:
            errors.append(
                f"{prefix}attack {aid!r}: evidence_contract_ref {ref!r} not in evidence_contract_templates"
            )
        contract = attack.get("evidence_contract")
        if not isinstance(contract, dict):
            errors.append(f"{prefix}attack {aid!r}: missing evidence_contract after resolution")
            continue
        for key in EVIDENCE_CONTRACT_KEYS:
            if key not in contract or contract[key] in (None, ""):
                errors.append(f"{prefix}attack {aid!r}: evidence_contract missing required field {key!r}")
        budget = contract.get("budget")
        if isinstance(budget, dict):
            unknown = set(budget.keys()) - _BUDGET_KEYS
            if unknown:
                errors.append(
                    f"{prefix}attack {aid!r}: evidence_contract.budget has unknown keys {sorted(unknown)}"
                )
            requires_live = bool(budget.get("requires_live_llm"))
            mode = budget.get("mode")
            if attack.get("smoke") and requires_live:
                errors.append(
                    f"{prefix}attack {aid!r}: smoke=true attacks must have "
                    f"evidence_contract.budget.requires_live_llm=false (CI stays offline)"
                )
            if attack.get("smoke") and mode == "live_llm_opt_in":
                errors.append(
                    f"{prefix}attack {aid!r}: smoke=true attacks must not use budget.mode=live_llm_opt_in"
                )
            if attack.get("llm_attacker") and not requires_live:
                errors.append(
                    f"{prefix}attack {aid!r}: llm_attacker=true requires "
                    f"evidence_contract.budget.requires_live_llm=true"
                )
            if requires_live and attack.get("smoke"):
                # already covered above; keep for clarity
                pass
        # Smoke must not depend on live LLM attacker flag
        if attack.get("smoke") and attack.get("llm_attacker"):
            errors.append(
                f"{prefix}attack {aid!r}: smoke=true must not set llm_attacker "
                f"(live proprietary model is opt-in only)"
            )
    return errors
