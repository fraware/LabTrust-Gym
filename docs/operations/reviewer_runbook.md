# Reviewer runbook

Single reference for external reviewers and auditors: one command sequence, expected artifacts, and how to interpret the risk register and security gate.

## One command sequence

From the repo root, run the external reviewer risk register checks script. This runs security suite smoke, coordination study smoke (or uses provided run dirs), exports the risk register, validates schema and crosswalk, and optionally runs verify-bundle on one evidence bundle.

**Windows (PowerShell):**

```powershell
.\scripts\run_external_reviewer_risk_register_checks.ps1 [OutDir] [SecurityDir] [CoordDir]
```

**Linux / macOS (Bash):**

```bash
bash scripts/run_external_reviewer_risk_register_checks.sh [out_dir] [security_dir] [coord_dir]
```

- **OutDir / out_dir:** Output directory for the bundle and, if not provided, generated runs. Default: `risk_register_reviewer_out` (under repo root).
- **SecurityDir / security_dir:** If set, use this directory for SECURITY evidence; otherwise the script runs security suite smoke into `OutDir/security_smoke`.
- **CoordDir / coord_dir:** If set, use this directory for coordination evidence; otherwise the script runs coordination study (deterministic) into `OutDir/coordination_smoke`.

**Optional:** Set `LABTRUST_STRICT_COVERAGE=1` to exit with code 1 when any required_bench (method, risk) cell has no evidence and is not waived.

**Manual equivalent:** (1) Run security suite smoke: `labtrust run-security-suite --out <dir> --seed 42`. (2) Run coordination study smoke: `labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out <dir> --llm-backend deterministic` (with `LABTRUST_REPRO_SMOKE=1`). (3) Verify run evidence: `python scripts/verify_run_evidence.py --policy-root <repo_root> <run_dirs>`. (4) Export risk register: `labtrust export-risk-register --out <out_dir> --runs <run_dir1> --runs <run_dir2> ...`. (5) Validate bundle schema and crosswalk (see script for inline Python). (6) Optionally run `labtrust verify-bundle --bundle <EvidenceBundle_dir>` on one bundle.

## Expected artifacts

| Path | Description |
|------|-------------|
| `RISK_REGISTER_BUNDLE.v0.1.json` | Risk register bundle: risks, controls, evidence refs, coverage status, links, reproduce commands. Written under the output directory (e.g. `risk_register_reviewer_out/`). |
| `risk_register_reviewer_out/security_smoke/` | Security suite smoke output (if not provided): SECURITY/ (attack_results.json, coverage, etc.). |
| `risk_register_reviewer_out/coordination_smoke/` | Coordination study smoke output (if not provided): `summary/summary_coord.csv`, etc. |
| EvidenceBundle dirs | When run dirs contain receipt exports (e.g. from package-release), `verify-bundle` is run on one such bundle; the script locates it under the run dirs. |

See [Risk register](../risk-and-security/risk_register.md) for bundle structure and [Risk register contract](../contracts/risk_register_contract.v0.1.md) for the schema.

## How to interpret the risk register bundle

- **Risks and controls:** Each risk from the policy registry appears with `claimed_controls` and `evidence_refs`. Controls are from the security attack suite and safety-case claims.
- **Evidence and coverage:** Evidence entries have `status` (`present` or `missing`), optional `path`, `risk_ids`, and `artifacts`. Missing evidence is first-class: the bundle includes objects with `status=missing` and `expected_sources` so reviewers see what has not been collected.
- **Coverage gaps:** Run `labtrust validate-coverage --strict` (with bundle path and policy root) to fail when required_bench cells have no evidence and are not waived. Gaps indicate which (method_id, risk_id) pairs still need evidence or a waiver in `policy/risks/waivers.v0.1.yaml`.
- **Evidence strength:** Evidence may include `evidence_strength` (e.g. high from security_suite/coordination_pack, medium from coordination_study). Use as a first-order filter; for critical risks, inspect the actual evidence (what was run, what passed).

## How to interpret the security gate

- **Security suite:** `labtrust run-security-suite` produces SECURITY/ (attack_results.json, coverage, reason codes). Pass/fail is per attack scenario; the suite defines which controls are tested and how success is measured.
- **Coordination security pack:** When the run includes coordination pack output (pack_summary.csv, pack_gate.md), the pack gate summarizes pass/fail per cell (method, scale, injection). See [How to handle security gate failures](howto_security_gate_failures.md).
- **Reason codes:** Blocked or held actions carry reason codes (e.g. RBAC_ACTION_DENY, SIG_MISSING); these appear in results and logs and indicate why an action was not applied.

## See also

- [Risk register](../risk-and-security/risk_register.md) — Bundle content, generation from fixtures/release/pack, evidence semantics.
- [Risk register contract](../contracts/risk_register_contract.v0.1.md) — Schema and formal contract.
- [How to handle security gate failures](howto_security_gate_failures.md) — Interpreting security and coordination gate failures.
- [CI](ci.md) — Risk-register-gate and risk-coverage-every-pr jobs.
