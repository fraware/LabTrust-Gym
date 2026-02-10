# Troubleshooting

Common failures and how to fix or work around them.

## verify-bundle: manifest.json missing

**Symptom:** `manifest.json: missing` when running `labtrust verify-bundle --bundle <dir>` and `<dir>` is a **release root** (the output of `package-release`, containing `MANIFEST.v0.1.json`, `receipts/`, `results/`, etc.).

**Cause:** `verify-bundle` expects a single **EvidenceBundle.v0.1** directory (a path that contains `manifest.json`). The release root is not an EvidenceBundle; each EvidenceBundle lives under `release_dir/receipts/<task>_cond_<n>/EvidenceBundle.v0.1`.

**Fix:**

1. Pass a specific EvidenceBundle path, e.g.  
   `labtrust verify-bundle --bundle /path/to/release/receipts/taska_cond_0/EvidenceBundle.v0.1`
2. To verify the whole release, run `labtrust verify-release --release-dir <path>` (verifies every EvidenceBundle under `receipts/`), or use the E2E script: `bash scripts/ci_e2e_artifacts_chain.sh`. See [Release checklist](release_checklist.md) and [Evidence verification](evidence_verification.md).

## verify-bundle: hashchain length mismatch

**Symptom:** `hashchain_proof: length N != episode_log entries M` when running `labtrust verify-bundle --bundle <dir>`.

**Cause:** The evidence bundle’s `hashchain_proof.json` reported a `length` that did not match the number of lines in `episode_log_subset.jsonl`. This is resolved in the current code: the bundle writer sets `length = len(entries)` when writing the proof so the verifier’s check passes.

**If you still see it:** Ensure you are using a build that includes the fix (proof length written as entry count). Re-run the run that produced the bundle (e.g. `package-release` or `export-receipts`) and verify again. Do not hand-edit `hashchain_proof.json` to change `length` without also ensuring the chain hashes are consistent.

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

## E2E artifacts chain fails

**Symptom:** `make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh` fails at package-release, verify-release, or export-risk-register.

**Checks:**

1. **package-release:** Ensure `pip install -e ".[dev,env,plots]"` and no network required (script sets `LABTRUST_ALLOW_NETWORK=0`). If it fails on a missing task or policy, fix the repo state (e.g. restore deleted policy file).
2. **verify-release:** See “verify-bundle: hashchain length mismatch” above. The script runs `labtrust verify-release --release-dir <release_dir>`, which verifies every EvidenceBundle under `receipts/*/EvidenceBundle.v0.1`. If a bundle fails, see "verify-bundle: hashchain length mismatch" above (same checks apply per bundle).
3. **export-risk-register / schema-and-crosswalk:** If the risk register bundle fails schema or crosswalk checks, fix the policy or run dirs so that evidence and risk IDs align (see [Risk register](risk_register.md)).

## See also

- [Forker guide](FORKER_GUIDE.md) – pipeline and partner overlay.
- [Release checklist](release_checklist.md) – mandatory E2E chain before release.
- [CI gates](ci.md) – what runs on push/PR and optional jobs.
