# Prime Intellect Inference benchmarking

LabTrust-Gym can call [Prime Intellect Inference](https://docs.primeintellect.ai/inference/overview) using backend id `prime_intellect_live`. The integration uses the OpenAI Python SDK pointed at `https://api.pinference.ai/api/v1` (see upstream chat completions documentation).

## Prerequisites

- Install optional dependencies: `pip install -e ".[llm_prime_intellect]"` (or `llm_openai`; same packages).
- API key with Inference permission: set `PRIME_INTELLECT_API_KEY` in `.env` (or `PRIME_API_KEY` as documented by Prime).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `PRIME_INTELLECT_API_KEY` | Bearer token for Prime Inference (preferred in this repo). |
| `PRIME_API_KEY` | Alternate name accepted by Prime docs and by credential resolution. |
| `LABTRUST_PRIME_INTELLECT_MODEL` | Default model id (e.g. `meta-llama/llama-3.1-70b-instruct`). |
| `LABTRUST_PRIME_INTELLECT_BASE_URL` | Override gateway URL (default `https://api.pinference.ai/api/v1`). |
| `LABTRUST_PRIME_TEAM_ID` | Sets `X-Prime-Team-ID` for team billing. |
| `LABTRUST_PRIME_INTELLECT_FALLBACK_MODEL` | Comma-separated fallback model ids (same idea as OpenAI fallback). |
| `LABTRUST_LLM_TIMEOUT_S`, `LABTRUST_LLM_RETRIES` | Shared with other live backends. |

## CLI smoke check

```bash
labtrust llm-healthcheck --backend prime_intellect_live --allow-network
```

## Single benchmark run

```bash
labtrust run-benchmark --task throughput_sla --episodes 1 --seed 42 --out runs/pi_smoke.json ^
  --pipeline-mode llm_live --allow-network --llm-backend prime_intellect_live ^
  --llm-model meta-llama/llama-3.1-70b-instruct
```

## Top-6 model sweep (hospital pipeline)

The file [scripts/hospital_lab_full_pipeline_config.yaml](scripts/hospital_lab_full_pipeline_config.yaml) lists `prime_intellect_benchmark_models` (six entries). To run that sweep:

```bash
python scripts/run_hospital_lab_full_pipeline.py --out runs/pi_top6 --allow-network ^
  --benchmark-models-from-config --no-smoke
```

Align `policy/llm/model_pricing.v0.1.yaml` rates for those model ids with your Prime billing dashboard so `estimated_cost_usd` in results metadata stays meaningful.

## Cross-provider pack

Include `prime_intellect_live` in `--providers` when calling `run-cross-provider-pack` (comma-separated list).

## Coordination security pack (`run_hospital_lab_full_pipeline.py`)

When you sweep models with `--models prime_intellect_live:<model_id>,...` and `--include-coordination-pack`, the coordination pack uses the **same** backend as your sweep. Every `--models` entry must use one backend (for example only `prime_intellect_live`); mixed backends are rejected with a clear error.

Requirements:

- Pass `--allow-network` (model sweeps already require it).
- The pack runs with `allow_network=True` and the resolved backend (for example `prime_intellect_live`), not the old `--providers`-only fallback.

### Verifying live Prime results

After a run, open a coordination cell `pack_results/<cell_id>/results.json` and confirm:

- `metadata.pipeline_mode` is `llm_live`.
- `metadata.llm_backend_id` is `prime_intellect_live`.

If you see `llm_offline` or `fixture` while you intended a live Prime run, the pack did not execute as live inference. A completed cell always has `results.json`; folders with only `episodes.jsonl` or traces and no `results.json` are incomplete (for example interrupted runs).
