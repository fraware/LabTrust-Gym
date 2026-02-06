# Security attack suite and securitization packet

The security attack suite is a **first-class golden benchmark** that maps risks (from `policy/risks/risk_registry.v0.1.yaml`) to controls and executable scenarios. It provides a coverage harness for jailbreaks and prompt injection, tool vulnerability and egress, identity spoofing and replay, memory poisoning, and observability. The **securitization packet** is an auditable set of artifacts emitted under `SECURITY/` for release and paper artifacts.

## Prerequisites

The suite needs packages in the **same Python environment** that runs `labtrust`. Prefer `python -m pip` so the active interpreter (e.g. your venv) gets the packages:

- **Prompt-injection attacks (SEC-PI-001 to SEC-PI-004):** `pettingzoo` and `gymnasium`. Install with: `python -m pip install pettingzoo gymnasium` or `pip install -e ".[env]"`.
- **Test-ref attacks (SEC-TOOL-001, SEC-COORD-001, etc.):** `pytest` (run as subprocess). Install with: `python -m pip install pytest` or `pip install -e ".[dev]"`.

Full suite in current environment: `python -m pip install -e ".[dev,env]"`. If you use a virtual environment, activate it first.

If you see **0/10 passed**, check `SECURITY/attack_results.json` in the output directory for each attack’s `error` field. Typical causes: missing pettingzoo/gymnasium or pytest in the environment that runs `labtrust`.

**Windows / venv: pip installs to the wrong Python**  
If you run `pip install ...` and see "Requirement already satisfied" under `...\Python\Python312\lib\site-packages` (global Python) while `labtrust` runs from `.venv\Scripts\python.exe`, packages are in the wrong environment. Use the **exact copy-paste command** printed by the CLI hint. In **PowerShell** you must use the call operator: `& "C:\Path\To\LabTrust-Gym\.venv\Scripts\python.exe" -m pip install pettingzoo gymnasium pytest`. In Cmd, omit the leading `& `.

## Overview

- **Attack suite**: `policy/golden/security_attack_suite.v0.1.yaml` defines controls (e.g. CTRL-LLM-SHIELD, CTRL-TOOL-SANDBOX, CTRL-COORD-IDENTITY, CTRL-MEMORY) and attacks with `risk_id`, `control_id`, `scenario_ref` (prompt-injection scenarios) or `test_ref` (pytest module), `expected_outcome` (blocked/detected), and `smoke` (CI flag).
- **Runner**: `src/labtrust_gym/benchmarks/security_runner.py` loads the suite, runs each attack (prompt-injection in-process or test_ref via pytest subprocess), and writes `SECURITY/attack_results.json`.
- **Securitization outputs**: `src/labtrust_gym/benchmarks/securitization.py` produces `SECURITY/coverage.json`, `SECURITY/coverage.md` (risk to control to tests to artifacts), `SECURITY/reason_codes.md` (from reason_code_registry, namespaces TOOL/COORD/MEM/ADV), and `SECURITY/deps_inventory.json` (minimal SBOM-like: tool registry fingerprint, RBAC path/fingerprint, policy paths with sha256).

All of this is **deterministic** for fixed seed and unchanged policy; smoke mode runs only attacks with `smoke: true` and is CI-runnable.

## Running the suite

**Standalone:**

```bash
labtrust run-security-suite --out <dir> [--seed 42] [--full]
```

- Writes `SECURITY/attack_results.json` and the full securitization packet under `<dir>/SECURITY/`.
- Default: smoke-only (attacks with `smoke: true`). Use `--full` to run all attacks.
- Exit code 0 only if all attacks pass.

**As part of paper release:**

The `paper_v0.1` package-release profile runs the security suite (smoke-only, seed = seed-base) and emits the securitization packet automatically. Outputs appear under `<dir>/SECURITY/` in the release artifact.

## Artifacts under SECURITY/

| File | Description |
|------|--------------|
| `attack_results.json` | Suite run: version, metadata, results per attack (attack_id, risk_id, control_id, passed, duration_ms, error), summary (total, passed, failed). |
| `coverage.json` | Risk-to-controls mapping, control-to-tests, artifact paths, risk_names, control_names. |
| `coverage.md` | Human-readable risk -> control -> tests -> artifacts. |
| `reason_codes.md` | Table of security-relevant reason codes (TOOL, COORD, MEM, ADV) from the registry. |
| `deps_inventory.json` | Tool registry path and fingerprint, RBAC path and fingerprint, policy_paths (path + sha256). |

