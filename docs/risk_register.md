# Risk register

This document describes the **RiskRegisterBundle**: what it is, how to generate it from fixtures, a paper release, or an official pack run, and how to review coverage and evidence gaps. For the formal contract and schema see [Risk register contract](risk_register_contract.v0.1.md). For the dataset-driven viewer see [Risk register viewer](risk_register_viewer.md).

## What the bundle is

**RiskRegisterBundle.v0.1** is a single JSON artifact that encodes the full risk register plus evidence links so that a website (or other consumer) can render risks, controls, and evidence without parsing scattered YAML at runtime. It is **buildable from repo policy plus run outputs** and **deterministic** when policy and input run dirs are fixed.

- **Schema**: `policy/schemas/risk_register_bundle.v0.1.schema.json`
- **Output filename**: `RISK_REGISTER_BUNDLE.v0.1.json`

The bundle contains:

- **risks**: One entry per risk from `policy/risks/risk_registry.v0.1.yaml` with crosswalk fields (`risk_id`, `name`, `risk_domain`, `claimed_controls`, `evidence_refs`, `coverage_status`, etc.).
- **controls**: From the security attack suite and safety-case claims (`control_id`, `name`, `description`, `source`).
- **evidence**: Aggregated from run dirs (security suite, coordination study, safety case, official pack, bundle verification). Each entry has `evidence_id`, `type`, `status` (`present` or `missing`), optional `path`, `risk_ids`, `summary`, and `artifacts`. Run dirs that contain `pack_summary.csv`, `SECURITY/coordination_risk_matrix.csv` or `.md`, `LAB_COORDINATION_REPORT.md`, or `COORDINATION_DECISION.v0.1.json` are now scanned and these artifacts are listed as evidence (coordination_pack, lab report, coordination decision).
- **links**: Repo-local and run-local paths (policy files, SECURITY/, summary/, etc.) for deep links.
- **reproduce**: Per-evidence CLI commands so the UI can show "how to reproduce" without hardcoding.

Evidence gaps are explicit and first-class: when a risk has no evidence in the scanned runs, the bundle includes a missing-evidence object with `status=missing` and `expected_sources` so reviewers see what is not yet collected.

## How to generate the bundle

### From fixtures (CI and local smoke)

Use the committed `tests/fixtures/ui_fixtures/` run dir so the bundle is reproducible without running benchmarks:

```bash
labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures
```

The bundle is written to `./risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json`. Omit `--include-generated-at` (default) and leave the default `git_commit_hash` for provenance. CI runs the risk-register gate: generate from fixtures, validate schema, run contract gate tests (snapshot, crosswalk, coverage). See [CI](ci.md).

### From a paper release

A paper release (e.g. `package-release --profile paper_v0.1`) produces a single directory with `SECURITY/`, `SAFETY_CASE/`, `MANIFEST.v0.1.json`, baselines, and optional coordination outputs. Generate the risk register from that directory:

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper
labtrust export-risk-register --out ./risk_register_out --runs release_paper
```

Evidence in the bundle will reflect whatever is under `release_paper/` (SECURITY/attack_results.json, SAFETY_CASE/safety_case.json, MANIFEST, etc.). To include an official pack run in the same export, add `--include-official-pack <dir>`.

### From an official pack run dir

The official benchmark pack produces one output dir with baselines, SECURITY/, SAFETY_CASE/, and transparency log. When run with `--pipeline-mode llm_live`, it also writes TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json; the risk register includes these in its links when present. Use the pack output as the sole run source or in addition to other dirs:

```bash
labtrust run-official-pack --out official_pack_out --seed-base 42
labtrust export-risk-register --out ./risk_register_out --runs official_pack_out
```

Or add it alongside other runs:

```bash
labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures --include-official-pack official_pack_out
```

### Multiple run dirs and globs

You can pass several run dirs or globs. Each is scanned for SECURITY/ (including attack_results, coverage, coordination_risk_matrix), summary/, pack_summary.csv, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.v0.1.json, PARETO/, SAFETY_CASE/, MANIFEST, and evidence bundles:

```bash
labtrust export-risk-register --out ./risk_register_out \
  --runs runs/security_smoke \
  --runs runs/coord_study \
  --runs "runs/labtrust_*"
