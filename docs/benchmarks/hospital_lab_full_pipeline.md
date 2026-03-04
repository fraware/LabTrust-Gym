# Hospital lab full pipeline – result collection

This document describes how to collect end-to-end pipeline results for the **pathology lab (blood sciences)** design: baselines, all coordination methods (or a chosen matrix preset), security suite (smoke and/or full), safety case, and optional method sweep or per-model comparison. The script and preset names use "hospital lab" (broad category); the modeled workflow is a blood sciences lane. See [Glossary – Lab terminology](../reference/glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab). A single orchestrator script runs the existing pack, coordination security pack, and security/safety components and writes a summary manifest.

## Purpose

- **Single run**: Produce one output tree with baselines, coordination pack (method x scale x injection), security attack results, safety case, and transparency log.
- **Scope options**: Choose matrix preset (hospital_lab for fast regression, hospital_lab_full for all methods), security mode (smoke, full, or both), and optional cross-provider or per-model sweep.
- **Summary manifest**: `summary/full_pipeline_manifest.json` and `full_pipeline_manifest.md` list artifacts and parameters for quick comparison.

See [Official benchmark pack](official_benchmark_pack.md), [Security attack suite](../risk-and-security/security_attack_suite.md), [Lab coordination report](../coordination/lab_coordination_report.md), and [Trust verification](../risk-and-security/trust_verification.md) for details on each component.

## Scope options

| Dimension | Options | Default |
|-----------|---------|---------|
| **Matrix preset** | `hospital_lab`, `hospital_lab_full`, `full_matrix` | `hospital_lab` |
| **Security** | `smoke`, `full`, `both` | `smoke` |
| **Coordination pack** | Enabled with `--include-coordination-pack` | Off |
| **Providers** | Comma-separated (e.g. `openai_live,anthropic_live`) for cross-provider | Single deterministic pack |
| **Models** | Comma-separated `backend:model_id` for per-model sweep | Single run |
| **Method sweep** | `--method-sweep` runs all coordination methods into `method_sweep/` | Off |

- **hospital_lab**: 4 methods, 2 scales, critical injections (fast regression).
- **hospital_lab_full**: All coordination methods from the pack policy, same scales and injections.
- **full_matrix**: All scales, all methods, all injections (large run).
- **Security both**: Pack runs with smoke; a separate `security_full/` run executes the full attack suite.

Config file (optional): `scripts/hospital_lab_full_pipeline_config.yaml` defines allowed matrix presets, security modes, and default providers. The script can load it automatically or via `--config`.

**Environment:** The script loads `.env` from the repo root at startup (when present), so coordination pack and child runs see `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` without sourcing them in the shell.

## How to run

From the repo root:

```bash
# Minimal: deterministic pack only
python scripts/run_hospital_lab_full_pipeline.py --out runs/hospital_lab_full

# With coordination pack (hospital_lab matrix) and security full in a separate dir
python scripts/run_hospital_lab_full_pipeline.py --out runs/full \
  --matrix-preset hospital_lab --security both --include-coordination-pack

# Full benchmark: hospital_lab_full matrix, security both, coordination pack
python scripts/run_hospital_lab_full_pipeline.py --out runs/full_bench \
  --matrix-preset hospital_lab_full --security both --include-coordination-pack --seed-base 42

# OpenAI-only: single provider, coordination pack uses that backend
python scripts/run_hospital_lab_full_pipeline.py --out runs/openai_only \
  --providers openai_live --include-coordination-pack --allow-network

# Cross-provider: one pack per provider, then one coordination pack
python scripts/run_hospital_lab_full_pipeline.py --out runs/cross \
  --providers openai_live,anthropic_live --include-coordination-pack --allow-network

# Per-model sweep (requires --allow-network and API keys)
python scripts/run_hospital_lab_full_pipeline.py --out runs/models \
  --models "openai_live:gpt-4o-mini,openai_live:gpt-4o" --include-coordination-pack --allow-network

# Optional: add method sweep (all coordination methods) and LLM attacker security run
python scripts/run_hospital_lab_full_pipeline.py --out runs/complete \
  --matrix-preset hospital_lab_full --security both --include-coordination-pack \
  --method-sweep --llm-attacker --allow-network --llm-backend openai_live
```

