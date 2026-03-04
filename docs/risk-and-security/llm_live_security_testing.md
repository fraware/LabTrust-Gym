# Live LLM security testing

This document describes how to run the security suite and official benchmark pack under **live LLM conditions** and how to feed the resulting run directories into the risk register export so that tool, flow, and data risk evidence appears in the bundle.

## When to run under live LLM

- **Deterministic evidence (default):** The security suite runs `test_ref` attacks via pytest (no LLM) and prompt-injection scenarios with fixed adversarial strings. This is sufficient for CI and for evidencing tool/flow/data controls (registry, sandbox, arg validation, flow metrics, provenance).
- **Live LLM evidence:** To evidence that **prompt-injection and jailbreak** defenses hold against live LLM-generated payloads, run the suite with `--llm-attacker` and `--allow-network`. To evidence that **coordination and benchmarks** behave correctly with a live LLM backend, run the official pack or coordination study with `--pipeline-mode llm_live`.

Tool/flow/data tests (SEC-TOOL-*, SEC-FLOW-*, SEC-DATA-PROV-001) do **not** use a live LLM; they are deterministic. The risk register bundle can still include evidence from runs that mix deterministic suite output and optional LLM-attacker or llm_live pack output.

## Running the security suite with LLM attacker

Attacks with `llm_attacker: true` in `policy/golden/security_attack_suite.v0.1.yaml` (e.g. SEC-LLM-ATTACK-001 through SEC-LLM-ATTACK-010) use a live LLM to generate adversarial strings. Run them only when you have network access and the appropriate API key:

```bash
labtrust run-security-suite --out ./security_llm_live_out --llm-attacker --allow-network --llm-backend openai_live [--llm-model gpt-4o-mini] [--smoke]
```

- **--llm-attacker**: Include LLM-attacker attacks. Requires **--allow-network** and **--llm-backend**.
- **--allow-network**: Required for live API calls. Or set `LABTRUST_ALLOW_NETWORK=1`.
- **--llm-backend**: `openai_live`, `ollama_live`, or `anthropic_live`. Requires the corresponding API key (e.g. `OPENAI_API_KEY`).
- **--smoke**: Run only smoke attacks (default when omitted in CI). Omit for full suite.

Output: `./security_llm_live_out/SECURITY/attack_results.json` (and optionally `llm_attacker_baseline.json` for regression). Use this directory as one of the run dirs when exporting the risk register.

## Running the official pack under llm_live

The official benchmark pack runs core tasks, coordination methods, and the security suite. Under `llm_live`, the pack uses policy v0.2 and writes TRANSPARENCY_LOG and live_evaluation_metadata for reproducibility.

**To actually use a live LLM** for baselines and coordination tasks, you must pass **--llm-backend** (e.g. `openai_live`). Without it, the pack runs with `llm_backend='none'`: pipeline_mode is still llm_live (v0.2 policy, transparency layout) but no live API calls are made.

```bash
labtrust run-official-pack --out ./pack_llm_live_out --pipeline-mode llm_live --allow-network --llm-backend openai_live [--smoke] [--seed-base 42]
```

- **--llm-backend openai_live** (or `ollama_live`, `anthropic_live`): use that backend for tasks that call an LLM; requires the corresponding API key (e.g. `OPENAI_API_KEY`).
- Produces `./pack_llm_live_out/SECURITY/` (attack_results from suite), `./pack_llm_live_out/TRANSPARENCY_LOG/llm_live.json`, `./pack_llm_live_out/live_evaluation_metadata.json`, and baseline/coordination outputs.
- Use `./pack_llm_live_out` as a run dir when exporting the risk register so that SECURITY evidence and (when applicable) coordination evidence are included in the bundle.

## Including LLM-attacker in the pack run

The pack runs the security suite in **smoke-only** by default and does **not** pass `--llm-attacker`. To run the suite with LLM attacker as part of a single flow, run the suite separately with `--llm-attacker` (see above), then include both the pack output dir and the security_llm_live_out dir when exporting the risk register.

## Feeding run dirs into the risk register

After producing one or more run directories (e.g. deterministic security smoke, optional security with LLM attacker, optional official pack with llm_live), export the risk register so evidence appears in the bundle:

