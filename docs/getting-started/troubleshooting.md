# Troubleshooting

Common failures and how to fix or work around them.

## verify-bundle: manifest.json missing

When you run `labtrust verify-bundle --bundle <dir>` and `<dir>` is a **release root** (the output of `package-release`, containing `MANIFEST.v0.1.json`, `receipts/`, `results/`, and related artifacts), you may see `manifest.json: missing`.

`verify-bundle` expects a single **EvidenceBundle.v0.1** directory whose path contains `manifest.json`. A release root uses a different layout; each EvidenceBundle lives under `release_dir/receipts/<task>_cond_<n>/EvidenceBundle.v0.1`.

To resolve the issue:

1. Pass a specific EvidenceBundle path, for example  
   `labtrust verify-bundle --bundle /path/to/release/receipts/taska_cond_0/EvidenceBundle.v0.1`
2. To verify the whole release, run `labtrust verify-release --release-dir <path> [--strict-fingerprints]` (verifies every EvidenceBundle, risk register, and RELEASE_MANIFEST hashes), or use the E2E script `bash scripts/ci_e2e_artifacts_chain.sh` (package-release → export-risk-register → build-release-manifest → verify-release --strict-fingerprints). See [Trust verification](../risk-and-security/trust_verification.md) and [Frozen contracts](../contracts/frozen_contracts.md) (verify-bundle, verify-release).

## verify-bundle: hashchain length mismatch

When you run `labtrust verify-bundle --bundle <dir>`, you may see `hashchain_proof: length N != episode_log entries M`.

The evidence bundle’s `hashchain_proof.json` reported a `length` that did not match the number of lines in `episode_log_subset.jsonl`. Current code sets `length = len(entries)` when writing the proof so the verifier’s check passes.

If the error persists, use a build that includes that fix (proof length written as entry count), re-run the run that produced the bundle (for example `package-release` or `export-receipts`), and verify again. Avoid hand-editing `hashchain_proof.json` to change `length` unless you also keep chain hashes consistent.

## Policy directory not found (PolicyPathError)

Any CLI command or test that needs policy may raise `PolicyPathError: Policy directory not found` or report that `LABTRUST_POLICY_DIR=...` does not exist or is not a directory.

The library resolves the policy root in this order: (1) `LABTRUST_POLICY_DIR` when set (must be an existing directory), (2) package data when installed from wheel, (3) current or parent directory containing `policy/` with `policy/emits/`. When none of these yield a valid policy directory, **PolicyPathError** is raised with an explicit message.

To resolve the issue:

1. **Run from repo root** so that `policy/` and `policy/emits/` exist under the current directory (or a parent). This is the usual case for development and CI.
2. **When using LABTRUST_POLICY_DIR**, set it to the **absolute or resolved path** of the policy directory (the directory that contains `emits/`, `schemas/`, and related subtrees). Ensure the path exists and is a directory; otherwise the CLI raises with a clear message.
3. When installed from PyPI/wheel, policy loads from the package and no repo checkout is required. If PolicyPathError appears after a pip install, check that `LABTRUST_POLICY_DIR` is unset or points at a valid directory.

## Policy validation errors

When `labtrust validate-policy` (or `validate-policy --partner <id>`) reports schema or structural errors:

1. Run `labtrust validate-policy` and read the reported file and key (for example missing required key, wrong type). Fix the YAML/JSON under `policy/` to match the schema in `policy/schemas/`.
2. For a partner overlay, ensure `policy/partners/<id>/` exists and overlay files follow the same schema as base policy. Use `labtrust validate-policy --partner <id>` to validate the overlay.
3. When you add a new policy file, ensure it is listed in the loader’s validation list (see `src/labtrust_gym/policy/validate.py`) and that the schema exists under `policy/schemas/` when applicable.

## Pack gate failures (security_gate_failed)

`COORDINATION_DECISION.v0.1.json` may show `verdict: "security_gate_failed"`, or `labtrust check-security-gate --run <dir>` may exit 1.

One or more cells in the coordination security pack failed the gate rules (for example attack_success_rate &gt; 0, or violations above nominal+delta). Gate rules are in `policy/coordination/coordination_security_pack_gate.v0.1.yaml`.

Recommended steps:

1. Open `pack_gate.md` in the pack output directory and find rows with verdict **FAIL**.
2. For each failed cell, check the rationale (for example `attack_success_rate=0.2 (expected 0)`). Fix the coordination method or defenses so the metric meets the rule, or relax the gate rule in the policy (with approval).
3. Re-run the pack with `labtrust run-coordination-security-pack --out <dir> ...`, then `labtrust build-lab-coordination-report --pack-dir <dir>` and `labtrust check-security-gate --run <dir>` until the gate passes.
4. Treat `security_gate_failed` as a blocking condition before deploying a coordination method.

## No admissible method (selection policy constraints)

`COORDINATION_DECISION` may show `verdict: "no_admissible_method"` and list violated constraints.

No method satisfied all hard constraints in the selection policy (for example violation ceiling, attack success rate ceiling, cost ceiling). See `policy/coordination/coordination_selection_policy.v0.1.yaml`.

Recommended steps:

1. Open `COORDINATION_DECISION.md` and read the “Disqualified” section and “Violated constraints” sample.
2. Improve the methods so at least one passes all constraints, or relax constraints in the selection policy for your org (for example increase violation ceiling) and re-run the pack and report.
3. Follow the recommended actions in the decision artifact (for example “Tighten defenses or add safe fallback for failing methods”).

