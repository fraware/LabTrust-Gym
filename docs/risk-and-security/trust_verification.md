# Trust verification

This page is the single place for the trust story: what we run to prove consistency and what each artifact proves. Every verification step and every security/safety artifact below has both (1) **what it proves** and (2) **how to run or inspect it**.

## Verification chain (E2E)

The main trust proof is the four-step E2E chain. **Pass** means the artifact is internally consistent and policy-fingerprinted.

| Step | What it attests | How to run |
|------|-----------------|------------|
| 1. package-release (minimal) | Reproducible run plus EvidenceBundles and MANIFEST; ENV/ with deps and git provenance | `labtrust package-release --profile minimal --seed-base 100 --out <work_dir>/release` |
| 2. export-risk-register | Risk register bundle built from policy and run dirs; evidence and gaps in one artifact | `labtrust export-risk-register --out <work_dir>/release --runs <work_dir>/release` |
| 3. build-release-manifest | RELEASE_MANIFEST.v0.1.json with hashes of MANIFEST, all evidence bundles, and risk register bundle | `labtrust build-release-manifest --release-dir <work_dir>/release` |
| 4. verify-release | Every EvidenceBundle.v0.1, risk register schema and crosswalk, and RELEASE_MANIFEST hashes validated; all offline | `labtrust verify-release --release-dir <work_dir>/release --strict-fingerprints` |

**Full chain (Unix/macOS):** `make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh`. See [Release checklist](../operations/release_checklist.md) and [Frozen contracts](../contracts/frozen_contracts.md).

## Evidence bundles and verify-bundle

Every run can produce **EvidenceBundle.v0.1** (via `export-receipts` from episode logs). The bundle contains manifest, schema, hashchain, and invariant trace.

- **What it proves:** If verification passes, the run is consistent and auditable; the hashchain and manifest tie the run to policy and step events.
- **How to run (single bundle):** `labtrust verify-bundle --bundle <path>` where `<path>` is a directory that contains `manifest.json` (e.g. under `receipts/<task>_cond_<n>/EvidenceBundle.v0.1`). Use `--strict-fingerprints` for release validation.
- **How to run (full release):** `labtrust verify-release --release-dir <dir> --strict-fingerprints` runs verify-bundle over every EvidenceBundle in the release.

**Trust primitive:** Run verify-bundle or verify-release; if it passes, the run is consistent and auditable.

## Risk register and coverage

The risk register bundle plus `validate-coverage --strict` is the trust story for safety: every required risk is either evidenced (by benchmarks, security pack, or studies) or explicitly waived.

- **What it proves:** We know what we claim to mitigate and we evidence or waive it. No un-evidenced required risk when the gate passes.
- **How to run:** `labtrust export-risk-register --out <dir> --runs <dir>` to build the bundle; `labtrust validate-coverage --bundle <path> --strict` to validate (exit 1 if any required risk has missing evidence and is not waived).

CI can run `validate-coverage --strict` as a gate. See [Risk register](risk_register.md) and [Gate and required bench](gate_and_required_bench.md).

## Security and safety artifacts (which artifact answers which concern)

| Concern | What it proves | How to run or inspect |
|---------|----------------|----------------------|
| **Adversarial behavior** | Security attack suite: attack success, detection, containment | Run: `labtrust run-security-suite --out <dir>`. Inspect: `<dir>/SECURITY/attack_results.json`, securitization packet. |
| **Coordination under attack** | Coordination security pack: method × scale × injection outcomes and gate verdicts | Run: `labtrust run-coordination-security-pack --out <dir>`. Inspect: `pack_gate.md`, `pack_summary.csv`. |
| **Prompt injection** | Policy and golden scenarios for pre-LLM block and output consistency | Policy under `policy/security/`; golden: `policy/golden/prompt_injection_scenarios.v0.1.yaml`. See [Prompt-injection defense](prompt_injection_defense.md) for tests and commands. |
| **Safety claims** | Safety case: claim → control → test → artifact | Run: `labtrust safety-case --out <dir>`. Inspect: `<dir>/SAFETY_CASE/safety_case.json`, `safety_case.md`. |

See [Security attack suite](security_attack_suite.md), [Prompt-injection defense](prompt_injection_defense.md), and [Risk register](risk_register.md).

## Determinism and reproducibility

Determinism and reproducibility support the claim that the same inputs yield the same outputs.

- **determinism-report:** Produces `determinism_report.md` and `determinism_report.json` with run config and hash comparison; asserts v0.2 metrics and episode log hash identical across two runs.
  - **How to run:** `labtrust determinism-report --task throughput_sla --episodes 2 --seed 42 --out <dir>`
- **reproduce:** Reproduces minimal or full study results and figures (sweep + plots).
  - **How to run:** `labtrust reproduce --profile minimal` or `labtrust reproduce --profile full`

Seeds, commands, and figure/table paths are documented in [Paper provenance](../benchmarks/paper/README.md). **Trustworthiness includes same inputs → same outputs.**
