# Reviewer runbook

Single reference for external reviewers and auditors. It gives one command sequence, expected artifacts, and guidance for interpreting the risk register and security gate.

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

- **OutDir / out_dir** is the output directory for the bundle and, when omitted, for generated runs. The default is `risk_register_reviewer_out` under the repo root.
- **SecurityDir / security_dir**, when set, supplies SECURITY evidence; otherwise the script runs security suite smoke into `OutDir/security_smoke`.
- **CoordDir / coord_dir**, when set, supplies coordination evidence; otherwise the script runs a deterministic coordination study into `OutDir/coordination_smoke`.

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

- **Risks and controls.** Each risk from the policy registry appears with `claimed_controls` and `evidence_refs`. Controls come from the security attack suite and safety-case claims.
- **Evidence and coverage.** Evidence entries have `status` (`present` or `missing`), optional `path`, `risk_ids`, and `artifacts`. Missing evidence is first-class; the bundle includes objects with `status=missing` and `expected_sources` so reviewers can see which runs still need to be collected.
- **Coverage gaps:** Run `labtrust validate-coverage --strict` (with bundle path and policy root) to fail when required_bench cells have no evidence and are not waived. Gaps indicate which (method_id, risk_id) pairs still need evidence or a waiver in `policy/risks/waivers.v0.1.yaml`.
- **Evidence strength:** Evidence may include `evidence_strength` (e.g. high from security_suite/coordination_pack, medium from coordination_study). Use as a first-order filter; for critical risks, inspect the actual evidence (what was run, what passed).

## How to interpret the security gate

- **Security suite.** `labtrust run-security-suite` produces `SECURITY/` (`attack_results.json`, coverage, reason codes). Pass or fail is per attack scenario; the suite defines which controls are tested and how success is measured.
- **Coordination security pack.** When the run includes coordination pack output (`pack_summary.csv`, `pack_gate.md`), the pack gate summarizes pass or fail per cell (method, scale, injection). Under `summary/` expect SOTA leaderboards (`sota_leaderboard.md` / `.csv` and `sota_leaderboard_full.md` / `.csv`) and `method_class_comparison.md` / `.csv` (including `blocks_mean`, `attack_success_rate_mean`). See [How to handle security gate failures](howto_security_gate_failures.md) and [Hospital lab key metrics](../benchmarks/hospital_lab_metrics.md).
- **Reason codes.** Blocked or held actions carry reason codes (for example `RBAC_ACTION_DENY`, `SIG_MISSING`) in results and logs, showing why the engine rejected or held an action.

## See also

- [Risk register](../risk-and-security/risk_register.md) — Bundle content, generation from fixtures/release/pack, evidence semantics.
- [Risk register contract](../contracts/risk_register_contract.v0.1.md) — Schema and formal contract.
- [How to handle security gate failures](howto_security_gate_failures.md) — Interpreting security and coordination gate failures.
- [CI](ci.md) — Risk-register-gate and risk-coverage-every-pr jobs.

## Independent domain review (LTG-PR8)

This runbook covers **technical** risk-register and security-gate checks for auditors.
It is **not** the domain-review process for scenario plausibility, hazard coverage, or
non-claims language.

For independent domain review materials (charter, invitation, protocol, unsigned
approval slots, and the fail-closed gate that LTG-PR9 uses before any
“scientifically reviewed” claim):

- [Independent review index](../reviews/README.md)
- [Reviewer charter](../reviews/charter.md)
- [Protocol and checklist](../reviews/protocol_and_checklist.md)
- [Signed approval gate](../reviews/signed_approval_gate.md)
- Artifact slots: [`benchmarks/reviews/`](../../benchmarks/reviews/README.md)

**Status:** all three role slots are UNSIGNED. Passing the commands above does not
approve golden scenarios or clinically validate LabTrust-Gym. Golden scenarios keep
`governance.reviewer: pending-domain-review` until signed reports exist.
