# Partner calibration

Partner calibration provides **workload priors** for benchmark tasks: arrival patterns and STAT rate, fitted from aggregate operational data (no PII). When present, benchmarks use these priors to generate initial specimens and priorities.

## File and schema

- **File**: `policy/partners/<partner_id>/calibration.v0.1.yaml`
- **Schema**: `policy/schemas/calibration.v0.1.schema.json`

Calibration is optional. If the file is missing, tasks use built-in defaults.

## Structure

```yaml
version: "0.1"
description: "Optional description of calibration source."
workload_priors:
  arrival_mean_s: 50
  arrival_scale_s: 25
  arrival_max_s: 120
  stat_rate: 0.12
  n_specimens_min: 2
  n_specimens_max: 6
```

## How to fit each parameter from aggregate operational data

Use **aggregate** operational data only (counts, rates, percentiles). No specimen-level or patient-level data.

| Parameter | Unit | How to fit |
|-----------|------|------------|
| arrival_mean_s | seconds | Mean of (arrival_time − episode_start) over representative episodes. |
| arrival_scale_s | seconds | Half-width of arrival window or std of arrival offsets. E.g. (p75 − p25)/2. |
| arrival_max_s | seconds | Upper bound for arrival_ts_s (e.g. episode length or SLA). |
| stat_rate | 0–1 | Fraction of specimens that are STAT. count(STAT) / count(all) over a period. |
| n_specimens_min | count | Minimum specimens per episode (low-load or minimum batch). |
| n_specimens_max | count | Maximum specimens per episode (high-load or capacity). |

## Loader and fingerprint

- **load_effective_policy(root, partner_id)** loads calibration when present and merges it into **effective_policy["calibration"]**.
- **calibration_fingerprint** is the SHA-256 hash of the canonical JSON of the calibration dict. Returned as the 4th value from `load_effective_policy`.

## Benchmarks

When **calibration** is present in initial_state (e.g. from partner overlay), tasks use workload_priors for arrival sampling, stat_rate for specimen priority_class, and n_specimens_min/max for episode size. Missing calibration or missing fields fall back to task defaults.
