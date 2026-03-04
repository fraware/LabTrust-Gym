# Risk register

This document describes the **RiskRegisterBundle**: what it is, how to generate it from fixtures, a paper release, or an official pack run, and how to review coverage and evidence gaps. For the formal contract and schema see [Risk register contract](../contracts/risk_register_contract.v0.1.md). For the dataset-driven viewer see [Risk register viewer](risk_register_viewer.md). **External reviewers:** See [Reviewer runbook](../operations/reviewer_runbook.md) for one command sequence, expected artifacts, and how to interpret the bundle and security gate.

## What the bundle is

**RiskRegisterBundle.v0.1** is a single JSON artifact that encodes the full risk register plus evidence links so that a website (or other consumer) can render risks, controls, and evidence without parsing scattered YAML at runtime. It is **buildable from repo policy plus run outputs** and **deterministic** when policy and input run dirs are fixed.

- **Schema**: `policy/schemas/risk_register_bundle.v0.1.schema.json`
- **Output filename**: `RISK_REGISTER_BUNDLE.v0.1.json`

The bundle contains:

- **risks**: One entry per risk from `policy/risks/risk_registry.v0.1.yaml` with crosswalk fields (`risk_id`, `name`, `risk_domain`, `claimed_controls`, `evidence_refs`, `coverage_status`, etc.).
- **controls**: From the security attack suite and safety-case claims (`control_id`, `name`, `description`, `source`).
- **evidence**: Aggregated from run dirs (security suite, coordination study, safety case, official pack, bundle verification). Each entry has `evidence_id`, `type`, `status` (`present` or `missing`), optional `path`, `risk_ids`, `summary`, and `artifacts`. Optional **evidence_strength** (`low`, `medium`, `high`) and **confidence_notes** (string) indicate reviewer-facing confidence that the evidence supports the control. evidence_strength is derived from **source type** (e.g. security_suite and coordination_pack -> high, coordination_study -> medium) as a heuristic; it is not a measure of ground-truth strength. A shallow pack run may be weaker than a deep study. Use strength as a first-order filter; for critical risks, inspect the actual evidence (what was run, what passed) rather than relying on the label alone. Optional **evidence_strength_notes** allows reviewers to record notes (e.g. "high from suite but attacks were narrow"). Run dirs that contain `pack_summary.csv`, `SECURITY/coordination_risk_matrix.csv` or `.md`, `LAB_COORDINATION_REPORT.md`, or `COORDINATION_DECISION.v0.1.json` are now scanned and these artifacts are listed as evidence (coordination_pack, lab report, coordination decision).
- **links**: Repo-local and run-local paths (policy files, SECURITY/, summary/, etc.) for deep links.
- **reproduce**: Per-evidence CLI commands so the UI can show "how to reproduce" without hardcoding.
- **evidence_level** (optional): When run dirs were provided, the bundle may include `evidence_level`: `deterministic_only` or `with_live_llm`. Reviewers can use it to see whether validate-coverage passed with deterministic evidence only or with live LLM (LLM attacker or llm_live pack runs).

Evidence gaps are explicit and first-class: when a risk has no evidence in the scanned runs, the bundle includes a missing-evidence object with `status=missing` and `expected_sources` so reviewers see what is not yet collected.

**Evidence semantics:** Required_bench evidence means "we ran the designated injection for this (method, risk)." It is a **necessary** condition for coverage, not sufficient. Effectiveness of the control for that risk in general depends on injection design, success criteria, and threat model. Each (method_id, risk_id) to injection mapping should be reviewed (e.g. "Does this injection actually stress this risk? Are success criteria strict enough?"). See [Risk register contract](../contracts/risk_register_contract.v0.1.md).

## How to generate the bundle

### From fixtures (CI and local smoke)

Use the committed fixtures so the bundle is reproducible without running benchmarks:

- **Contract gate (snapshot, crosswalk):** `tests/fixtures/ui_fixtures` only.
- **Coverage gate (validate-coverage --strict):** Run dirs are defined in `scripts/risk_coverage_fixture_dirs.py` (currently `tests/fixtures/ui_fixtures` and `tests/fixtures/coord_pack_fixture_minimal`). The minimal fixture contains only `pack_summary.csv`; the bundle builder marks that coordination_pack evidence as **synthetic: true**. No waivers are used for fixture-based validation.

```bash
# Contract gate (ui_fixtures only)
labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures

# Coverage gate (same as CI)
labtrust export-risk-register --out ./risk_register_out $(python scripts/risk_coverage_fixture_dirs.py)
```

The bundle is written to `./risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json`. CI runs **risk-register-gate** (ui_fixtures only, then contract tests) and **risk-coverage-every-pr** (fixture dirs from script, then validate-coverage --strict). See [CI](../operations/ci.md).

### From a paper release

