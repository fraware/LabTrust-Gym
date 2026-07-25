# Trust verification

This page is the single place for the trust story. It lists what we run to prove consistency and what each artifact attests. Every verification step and every security or safety artifact below includes what it proves and how to run or inspect it.

## Verification chain (E2E)

The main trust proof is the four-step E2E chain. **Pass** means the artifact is internally consistent and policy-fingerprinted.

| Step | What it attests | How to run |
|------|-----------------|------------|
| 1. package-release (minimal) | Reproducible run plus EvidenceBundles and MANIFEST; ENV/ with deps and git provenance | `labtrust package-release --profile minimal --seed-base 100 --out <work_dir>/release` |
| 2. export-risk-register | Risk register bundle built from policy and run dirs; evidence and gaps in one artifact | `labtrust export-risk-register --out <work_dir>/release --runs <work_dir>/release` |
| 3. build-release-manifest | RELEASE_MANIFEST.v0.1.json with hashes of MANIFEST, all evidence bundles, risk register bundle, and aggregated reconstruction provenance | `labtrust build-release-manifest --release-dir <work_dir>/release` |
| 4. verify-release | Every EvidenceBundle.v0.1 (including reconstruction digests when present), risk register schema and crosswalk, and RELEASE_MANIFEST hashes validated; all offline | `labtrust verify-release --release-dir <work_dir>/release --strict-fingerprints` |

**Full chain (Unix/macOS):** `make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh`. See [Frozen contracts](../contracts/frozen_contracts.md) and [CI](../operations/ci.md).

## PCS release reconstruction chain (LTG-PR6)

Independent reconstruction and verification of a release pack (no live LLM) follows this CLI order:

```bash
labtrust export-receipts --run <episode.jsonl> --out <receipts_dir>
labtrust verify-bundle --bundle <receipts_dir>/EvidenceBundle.v0.1
labtrust build-release-manifest --release-dir <release_dir>
labtrust verify-release --release-dir <release_dir> --strict-fingerprints
labtrust run-official-pack --out <pack_dir> --smoke   # optional: --include-coordination-pack
```

Trajectory replay (LTG-PR2) strengthens the same contract: digests written into EvidenceBundle `reconstruction` are the same functions used by `labtrust replay-trajectory` (`canonical_episode_log_digest`, `evidence_digest`).

### Reconstruction field checklist

Every new EvidenceBundle manifest, `pack_manifest.json`, and `RELEASE_MANIFEST.v0.1.json` carries or links to:

| Field | EvidenceBundle | pack_manifest | RELEASE_MANIFEST |
|-------|----------------|---------------|------------------|
| Policy digest | `reconstruction.policy_digest` (= `policy_fingerprint`) | `reconstruction.policy_digest` | aggregated `policy_digest(s)` |
| Environment digest | `reconstruction.environment_digest` | same | aggregated |
| Agent identity | `reconstruction.agent_identity` | `agent_identities` from baselines | aggregated |
| Seed | `reconstruction.seed` | `seed` / `seed_base` | aggregated `seed(s)` |
| Scenario IDs | `reconstruction.scenario_ids` | tasks as scenario IDs | aggregated |
| Episode-log digests | `reconstruction.episode_log_digest` (+ PR2 replay) | listed when bundles present | `episode_log_digests[]` |
| Risk-register refs | `risk_register_refs` | refs when bundle present | `RISK_REGISTER_BUNDLE.v0.1.json` |
| Verification results | offline commands / report refs | same | commands + `verify_report.txt` refs |
| Missing-evidence declarations | usually `[]` on a single bundle | usually `[]` | from risk register `status=missing` |

Schemas: `policy/schemas/evidence_bundle_manifest.v0.1.schema.json`, `pack_manifest.v0.1.schema.json`, `release_manifest.v0.1.schema.json`.

Legacy fixtures without a `reconstruction` block still verify (digests are checked only when present). New exports always write the block.

## Evidence bundles and verify-bundle

Every run can produce **EvidenceBundle.v0.1** (via `export-receipts` from episode logs). The bundle contains manifest, schema, hashchain, and invariant trace.

When verification passes, the run is consistent and auditable, and the hashchain and manifest tie the run to policy and step events.

- **Single bundle.** Run `labtrust verify-bundle --bundle <path>` where `<path>` is a directory that contains `manifest.json` (for example under `receipts/<task>_cond_<n>/EvidenceBundle.v0.1`). Use `--strict-fingerprints` for release validation. When `reconstruction.episode_log_digest` / `evidence_digest` are present, verify-bundle recomputes them from `episode_log_subset.jsonl` (same contract as trajectory replay).
- **Full release.** Run `labtrust verify-release --release-dir <dir> --strict-fingerprints` to verify every EvidenceBundle in the release.

