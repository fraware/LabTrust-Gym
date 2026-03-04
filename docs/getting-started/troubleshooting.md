# Troubleshooting

Common failures and how to fix or work around them.

## verify-bundle: manifest.json missing

**Symptom:** `manifest.json: missing` when running `labtrust verify-bundle --bundle <dir>` and `<dir>` is a **release root** (the output of `package-release`, containing `MANIFEST.v0.1.json`, `receipts/`, `results/`, etc.).

**Cause:** `verify-bundle` expects a single **EvidenceBundle.v0.1** directory (a path that contains `manifest.json`). The release root is not an EvidenceBundle; each EvidenceBundle lives under `release_dir/receipts/<task>_cond_<n>/EvidenceBundle.v0.1`.

**Fix:**

1. Pass a specific EvidenceBundle path, e.g.  
   `labtrust verify-bundle --bundle /path/to/release/receipts/taska_cond_0/EvidenceBundle.v0.1`
2. To verify the whole release, run `labtrust verify-release --release-dir <path> [--strict-fingerprints]` (verifies every EvidenceBundle, risk register, and RELEASE_MANIFEST hashes), or use the E2E script: `bash scripts/ci_e2e_artifacts_chain.sh` (package-release → export-risk-register → build-release-manifest → verify-release --strict-fingerprints). See [Trust verification](../risk-and-security/trust_verification.md) and [Frozen contracts](../contracts/frozen_contracts.md) (verify-bundle, verify-release).

## verify-bundle: hashchain length mismatch

**Symptom:** `hashchain_proof: length N != episode_log entries M` when running `labtrust verify-bundle --bundle <dir>`.

**Cause:** The evidence bundle’s `hashchain_proof.json` reported a `length` that did not match the number of lines in `episode_log_subset.jsonl`. This is resolved in the current code: the bundle writer sets `length = len(entries)` when writing the proof so the verifier’s check passes.

**If you still see it:** Ensure you are using a build that includes the fix (proof length written as entry count). Re-run the run that produced the bundle (e.g. `package-release` or `export-receipts`) and verify again. Do not hand-edit `hashchain_proof.json` to change `length` without also ensuring the chain hashes are consistent.

## Policy directory not found (PolicyPathError)

**Symptom:** `PolicyPathError: Policy directory not found` or `LABTRUST_POLICY_DIR=... does not exist` (or `is not a directory`) when running any CLI command or test that needs policy.

**Cause:** The library resolves the policy root in this order: (1) `LABTRUST_POLICY_DIR` (if set, must be an existing directory), (2) package data (when installed from wheel), (3) current or parent directory containing `policy/` with `policy/emits/`. If none of these yield a valid policy directory, **PolicyPathError** is raised instead of silently using the wrong path.

**Fix:**

1. **Run from repo root** so that `policy/` and `policy/emits/` exist under the current directory (or a parent). This is the usual case for development and CI.
2. **If using LABTRUST_POLICY_DIR:** Set it to the **absolute or resolved path** of the policy directory (the directory that contains `emits/`, `schemas/`, etc.). Ensure the path exists and is a directory; otherwise the CLI will raise with a clear message.
3. When installed from PyPI/wheel, policy is loaded from the package; you do not need a repo. If you see PolicyPathError after a pip install, ensure you are not overriding `LABTRUST_POLICY_DIR` to a missing path.

## Policy validation errors

**Symptom:** `labtrust validate-policy` (or `validate-policy --partner <id>`) reports schema or structural errors.

**Fix:**

1. Run `labtrust validate-policy` and read the reported file and key (e.g. missing required key, wrong type). Fix the YAML/JSON under `policy/` to match the schema in `policy/schemas/`.
2. For partner overlay: ensure `policy/partners/<id>/` exists and overlay files follow the same schema as base policy. Use `labtrust validate-policy --partner <id>` to validate the overlay.
3. If you added a new policy file, ensure it is listed in the loader’s validation list (see `policy/validate.py` or the validate-policy implementation) and that the schema exists under `policy/schemas/` if applicable.

## Pack gate failures (security_gate_failed)

**Symptom:** `COORDINATION_DECISION.v0.1.json` has `verdict: "security_gate_failed"` or `labtrust check-security-gate --run <dir>` exits 1.

**Cause:** One or more cells in the coordination security pack failed the gate rules (e.g. attack_success_rate &gt; 0, or violations above nominal+delta). Gate rules are in `policy/coordination/coordination_security_pack_gate.v0.1.yaml`.

**What to do:**

1. Open `pack_gate.md` in the pack output directory and find rows with verdict **FAIL**.
2. For each failed cell, check the rationale (e.g. `attack_success_rate=0.2 (expected 0)`). Fix the coordination method or defenses so the metric meets the rule, or relax the gate rule in the policy (with approval).
3. Re-run the pack: `labtrust run-coordination-security-pack --out <dir> ...` then `labtrust build-lab-coordination-report --pack-dir <dir>` and `labtrust check-security-gate --run <dir>` until the gate passes.
4. Do not deploy a coordination method when the decision is `security_gate_failed`; treat it as a blocking condition.

## No admissible method (selection policy constraints)

**Symptom:** `COORDINATION_DECISION` has `verdict: "no_admissible_method"` and lists violated constraints.

**Cause:** No method satisfied all hard constraints in the selection policy (e.g. violation ceiling, attack success rate ceiling, cost ceiling). See `policy/coordination/coordination_selection_policy.v0.1.yaml`.

**What to do:**

1. Open `COORDINATION_DECISION.md` and read the “Disqualified” section and “Violated constraints” sample.
2. Either improve the methods (so at least one passes all constraints) or relax constraints in the selection policy for your org (e.g. increase violation ceiling) and re-run the pack and report.
3. Use the recommended actions in the decision artifact (e.g. “Tighten defenses or add safe fallback for failing methods”).

