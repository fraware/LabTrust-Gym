# HSL-like partner overlay

Minimal example overlay for a partner profile similar to HSL (Blood Sciences). Overrides only specific policy subtrees; base policy remains the default for anything not overridden.

## Overridden files

- **critical/critical_thresholds.v0.1.yaml** — Tighter K/Na thresholds for this partner.
- **stability/stability_policy.v0.1.yaml** — Scope and panel rule overrides (e.g. biochem pre-separation window).
- **enforcement/enforcement_map.v0.1.yaml** — Partner-specific enforcement rules (add/override by rule_id).

## Merge rules

- **Critical thresholds**: Overlay entries replace base entries by (analyte_code, units); may add new analytes. Base keys retained where not overridden.
- **Stability**: Overlay replaces top-level keys (scope, panel_rules) or panel_rules by panel_id; required keys preserved.
- **Enforcement**: Overlay rules replace base rules by rule_id; may add rules. Core severities must remain covered.

## Usage

```bash
labtrust validate-policy --partner hsl_like
labtrust run-benchmark --task TaskA --partner hsl_like --episodes 2
```

Environment: `LABTRUST_PARTNER=hsl_like`.
