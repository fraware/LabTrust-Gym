# Partner pack v0.1 — hsl_like

HSL-like Blood Sciences example overlay. Researchers can run benchmarks with `--partner hsl_like` to use partner-specific policy without changing core code.

## Overridden files

| File | Overridden | Notes |
|------|------------|--------|
| **critical/critical_thresholds.v0.1.yaml** | Yes | Tighter K/Na thresholds (e.g. K 2.8–6.0, Na 125–155 mmol/L). |
| **stability/stability_policy.v0.1.yaml** | Yes | Scope and panel rules (e.g. BIOCHEM_PANEL_CORE 90 min collection-to-separation, breach handling). |
| **enforcement/enforcement_map.v0.1.yaml** | Yes | Partner-specific rules (e.g. ENF-CRIT-001 throttle on INV-CRIT-004). |
| **calibration.v0.1.yaml** | Yes | Optional calibration / site-specific tuning. |
| **equipment/equipment_registry.v0.1.yaml** | No | Base policy used; no partner equipment overlay in v0.1. |

Merge rules: critical by (analyte_code, units); stability by scope/panel_rules; enforcement by rule_id; equipment not merged (base only).

## Realistic vs placeholder

- **Realistic (illustrative):** Threshold ranges and stability windows are in a plausible HSL-like range; enforcement rule IDs and throttle durations are example values.
- **Placeholder:** Numeric values (e.g. 90 min, 45 s throttle) are not validated against a real site; equipment registry is base-only so service times and device counts are unchanged. Use for overlay behaviour and metric-shift sanity checks, not production tuning.

## Expected metric shifts with `--timing simulated`

- **device_utilization:** Present in simulated mode for both default and hsl_like; values may differ if equipment were overridden (in v0.1 equipment is not overridden, so utilization is from base equipment only).
- **Throughput / TAT:** Can differ due to stability windows (e.g. stricter pre-separation) and critical thresholds affecting release/override paths.
- **Violations / blocked counts:** May differ if enforcement rules or stability breach handling change which steps are BLOCKED.

Run one episode with default and one with `--partner hsl_like` (same task, seed, timing) and assert e.g. `policy_fingerprint` or metrics differ to confirm overlay effect.

## Usage

```bash
labtrust validate-policy --partner hsl_like
labtrust run-benchmark --task TaskA --partner hsl_like --episodes 2 --timing simulated
```

Environment: `LABTRUST_PARTNER=hsl_like`.