```

### Injecting the bundle for the viewer

To write the same bundle into each run dir so the viewer can load it from there (e.g. when opening a run from the UI):

```bash
labtrust export-risk-register --out ./risk_register_out --runs release_paper --inject-ui-export
```

## How to review coverage and evidence gaps

1. **Open the bundle in the viewer**  
   Open `viewer/index.html` and load `RISK_REGISTER_BUNDLE.v0.1.json` (or a zip that contains it). Use search and filters (risk_domain, applies_to, coverage_status, "has evidence") to find risks and their evidence.

2. **Check coverage status per risk**  
   Each risk has `coverage_status`: `covered`, `partially_covered`, `uncovered`, or `not_applicable`. This is derived from the method–risk matrix and which evidence is present. In the viewer, filter by "has evidence" to see which risks have at least one present evidence.

3. **Review missing evidence**  
   Evidence entries with `status=missing` list `expected_sources` (e.g. "security suite smoke", "coordination study required_bench"). Use them to see what still needs to be run or waived.

4. **Coverage gate (required_bench)**  
   Every (method_id, risk_id) cell with `required_bench: true` in the method–risk matrix must be either evidenced (at least one present evidence for that risk) or explicitly waived. The risk-register contract gate tests enforce this; the external reviewer script can run the same checks on a bundle built from your runs. Set `LABTRUST_STRICT_COVERAGE=1` to exit with failure when any required cell is missing and not waived.

5. **Crosswalk integrity**  
   The bundle must satisfy: every `risk_id` referenced in evidence exists in `risks`; every `evidence_id` in `risks[].evidence_refs` exists in `evidence`; every `control_id` in `risks[].claimed_controls` exists in `controls`. CI and the external reviewer script run these checks; failures indicate policy or build errors.

6. **Reproduce commands**  
   For each evidence item, the bundle’s `reproduce[]` (and the viewer) show CLI commands to regenerate that evidence. Use them to verify or re-run specific parts of the run set.

## External reviewer workflow

Run the dedicated script to produce a bundle from security and coordination smoke (or from provided dirs), validate schema and crosswalk, and optionally verify an evidence bundle:

```bash
./scripts/run_external_reviewer_risk_register_checks.sh [out_dir] [security_dir] [coord_dir]
```

- **out_dir**: Where to write the risk register bundle and, if not providing dirs, generated smoke runs (default: `./risk_register_reviewer_out`).
- **security_dir**: If set, use this dir for SECURITY evidence; otherwise run security suite smoke into `out_dir/security_smoke`.
- **coord_dir**: If set, use this dir for coordination evidence; otherwise run coordination study smoke into `out_dir/coordination_smoke`.

The script:

1. Runs security suite smoke and/or coordination study smoke if dirs were not provided.
2. Runs `export-risk-register` with the chosen run dir(s).
3. Validates the bundle against the schema (done by export by default).
4. Runs crosswalk integrity and, when requested, coverage checks on the written bundle; exits non-zero on failure.
5. Optionally runs `verify-bundle` on the first EvidenceBundle found under the run dirs.

See the script header for environment variables (e.g. `LABTRUST_STRICT_COVERAGE=1`). On Windows you can run the PowerShell version: `scripts/run_external_reviewer_risk_register_checks.ps1 [OutDir] [SecurityDir] [CoordDir]`. For the Bash script use WSL or ensure LF line endings (`.gitattributes` sets `*.sh text eol=lf`).

## See also

- [Risk register contract](risk_register_contract.v0.1.md) — Bundle format, fields, validation, determinism
- [Risk register viewer](risk_register_viewer.md) — Loader modes, UX, reproduce commands
- [Coordination studies](coordination_studies.md) — Coverage gate, study spec, external reviewer checks
- [Security attack suite](security_attack_suite.md) — SECURITY/ outputs and securitization packet
- [Official benchmark pack](official_benchmark_pack.md) — Pack layout and run command
- [Paper-ready release](paper_ready.md) — paper_v0.1 profile and artifact layout
- [CI](ci.md) — risk-register-gate job and contract tests