A paper release (e.g. `package-release --profile paper_v0.1`) produces a single directory with `SECURITY/`, `SAFETY_CASE/`, `MANIFEST.v0.1.json`, baselines, and optional coordination outputs. Generate the risk register from that directory:

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper
labtrust export-risk-register --out ./risk_register_out --runs release_paper
```

Evidence in the bundle will reflect whatever is under `release_paper/` (SECURITY/attack_results.json, SAFETY_CASE/safety_case.json, MANIFEST, etc.). To include an official pack run in the same export, add `--include-official-pack <dir>`.

### Required-bench coverage pack (deterministic)

To produce a single deterministic run set that satisfies every required_bench cell (or waivers) and passes `validate-coverage --strict`:

```bash
./scripts/run_required_bench_matrix.sh --out runs/required_bench_pack
# Windows: .\scripts\run_required_bench_matrix.ps1 -OutDir runs\required_bench_pack
```

The script runs security suite (smoke) and coordination security pack, then `export-risk-register` and `validate-coverage --strict`. The resulting folder can be fed into verify-release when packaged (e.g. as part of paper_v0.1 or a dedicated coverage pack profile). Coverage is a build product: when using the required_bench matrix output, all cells are evidenced (or waivers in `policy/risks/waivers.v0.1.yaml` with expiry). Required_bench evidence is necessary but not sufficient for assurance; effectiveness depends on injection design and success criteria. For CI fixture-based validation, waivers are not used; see `scripts/risk_coverage_fixture_dirs.py`. See `policy/coordination/method_risk_matrix.v0.1.yaml` for required_bench cells.

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

   **Waivers:** `policy/risks/waivers.v0.1.yaml` lists cells that may be missing evidence with an expiry and optional signer. When you run `labtrust validate-coverage --strict`, the loader reads this file and treats non-expired entries as waived; expired waivers are ignored and the cell must be evidenced. **Current state:** The file is kept as `waivers: []` for the fixture-based CI path; CI does not use waivers when validating the bundle built from ui_fixtures + coord_pack_fixture_minimal. See `load_waivers()` in `src/labtrust_gym/export/risk_register_bundle.py`.

5. **Crosswalk integrity**  
   The bundle must satisfy: every `risk_id` referenced in evidence exists in `risks`; every `evidence_id` in `risks[].evidence_refs` exists in `evidence`; every `control_id` in `risks[].claimed_controls` exists in `controls`. CI and the external reviewer script run these checks; failures indicate policy or build errors.

6. **Reproduce commands**  
   For each evidence item, the bundle’s `reproduce[]` (and the viewer) show CLI commands to regenerate that evidence. Use them to verify or re-run specific parts of the run set.

## Risk-to-attack coverage

Which risks are directly covered by the attack suite or coordination pack, and which are waived or partially covered. Every risk_id from `policy/risks/risk_registry.v0.1.yaml` appears below. Waiver: reference to `policy/risks/waivers.v0.1.yaml` when a required_bench cell is intentionally not evidenced (expiry + rationale).

| risk_id | Name | Attack coverage | Gate expectation | Waiver |
|---------|------|-----------------|------------------|--------|
| R-CAP-001 | Jailbreak attacks | Suite: SEC-PI-*, SEC-LLM-ATTACK-*; pack: INJ-COORD-PROMPT-INJECT-001, INJ-LLM-PROMPT-INJECT-COORD-001 | attack_success_rate 0; blocked/detected | — |
| R-TOOL-006 | Tool vulnerability exploitation | Suite: SEC-TOOL-001, SEC-TOOL-002, SEC-TOOL-003 (test_tool_sandbox: egress/caps, unregistered tool denied) | blocked | — |
| R-COMMS-001 | Identity spoofing | Suite: SEC-COORD-001, SEC-COORD-RT-001; pack: INJ-ID-SPOOF-001, INJ-COORD-PLAN-REPLAY-001 | attack_success_rate 0 | — |
| R-COMMS-002 | Communication poisoning | Suite: SEC-DETECTOR-001, SEC-COMMS-001; pack: INJ-COMMS-POISON-001, inj_msg_poison | attack_success_rate 0 or detection within steps | — |
| R-DATA-003 | Memory poisoning | Suite: SEC-MEM-001; pack: INJ-MEMORY-POISON-COORD-001, INJ-MEMORY-POISON-001 | blocked | — |
| R-DATA-001 | Untrusted data exchange | Suite: SEC-OBS-001, SEC-DATA-PROV-001; pack: INJ-COMMS-POISON-001 | evidenced via observability + provenance | — |
| R-SYS-002 | Agent collusion | Suite: SEC-COORD-RT-002; pack: INJ-COLLUSION-001, INJ-COORD-BID-SHILL-001 | attack_success_rate 0 or blocked | — |
| R-TOOL-001 | Tool selection errors | Suite: SEC-TOOL-SELECT-001 (test_tool_selection_wrong_tool_blocked_by_registry); pack: inj_tool_selection_noise (ToolSelectionNoiseInjector) | blocked | — |
| R-TOOL-002 | Tool execution failure | Suite: SEC-TOOL-EXECFAIL-001 (test_tool_execution_failure); pack: inj_device_fail | blocked | — |
| R-TOOL-003 | Unverified tool risk | Suite: SEC-TOOL-UNVERIFIED-001 (test_unregistered_tool_denied; pre-action validation evidenced) | blocked | — |
| R-TOOL-004 | Tool misuse risk | Suite: SEC-TOOL-MISUSE-001; pack: INJ-TOOL-MISUSE-001 | blocked | — |
| R-TOOL-005 | Function call misparameterization | Suite: SEC-TOOL-MISPARAM-001, SEC-TOOL-MISPARAM-FUZZ-001; pack: INJ-TOOL-MISPARAM-001 | blocked | — |
| R-DATA-002 | Data poisoning (train/run-time) | No suite attack; pack: inj_poison_obs (marl_ppo required_bench) | Evidenced via coord_risk where required_bench | — |
| R-SYS-001 | Agent denial of service | No suite attack; pack: INJ-DOS-PLANNER-001 in required_bench_plan | Evidenced via coord_risk cells | — |
| R-FLOW-001 | Action inefficiency | Suite: SEC-FLOW-INEF-001 | detected | — |
| R-FLOW-002 | Action progress risk | Suite: SEC-FLOW-PROGRESS-001 | detected | — |

Risks without a direct suite attack_id (R-TOOL-001–005, R-DATA-002, R-SYS-001, R-FLOW-*) are either covered by the coordination pack via required_bench_plan (method_id + injection_id), by waivers in `policy/risks/waivers.v0.1.yaml` with expiry and rationale, or marked out of scope for the current suite. Run `labtrust validate-coverage --strict` after producing evidence (e.g. via `run_required_bench_matrix.sh`) to confirm all required cells are evidenced or waived. **Waivers:** For any required_bench (method_id, risk_id) cell that is intentionally not evidenced, add an entry to `policy/risks/waivers.v0.1.yaml` with `risk_id`, `method_id`, `why`, `expires_on` (YYYY-MM-DD), and optional `approved_by` so strict coverage validation passes.

**Future work (planned attacks):** R-TOOL-003 is evidenced by SEC-TOOL-UNVERIFIED-001 (unverified tool call denied via test_unregistered_tool_denied). Other risks may get additional attack_ids as the suite expands.

## Reserved and legacy injection IDs (out of scope for this release)

Four injection IDs remain **reserved** and are registered as **NoOpInjector** (passthrough) so that runs and the risk register do not fail when referenced. All other IDs listed below (including former reserved `inj_prompt_injection`, `inj_misparam_device`, and `inj_collusion_handoff`) are implemented as real injectors. For active fault injection use **INJ-*** IDs from `policy/coordination/injections.v0.2.yaml` (e.g. INJ-COMMS-POISON-001, INJ-COLLUSION-001, INJ-COORD-PROMPT-INJECT-001).

**Reserved no-op IDs (4):** `none` (no-op baseline for coordination security pack), `inj_untrusted_payload`, `inj_stuck_state`, `inj_jailbreak`. **Implemented as real injectors (including former reserved):** `inj_prompt_injection` (PromptInjectionObsInjector; injects into scenario_note/specimen_note), `inj_misparam_device` (MisparamDeviceInjector; perturbs device-related action args), `inj_collusion_handoff` (CollusionHandoffInjector; duplicates handoff messages to stress detection), `inj_tool_selection_noise` (ToolSelectionNoiseInjector), `inj_device_fail` (DeviceFailInjector), `inj_msg_poison` (MsgPoisonInjector), `inj_dos_flood` (DosFloodInjector), `inj_memory_tamper` (MemoryTamperInjector), `inj_poison_obs` (PoisonObsInjector). See [Risk injections (extension contract)](risk_injections.md) and `RESERVED_NOOP_INJECTION_IDS` in `src/labtrust_gym/security/risk_injections.py`. Coordination security pack config supports **disallow_reserved_injections** so strict packs can forbid use of reserved (no-op) IDs.

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

- [Risk register contract](../contracts/risk_register_contract.v0.1.md) — Bundle format, fields, validation, determinism
- [Risk register viewer](risk_register_viewer.md) — Loader modes, UX, reproduce commands
- [Risk injections (extension contract)](risk_injections.md) — How to implement and register injectors; reserved IDs
- [Coordination studies](../coordination/coordination_studies.md) — Coverage gate, study spec, external reviewer checks
- [Security attack suite](security_attack_suite.md) — SECURITY/ outputs and securitization packet
- [Official benchmark pack](../benchmarks/official_benchmark_pack.md) — Pack layout and run command
- [Paper provenance](../benchmarks/paper/README.md) — paper_v0.1 profile and artifact layout
- [CI](../operations/ci.md) — risk-register-gate job, risk-coverage-strict job (schedule/manual), and contract tests