## train-ppo: mean reward 0.00

**Symptom:** After training, `labtrust eval-ppo` reports mean reward 0.00.

**Cause:** Throughput_sla rewards only when `RELEASE_RESULT` is emitted (QC/supervisor). In the PPO setup those agents are scripted and may never release in short runs.

**Fix:** The task now includes **schedule_reward** (0.1) for each accepted QUEUE_RUN by ops_0, so you get non-zero reward during training. Retrain with the current code; if you still see 0.00, increase timesteps or check that the policy is taking action 2 (QUEUE_RUN) sometimes.

## eval-agent with PPO model

**Symptom:** You want to run the benchmark with a trained PPO model as ops_0.

**Fix:** Use the built-in PPOAgent. Set `LABTRUST_PPO_MODEL` to the path to your `model.zip` (e.g. `labtrust_runs/ppo_10k/model.zip`), then run:

`labtrust eval-agent --task throughput_sla --episodes 5 --agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent --out labtrust_runs/ppo_bench_results.json`

See [MARL baselines](../agents/marl_baselines.md).

## Paths with special characters

**Symptom:** Commands fail or produce wrong paths when the repo root or `--out` path contains spaces, parentheses, or non-ASCII characters.

**Fix:** Quote paths in shell commands (e.g. `--out "/path/with spaces"`). On Windows use double quotes in PowerShell and Cmd. Prefer paths without special characters for `--out` and `LABTRUST_POLICY_DIR` when possible. If you hit encoding errors, set `PYTHONUTF8=1` (Python 3.7+) or use a repo path that is ASCII-only.

## CLI error messages

**Symptom:** A CLI command exits with a generic error or traceback that does not clearly say what went wrong.

**Fix:** Check stderr for the first line that mentions a file, key, or constraint (e.g. "manifest: missing file", "Unknown injection_id"). Use `--help` on the subcommand for required arguments. For policy or schema errors, run `labtrust validate-policy` first. If the error is unclear, run with minimal args (e.g. one episode, one task) to isolate the failure. Report unclear errors with the exact command and stderr so we can improve messages.

## E2E artifacts chain fails

**Symptom:** `make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh` fails at package-release, verify-release, or export-risk-register.

**Checks:**

1. **package-release:** Ensure `pip install -e ".[dev,env,plots]"` and no network required (script sets `LABTRUST_ALLOW_NETWORK=0`). If it fails on a missing task or policy, fix the repo state (e.g. restore deleted policy file).
2. **verify-release:** See “verify-bundle: hashchain length mismatch” above. The script runs `labtrust verify-release --release-dir <release_dir>`, which verifies every EvidenceBundle under `receipts/*/EvidenceBundle.v0.1`. If a bundle fails, see "verify-bundle: hashchain length mismatch" above (same checks apply per bundle).
3. **export-risk-register / schema-and-crosswalk:** If the risk register bundle fails schema or crosswalk checks, fix the policy or run dirs so that evidence and risk IDs align (see [Risk register](../risk-and-security/risk_register.md)).

## Live LLM runs: zero throughput and 100% error rate

**Symptom:** Cross-provider or llm_live pack runs complete but `throughput_sla` (and other tasks) show `throughput: 0`, `llm_error_rate: 1`, `total_tokens: 0` in the result JSON. The run did not crash; the pipeline executed 80 steps and made LLM calls, but every call was counted as an error.

**Cause:** The live LLM backend (openai_live, anthropic_live) never got a successful API response. Common causes: **OPENAI_API_KEY** or **ANTHROPIC_API_KEY** not set or not visible to the process (e.g. wrong env, or key in a `.env` that is not loaded by the runner); network blocked; invalid API key. Schema errors (e.g. provider returning fields not in the strict ActionProposal schema) also yield NOOP and count as errors; the code uses strict schemas (`additionalProperties: false`) for OpenAI and Anthropic.

**Logs:** The pipeline does not write stderr or a log file into the run directory. The result JSON records `error_count` and `error_rate` but not the underlying exception message. To see the actual error:

1. **Minimal backend check:** From repo root, run:
   ```bash
   LABTRUST_ALLOW_NETWORK=1 python scripts/check_llm_backends_live.py --backends openai_live
   ```
   (Use `anthropic_live` or `openai_live,anthropic_live` as needed.) The script loads `.env` from the repo root when present (python-dotenv or fallback parser), so running it from repo root is sufficient for key visibility.
   - It prints: `success`, `total_calls`, `error_count`, `error_rate`, `total_tokens`; and `last_metrics.error_code` and, when present, `last_metrics.error_message` (e.g. connection refused, invalid API key).
2. **Interpretation:** If you see `error_code: LLM_PROVIDER_ERROR` and **no** `error_message`, the backend returned before calling the API (e.g. **API key missing or empty**). If you see an `error_message`, that is the exception from the HTTP client or API (e.g. 401, timeout, connection error).

**Fix:** Set the correct API key in the environment used by the process (e.g. `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`), ensure the key is valid and has quota, then re-run `check_llm_backends_live.py`. Once that reports `success: true` and non-zero tokens, re-run the full pack.

**Deterministic comparison:** Running `labtrust run-benchmark --task throughput_sla --episodes 1 --seed 42 --out <file>` **without** `--llm-backend` uses scripted agents only (deterministic). That confirms the task and env run; throughput can still be 0 with the default 80-step horizon if no specimen reaches RELEASE_RESULT in time.

## See also

- [Forker guide](forkers.md) – pipeline and partner overlay.
- [Trust verification](../risk-and-security/trust_verification.md) and [CI](../operations/ci.md) – E2E chain before release.
- [CI gates](../operations/ci.md) – what runs on push/PR and optional jobs.