## train-ppo: mean reward 0.00

After training, `labtrust eval-ppo` may report mean reward 0.00.

Throughput_sla rewards only when `RELEASE_RESULT` is emitted (QC/supervisor). In the PPO setup those agents are scripted and may never release in short runs.

The task now includes **schedule_reward** (0.1) for each accepted QUEUE_RUN by ops_0, so you get non-zero reward during training. Retrain with the current code; if reward stays at 0.00, increase timesteps or check that the policy sometimes takes action 2 (QUEUE_RUN).

## eval-agent with PPO model

To run the benchmark with a trained PPO model as ops_0, use the built-in PPOAgent. Set `LABTRUST_PPO_MODEL` to the path to your `model.zip` (for example `labtrust_runs/ppo_10k/model.zip`), then run:

`labtrust eval-agent --task throughput_sla --episodes 5 --agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent --out labtrust_runs/ppo_bench_results.json`

See [MARL baselines](../agents/marl_baselines.md).

## Paths with special characters

Commands may fail or produce wrong paths when the repo root or `--out` path contains spaces, parentheses, or non-ASCII characters.

Quote paths in shell commands (for example `--out "/path/with spaces"`). On Windows use double quotes in PowerShell and Cmd. Prefer ASCII-only paths for `--out` and `LABTRUST_POLICY_DIR` when possible. If you hit encoding errors, set `PYTHONUTF8=1` (Python 3.7+) or use an ASCII-only repo path.

## CLI error messages

A CLI command may exit with a generic error or traceback that lacks a clear explanation.

Check stderr for the first line that mentions a file, key, or constraint (for example "manifest: missing file", "Unknown injection_id"). Use `--help` on the subcommand for required arguments. For policy or schema errors, run `labtrust validate-policy` first. When the error is unclear, run with minimal args (for example one episode, one task) to isolate the failure. Report unclear errors with the exact command and stderr so we can improve messages.

## E2E artifacts chain fails

`make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh` may fail at package-release, verify-release, or export-risk-register.

Check each stage:

1. **package-release** — Ensure `pip install -e ".[dev,env,plots]"` and no network required (script sets `LABTRUST_ALLOW_NETWORK=0`). When it fails on a missing task or policy, fix the repo state (for example restore a deleted policy file).
2. **verify-release** — See “verify-bundle: hashchain length mismatch” above. The script runs `labtrust verify-release --release-dir <release_dir>`, which verifies every EvidenceBundle under `receipts/*/EvidenceBundle.v0.1`. When a bundle fails, apply the same checks as in that section.
3. **export-risk-register / schema-and-crosswalk** — When the risk register bundle fails schema or crosswalk checks, fix the policy or run dirs so that evidence and risk IDs align (see [Risk register](../risk-and-security/risk_register.md)).

## Live LLM runs: zero throughput and 100% error rate

Cross-provider or llm_live pack runs may complete but show `throughput: 0`, `llm_error_rate: 1`, and `total_tokens: 0` in the result JSON. The run can finish without crashing; the pipeline executed 80 steps and made LLM calls, but every call was counted as an error.

The live LLM backend (openai_live, anthropic_live) never received a successful API response. Common causes include **OPENAI_API_KEY** or **ANTHROPIC_API_KEY** missing or invisible to the process (wrong env, or a `.env` file the runner never loads), blocked network, or an invalid API key. Schema errors (for example provider fields outside the strict ActionProposal schema) also yield NOOP and count as errors; the code uses strict schemas (`additionalProperties: false`) for OpenAI and Anthropic.

The pipeline does not write stderr or a log file into the run directory. The result JSON records `error_count` and `error_rate` but omits the underlying exception message. To see the actual error:

1. **Minimal backend check** — From repo root, run:
   ```bash
   LABTRUST_ALLOW_NETWORK=1 python scripts/check_llm_backends_live.py --backends openai_live
   ```
   (Use `anthropic_live` or `openai_live,anthropic_live` as needed.) The script loads `.env` from the repo root when present (python-dotenv or fallback parser), so running it from repo root is enough for key visibility.
   - It prints `success`, `total_calls`, `error_count`, `error_rate`, `total_tokens`, and `last_metrics.error_code`; when present, `last_metrics.error_message` (for example connection refused, invalid API key).
2. **Interpretation** — `error_code: LLM_PROVIDER_ERROR` with no `error_message` usually means the backend returned before calling the API (for example **API key missing or empty**). An `error_message` carries the HTTP client or API exception (for example 401, timeout, connection error).

Set the correct API key in the environment used by the process (for example `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`), ensure the key is valid and has quota, then re-run `check_llm_backends_live.py`. Once that reports `success: true` and non-zero tokens, re-run the full pack.

**Deterministic comparison** — Running `labtrust run-benchmark --task throughput_sla --episodes 1 --seed 42 --out <file>` **without** `--llm-backend` uses scripted agents only (deterministic). That confirms the task and env run; throughput can still be 0 with the default 80-step horizon when no specimen reaches RELEASE_RESULT in time.

## See also

- [Forker guide](forkers.md) – pipeline and partner overlay.
- [Trust verification](../risk-and-security/trust_verification.md) and [CI](../operations/ci.md) – E2E chain before release.
- [CI gates](../operations/ci.md) – what runs on push/PR and optional jobs.