## Coverage mapping

Coverage is derived from `risk_registry.v0.1.yaml` and `security_attack_suite.v0.1.yaml`:

- **risk_to_controls**: Each risk_id maps to the controls and attack_ids that exercise it.
- **control_to_tests**: Each control maps to scenario_ref or test_ref identifiers.
- **artifacts**: References to `SECURITY/attack_results.json` and `receipts/` for audit.

This gives reviewers a clear path from risk to control to test to artifact.

## Verification and fingerprints

Evidence bundle verification (`labtrust verify-bundle`) already checks:

- **tool_registry_fingerprint** (when present in manifest): recompute from `policy/tool_registry.v0.1.yaml`, match.
- **rbac_policy_fingerprint** (when present): recompute from `policy/rbac/rbac_policy.v0.1.yaml`, match.
- **coordination_policy_fingerprint** (when present): recompute from `policy/coordination_identity_policy.v0.1.yaml`, match.
- **memory_policy_fingerprint** (when present): recompute from `policy/memory_policy.v0.1.yaml`, match.

Bundles that do not include these optional keys are unchanged; when receipts or manifests add them, verify-bundle validates them. See [Evidence verification](evidence_verification.md).

## Coordination red-team attacks (TaskH)

The **coordination red-team** makes TaskH genuinely adversarial: collusion strategies, stealthy poisoning, delayed-trigger attacks, identity rotation, replay attempts, and mixed honest/malicious population. All adversaries are deterministic for official runs.

**Runnable suite entries** (in `policy/golden/security_attack_suite.v0.1.yaml`):

- **SEC-COORD-RT-001**: Strict signatures and bus replay protection block ID spoof and replay (`tests.test_coord_red_team_definitions`; control CTRL-COORD-IDENTITY).
- **SEC-COORD-RT-002**: Collusion and bid spoof definitions consistent; blocked when expected (`tests.test_coord_red_team_definitions`; control CTRL-COORD-IDENTITY).

**Injection policy**: `policy/coordination/injections.v0.2.yaml` (version 0.2) defines the red-team injection set with clear success, detection, and containment definitions per injection. Injection IDs include:

- `INJ-COLLUSION-001`, `INJ-BID-SPOOF-001` (collusion)
- `INJ-SLOW-POISON-001` (slow-roll / delayed-trigger poisoning)
- `INJ-ID-SPOOF-001` (identity rotation)
- `INJ-REPLAY-001` (replay attempts)
- `INJ-COMMS-POISON-001` (stealthy poisoning)
- `INJ-MEMORY-POISON-001` (delayed-trigger state corruption)

**Adversary library**: `src/labtrust_gym/baselines/adversary_coord.py` provides strategy-to-injection mapping and canonical success/detection/containment definitions.

**Coordination study results** include red-team metrics: `sec.stealth_success_rate`, `sec.time_to_attribution_steps`, `sec.blast_radius_proxy` (specimens affected before containment), in addition to `sec.attack_success_rate`, `sec.detection_latency_steps`, and `sec.containment_time_steps`. Summary CSV and Pareto report include these fields.

## Tests and acceptance

- **Determinism**: Running the suite twice with the same seed yields identical pass/fail and result count (`tests/test_security_attack_suite.py`).
- **Output contract**: `run_suite_and_emit` produces `SECURITY/attack_results.json` with version, results, and summary (`tests/test_security_attack_suite.py`).
- **Coverage and deps**: Coverage build and written files are deterministic; deps_inventory fingerprint is stable for same policy (`tests/test_securitization.py`).
- **Coordination red-team**: Success criteria consistent; strict signatures + bus replay protection block what should be blocked (`tests/test_coord_red_team_definitions.py`).

## Related

- [Evidence verification](evidence_verification.md) — verify-bundle checks and policy fingerprints.
- [Benchmarks](benchmarks.md) — TaskA–TaskH and baseline harness.
- [Paper-ready release](paper_ready.md) — paper_v0.1 profile includes SECURITY/ in the artifact.
- [CONTRACTS](CONTRACTS.md) — paper artifact contents and quickstart.