```bash
labtrust export-risk-register --out ./risk_register_out --runs ./security_smoke_out [--runs ./security_llm_live_out] [--runs ./pack_llm_live_out]
```

- Each run dir is scanned for `SECURITY/attack_results.json`, `SECURITY/coverage.json`, coordination outputs, `MANIFEST.v0.1.json`, etc.
- The bundle `risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json` will list evidence per risk; present evidence includes run-local paths and reproduce commands.
- **To pass validate-coverage --strict** when using only real run dirs (e.g. security_llm_out + pack_llm_out_live), include the coverage fixtures so every required_bench risk_id has evidence: add `--runs tests/fixtures/ui_fixtures --runs tests/fixtures/coord_pack_fixture_minimal` to the export command. Alternatively, run the full required_bench matrix and include its output; marl_ppo R-DATA-002 is not required.
- To inject the bundle into run dirs for the viewer: add `--inject-ui-export`.

## CI wiring (optional)

The workflow **`.github/workflows/llm_live_optional_smoke.yml`** runs only on `workflow_dispatch` and schedule; it does not run on push/PR and never blocks merges. When `OPENAI_API_KEY` is set, it:

1. Runs LLM healthcheck and official pack smoke with `--pipeline-mode llm_live`.
2. Runs coordination smoke (coord_scale, llm_central_planner) with `--pipeline-mode llm_live`.
3. Runs the security suite with **--llm-attacker** and uploads `SECURITY/` artifacts.
4. Optionally runs LLM attacker baseline regression if `tests/fixtures/llm_attacker_baseline.json` exists.

To include risk register export in CI after an llm_live run, add a step that runs `labtrust export-risk-register --out ./risk_register_out --runs ./llm_live_smoke_out` and upload `risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json` as an artifact. See [CI](../operations/ci.md) for the main CI layout and the "Optional: LLM live E2E in CI" section.

## Summary

| Goal | Command |
|------|--------|
| Deterministic security evidence (CI) | `labtrust run-security-suite --out <dir> [--smoke]` |
| Security + live LLM attacker | `labtrust run-security-suite --out <dir> --llm-attacker --allow-network --llm-backend openai_live` |
| Official pack under llm_live | `labtrust run-official-pack --out <dir> --pipeline-mode llm_live --allow-network --llm-backend openai_live` |
| Risk register bundle from runs | `labtrust export-risk-register --out <out> --runs <dir1> [--runs <dir2> ...]` |

Tool/flow/data risks (R-TOOL-001 through R-TOOL-006, R-FLOW-001/002, R-DATA-001) are evidenced by deterministic tests (test_ref and scenario_ref). Running under live LLM adds evidence for prompt-injection/jailbreak (R-CAP-001) and for coordination behaviour when the pack or study uses an LLM backend.

## Optional expansion

- **R-TOOL-005 (LLM-generated malformed tool args):** The suite evidences R-TOOL-005 via SEC-TOOL-MISPARAM-001 and SEC-TOOL-MISPARAM-FUZZ-001 (deterministic). Optionally add one or more attack_ids in `policy/golden/security_attack_suite.v0.1.yaml` with `llm_attacker: true` that use a live LLM to generate malformed tool calls; add the test_ref to the allowlist and map to R-TOOL-005 in the coverage map. Run them with `--llm-attacker --allow-network --llm-backend openai_live`.
- **Required-bench or pack under llm_live:** To produce evidence for the risk register from a full required_bench matrix or official pack run with a live LLM, run `scripts/run_required_bench_matrix.sh` (or the pack) with `--pipeline-mode llm_live` and `--llm-backend openai_live` (and `--allow-network`), then `labtrust export-risk-register --out <out> --runs <run_dirs>` and `labtrust validate-coverage --strict`. A scheduled or manual workflow can run this periodically and attach the bundle as an artifact. See `.github/workflows/required_bench_matrix.yml` for the deterministic matrix job; extend it or add a separate llm_live job if desired.

## Notes

- **Pack with llm_live but no --llm-backend:** Logs will show `llm_backend='none'`. The pack still runs (v0.2 policy, SECURITY suite, transparency layout) but baseline and coordination tasks do not call a live LLM. To get real live coordination and model_id/latency in TRANSPARENCY_LOG, re-run with `--llm-backend openai_live` (and set `OPENAI_API_KEY`).