Run `verify-bundle` or `verify-release` as the trust primitive; a passing result means the run is consistent and auditable.

### Evidence integrity

Before treating any run as evidence (e.g. for risk register coverage or release):

1. **Evidence bundles must pass** `labtrust verify-bundle` (or `verify-release` for a full release). CI and release scripts run verification and fail the pipeline if it does not pass.
2. **Artifacts must not be edited after generation.** Files such as `SECURITY/attack_results.json`, `pack_summary.csv`, `pack_gate.md`, and receipt manifests are tied to hashes and schema. Replacing or editing them invalidates the evidence chain; verification will fail if hashes or schema are checked.
3. When uncertain, re-run the producing command (for example `run-security-suite` or `run-coordination-security-pack`) before editing outputs.

## Risk register and coverage

The risk register bundle plus `validate-coverage --strict` is the trust story for safety: every required risk is either evidenced (by benchmarks, security pack, or studies) or explicitly waived.

A passing coverage gate shows that every required risk is evidenced or explicitly waived.

- Build the bundle with `labtrust export-risk-register --out <dir> --runs <dir>`.
- Validate with `labtrust validate-coverage --bundle <path> --strict` (exit code 1 when any required risk lacks evidence and has no waiver).

CI can run `validate-coverage --strict` as a gate. See [Risk register](risk_register.md) and [Gate and required bench](gate_and_required_bench.md).

## Security and safety artifacts (which artifact answers which concern)

**Reproduce commands** are the primary way to reproduce evidence (e.g. `labtrust run-security-suite --out <dir> --smoke --seed 42`). **Tests** (pytest paths) are supporting: they are what the suite or pipeline runs to produce the artifact; the artifact itself is produced by the CLI command.

| Concern | What it proves | How to run or inspect |
|---------|----------------|------|
| **Adversarial behavior** | Security attack suite: attack success, detection, containment | Run: `labtrust run-security-suite --out <dir>`. Inspect: `<dir>/SECURITY/attack_results.json`, securitization packet. |
| **Coordination under attack** | Coordination security pack: method × scale × injection outcomes and gate verdicts | Run: `labtrust run-coordination-security-pack --out <dir>`. Inspect: `pack_gate.md`, `pack_summary.csv`. |
| **Prompt injection** | Policy and golden scenarios for pre-LLM block and output consistency | Policy under `policy/security/`; golden: `policy/golden/prompt_injection_scenarios.v0.1.yaml`. See [Prompt-injection defense](prompt_injection_defense.md) for tests and commands. |
| **Safety claims** | Safety case: claim → control → reproduce command → artifact. The "tests" in the safety case are the underlying pytest or components that the command runs. Claims may include `artifacts_expected` and, when built from a release dir, `artifact_sha256` for machine-checkable evidence links. | Run: `labtrust safety-case --out <dir>`. Inspect: `<dir>/SAFETY_CASE/safety_case.json`, `safety_case.md`. |

See [Security attack suite](security_attack_suite.md), [Prompt-injection defense](prompt_injection_defense.md), and [Risk register](risk_register.md).

### Safety case and SMT

The safety case links each claim to a control, test, artifact, and command. Optional SMT checks in code (`run_smt_checks` in `safety_case.py`) run trivial structural validation (for example that `claim_id` is present) when z3 is installed; they validate structure only, not logical implications between claims and controls. Formal implication checks (for example claim C implies control X) are reserved for future use.

## Determinism and reproducibility

Determinism and reproducibility support the claim that the same inputs yield the same outputs.

- **determinism-report** produces `determinism_report.md` and `determinism_report.json` with run config and hash comparison, and asserts v0.2 metrics and episode log hash are identical across two runs. Run `labtrust determinism-report --task throughput_sla --episodes 2 --seed 42 --out <dir>`.
- **replay-trajectory** re-executes a recorded run or compares two episode logs under the exact-match digest contract used by EvidenceBundle reconstruction. Run `labtrust replay-trajectory --help`.
- **reproduce** rebuilds minimal or full study results and figures (sweep plus plots). Run `labtrust reproduce --profile minimal` or `labtrust reproduce --profile full`.

Seeds, commands, and figure/table paths are documented in [Paper provenance](../benchmarks/paper/README.md). **Trustworthiness includes same inputs → same outputs.**
