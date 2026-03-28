# OpenHands SWE-bench with Prime runbook

Minimal runbook to execute OpenHands SWE-bench on Prime Intellect with a preflight guard that validates model availability first.

## Scope

This runbook is tailored to the Prime list in `scripts/hospital_lab_full_pipeline_config.yaml`:

- `meta-llama/llama-3.1-70b-instruct`
- `anthropic/claude-3-5-sonnet-20241022`
- `meta-llama/llama-3.1-8b-instruct`
- `mistralai/mistral-small-latest`
- `deepseek/deepseek-chat`
- `Qwen/Qwen2.5-72B-Instruct`

Only models that are currently available in Prime `/models` should be used for benchmark runs.

## 1) Preflight availability (required)

From this repository root:

```bash
python scripts/preflight_prime_for_openhands_swebench.py --strict \
  --write-config-dir ".llm_config/prime" \
  --json-report "runs/prime_openhands_preflight.json"

# Optional: also write canonical config for immediate swebench-infer usage
python scripts/preflight_prime_for_openhands_swebench.py --strict \
  --auto-canonical-config \
  --json-report "runs/prime_openhands_preflight.json"
```

What this does:

- Loads `PRIME_INTELLECT_API_KEY` / `PRIME_API_KEY` from `.env` (if present).
- Queries Prime model catalog at `https://api.pinference.ai/api/v1/models` (or `LABTRUST_PRIME_INTELLECT_BASE_URL`).
- Verifies the configured Prime model list.
- Writes OpenHands-ready LLM config files for available models to `.llm_config/prime`.
- With `--auto-canonical-config`, writes `.llm_config/prime.json` using the
  first available requested model.

If preflight reports missing models, do not start SWE-bench with those IDs.

## 2) OpenHands benchmarks setup

In a separate working directory:

```bash
git clone https://github.com/OpenHands/benchmarks.git
cd benchmarks
make build
```

## 3) Copy one validated model config

Pick one generated config from this repository, for example:

- `LabTrust-Gym/.llm_config/prime/prime-anthropic-claude-3.5-haiku.json` (if generated)
- or any other generated `prime-*.json` that preflight marked available.

Copy it into OpenHands benchmarks as `.llm_config/prime.json` and set the API key value to a real secret if needed by your local workflow.

Expected config shape:

```json
{
  "model": "openai/<prime-model-id>",
  "base_url": "https://api.pinference.ai/api/v1",
  "api_key": "${PRIME_INTELLECT_API_KEY}"
}
```

## 4) Build SWE-bench images (small first)

```bash
uv run python -m benchmarks.swebench.build_images \
  --dataset princeton-nlp/SWE-bench_Verified \
  --split test \
  --image ghcr.io/openhands/eval-agent-server \
  --target source-minimal
```

## 5) Run a minimal SWE-bench inference smoke

Start with one instance:

```bash
uv run swebench-infer .llm_config/prime.json \
  --dataset princeton-nlp/SWE-bench_Verified \
  --split test \
  --workspace docker \
  --n-limit 1 \
  --max-iterations 80
```

Then scale up only after this succeeds.

## 6) Evaluate output

```bash
uv run swebench-eval output.jsonl
```

## Recommended operating pattern

- Always run preflight immediately before long jobs.
- Use only models that preflight marks available.
- Run one-model, low-`n-limit` smoke first.
- Increase workers and limits gradually to control cost and runtime risk.