Required when using live backends or LLM attacker: `--allow-network`; set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (and install `.[llm_openai]` / `.[llm_anthropic]` as needed).

## Output layout

Under the given `--out` directory:

| Path | Description |
|------|-------------|
| `baselines/` | Official pack baseline results (when not using providers or models sweep). |
| `SECURITY/` | Security attack results and securitization packet from the pack run. |
| `SAFETY_CASE/` | Safety case (claim to control, test, artifact). |
| `TRANSPARENCY_LOG/` | Transparency log; for live runs, includes `llm_live.json` and `live_evaluation_metadata.json`. |
| `coordination_pack/` | Present when `--include-coordination-pack`: pack_summary.csv, pack_gate.md, SECURITY/coordination_risk_matrix.*, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.*. |
| `security_full/` | Present when `--security full` or `--security both`: full security suite run. |
| `security_llm_attacker/` | Present when `--llm-attacker`: security suite with live LLM-generated payloads. |
| `method_sweep/` | Present when `--method-sweep`: output of run_all_coordination_methods_smoke (preset full). |
| `models/<backend>/<model_id>/` | Present when `--models` is used: one official pack output per (backend, model). |
| `<provider>/` | Present when `--providers` is used: one official pack output per provider (e.g. `openai_live/`, `anthropic_live/`). |
| `summary/full_pipeline_manifest.json` | Machine-readable manifest (timestamp, seed_base, matrix_preset, security_mode, artifacts list). |
| `summary/full_pipeline_manifest.md` | Human-readable summary and artifact table. |

## Partial runs and disk space

The coordination pack and other heavy steps (security full, method sweep) write large episode logs. If the run hits "No space left on device" (or any other failure), the script:

- Catches the failure per step: coordination pack, security full, LLM attacker, and method sweep each run in a try/except. A failed step is recorded in the manifest with an `error` field and the pipeline continues.
- On any uncaught exception (e.g. during the initial pack), writes a **partial summary manifest** with `pipeline_error`, `partial: true`, and the `artifacts` list for whatever completed (e.g. cross-provider `openai_lab/`, `anthropic_live/`).

To avoid running out of space: use `--out` on a drive with enough free space; or run with a smaller matrix first (e.g. `--matrix-preset hospital_lab`) or without `--include-coordination-pack` for a lighter run.

## Interpreting results

- **Pack gate**: In `coordination_pack/pack_gate.md`, each cell shows PASS / FAIL / not_supported; the coordination security pack gate policy defines thresholds.
- **Security**: `SECURITY/attack_results.json` and `security_full/SECURITY/attack_results.json` (if run) list per-attack outcome (passed, blocked, detected). See [Security attack suite](../risk-and-security/security_attack_suite.md).
- **Safety case**: `SAFETY_CASE/safety_case.json` and `safety_case.md` trace claims to controls and evidence. See [Trust verification](../risk-and-security/trust_verification.md).
- **Cross-provider / per-model**: Compare `summary_cross_provider.json` (when using `--providers`) or the per-model subdirs under `models/` for latency and cost (e.g. `live_evaluation_metadata.json`, `TRANSPARENCY_LOG/llm_live.json`).

## Related commands

- `labtrust run-official-pack --out <dir> [--include-coordination-pack]`: Single official pack run (no orchestrator).
- `labtrust run-cross-provider-pack --out <dir> --providers ...`: Cross-provider only (no coordination pack override or security_full).
- `labtrust run-coordination-security-pack --out <dir> --matrix-preset hospital_lab [--scale-ids small_smoke] [--workers 4] [--llm-backend openai_live]`: Coordination pack only. Use `--scale-ids small_smoke` and `--workers N` for faster or smaller runs; `--llm-backend` requires `--allow-network` and API keys.
- `labtrust run-security-suite --out <dir> [--full]`: Security suite only.
- `python scripts/run_all_coordination_methods_smoke.py --preset full --out <dir>`: Method sweep only.

The full pipeline script composes these into one run and writes the summary manifest.
