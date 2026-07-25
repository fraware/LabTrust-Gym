# Scientific credibility program

LabTrust-Gym aims to be a **scientifically credible multi-agent laboratory workflow benchmark**: environment semantics, scenario coverage, policy boundaries, determinism, attack coverage, and release evidence must be **inspectable** and **independently reproducible**.

This document is the program overview for work packages LTG-01..LTG-09 and pull requests LTG-PR1..LTG-PR9. It does not claim clinical or deployment readiness.

## Non-goals

LabTrust-Gym does **not**:

* Provide clinical validation of laboratory software or procedures
* Act as production laboratory control software
* Constitute general medical-device certification or regulatory clearance
* Treat passing benchmark tests as evidence of real-world deployment safety
* Optimize leaderboard performance through benchmark leakage (holdouts and sealed partitions exist to resist this)

Related non-claims: [**Non-claims freeze (LTG-PR9)**](non_claims_freeze.md),
[Verifier assurance non-claims](../verifier_assurance/non_claims.md),
[Paper claims](PAPER_CLAIMS.md).

## What “credible” means here

| Property | Meaning in this repo |
|----------|----------------------|
| Environment semantics | Canonical CoreEnv state machine with transition tests |
| Scenario coverage | Golden GS-* + hazard matrix with explicit gaps |
| Policy boundaries | Versioned YAML + `labtrust validate-policy` schemas |
| Determinism | Seeded RNG; determinism report / replay contracts |
| Attack coverage | Security suite SEC-* with evidence contracts (PR5+) |
| Release evidence | Receipts, manifests, PCS / verify-release ([trust verification](../risk-and-security/trust_verification.md); LTG-PR6) |

## Definition of done (program checklist)

Honest status for packaging closure (**LTG-PR9**). “Automated” means default CI /
`tests/test_ltg_benchmark_release_dod.py`. “Human / full path” means runbook CLI
outside the smoke gate.

| DoD item | Status | How verified |
|----------|--------|--------------|
| Environment API conformance (PettingZoo / Gymnasium) | **Pass (automated subset)** | `tests/test_pz_api_conformance.py`, `tests/test_gymnasium_check_env.py`, transitions — **LTG-PR2** |
| Golden scenarios have explicit hazard mappings | **Pass** | Governance + coverage gate — **LTG-PR3** / **LTG-PR1** matrix |
| Deterministic runs reconstruct from artifacts | **Pass (API/helpers)**; full CLI reproduce **pending human pre-tag** | Reconstruction helpers + `tests/test_pcs_release_reconstruction.py` (**LTG-PR6**); full `labtrust reproduce` / `verify-release` in [release runbook](release_runbook.md) |
| Benchmark holdouts protected | **Pass (automated)** | VA-15 holdout tests / partition fixture — **LTG-PR4** |
| Release packs verify independently | **Pass (packaging + smoke)**; full pack/verify-release **pending human pre-tag** | Candidate under `benchmarks/releases/`; DoD smoke; runbook for `verify-release` — **LTG-PR6** / **LTG-PR9** |
| Independent-review process + UNSIGNED slots + fail-closed claim gate | **Pass** | **LTG-PR8**; claim remains disallowed |
| Domain reviewers complete signed approvals (three roles) | **Pending (human reviewers)** | Out-of-band recruitment; required before any “scientifically reviewed” language |
| No docs imply clinical deployment readiness | **Pass (freeze + docs)** | [Non-claims freeze](non_claims_freeze.md); this page; VA non-claims |

Checklist form:

- [x] Environment API conformance tests landed — **LTG-PR2** (run subset in CI / DoD notes)
- [x] All golden scenarios have explicit hazard mappings — **LTG-PR3**
- [x] Reconstruction provenance helpers + verify-bundle digest checks — **LTG-PR6** (full reproduce before public tag: human)
- [x] Benchmark holdouts protected — **LTG-PR4**
- [x] Engineering benchmark release packaging + DoD smoke — **LTG-PR9**
- [ ] Full pre-tag path (`reproduce`, determinism-report, official pack, verify-release) executed and recorded — **human** ([runbook](release_runbook.md))
- [x] Independent-review materials + UNSIGNED slots + fail-closed claim gate — **LTG-PR8**
- [ ] Domain reviewers complete signed approvals before “scientifically reviewed” language — **pending humans**
- [x] Non-claims freeze; no clinical deployment-readiness language in release packaging — **LTG-PR9**

## PR map (LTG-PR1 .. LTG-PR9)

| PR | Title | Primary packages |
|----|-------|------------------|
| **LTG-PR1** | State-machine and coverage inventory | LTG-02, LTG-03 (inventory) |
| **LTG-PR2** | API conformance and replay | LTG-01, LTG-04 |
| **LTG-PR3** | Golden-suite governance | LTG-03 (per-scenario metadata) |
| **LTG-PR4** | Verifier-assurance holdouts | LTG-05 |
| **LTG-PR5** | Attack-suite evidence contracts | LTG-06 |
| **LTG-PR6** | PCS release reconstruction | LTG-07 |
| **LTG-PR7** | External integrations | LTG-08 |
| **LTG-PR8** | Independent review | LTG-09 |
| **LTG-PR9** | Benchmark release | LTG-01..09 closure |

### LTG-PR1 deliverables

1. [Canonical CoreEnv state machine](../architecture/canonical_state_machine.md)
2. Transition-level tests for every `_STEP_DISPATCH` / `_STEP_DISPATCH_LATE` action (`tests/test_core_env_transitions.py`)
3. [`policy/coverage/hazard_coverage_matrix.v0.1.yaml`](../../policy/coverage/hazard_coverage_matrix.v0.1.yaml) (+ schema; wired into `validate-policy`)
4. This overview document

### LTG-PR3 deliverables

1. Per-scenario governance metadata on every golden scenario (`governance.*` in `golden_scenarios.v0.1.yaml`)
2. Fail-closed coverage gate (`validate_golden_hazard_coverage_gate`) tied to the hazard matrix
3. [Golden suite governance](golden_suite_governance.md) (change control, how to add scenarios, gap policy)
4. Schema/governance tests in default CI (`tests/test_golden_governance.py`)

### LTG-PR7 deliverables

1. Pinned public release: [`benchmarks/external_integrations/pinned_release.v1.json`](../../benchmarks/external_integrations/pinned_release.v1.json) (binds to official baselines v0.2 + VA release pack; `no_live_llm: true`)
2. Gated offline suite: `tests/test_ltg_external_integrations.py` — scripted, Gymnasium, PettingZoo, external Python agent, MARL PPO smoke, VA-13 offline PPO
3. Reconstructable evidence where applicable (`write_integration_evidence` → EvidenceBundle + `verify_bundle`)
4. Operator docs: [External integrations](../agents/external_integrations.md)

Skips cleanly when `[env]` / `[marl]` extras are missing. Default path never calls a live proprietary LLM.

### LTG-PR8 deliverables

1. [Reviewer charter](../reviews/charter.md) — three roles, scope, non-goals, COI
2. [Invitation template](../reviews/invitation_template.md) — out-of-band recruitment text
3. [Protocol and checklist](../reviews/protocol_and_checklist.md) — scenario framing, hazard coverage, non-claims
4. [Signed approval gate](../reviews/signed_approval_gate.md) — how approvals gate LTG-PR9
5. Unsigned report slots + registry: [`benchmarks/reviews/`](../../benchmarks/reviews/README.md) (`*.UNSIGNED.json`; `scientifically_reviewed_claim_allowed: false`)
6. Schemas + CI gate: `policy/schemas/independent_review_*.v1.schema.json`, `validate_independent_review_gate` (via `labtrust validate-policy`)

**Status:** process materials landed; **no signed approvals exist**. Golden scenarios remain `reviewer: pending-domain-review`. Independent review does **not** clinically validate LabTrust-Gym.

### LTG-PR9 deliverables

1. [Release runbook](release_runbook.md) — command sequence from conformance through evidence verify
2. Candidate packaging: [`benchmarks/releases/labtrust-benchmark-v0.2-candidate/`](../../benchmarks/releases/labtrust-benchmark-v0.2-candidate/) (manifest + notes; digests, pin, VA pack, known gaps)
3. [Non-claims freeze](non_claims_freeze.md) — single authoritative limitation block for release notes
4. DoD smoke: `tests/test_ltg_benchmark_release_dod.py` and `scripts/run_ltg_release_dod_smoke.py` (CI-friendly; skips heavy reproduce by default)
5. This DoD table updated for automated vs human/full-path items

**Claim posture:** ships as an **engineering benchmark** candidate.
`scientifically_reviewed_claim_allowed` remains **false**. Do not fabricate
signed reviews or set the claim flag.

**Known gaps called out in the candidate:** `catalog_drift` (hazard matrix),
UNSIGNED independent reviews, golden `reviewer: pending-domain-review`.

## Related documents

| Doc | Role |
|-----|------|
| [Canonical state machine](../architecture/canonical_state_machine.md) | CoreEnv transitions, BLOCKED contract |
| [Golden suite governance](golden_suite_governance.md) | Scenario change control and coverage gate |
| [Release runbook (LTG-PR9)](release_runbook.md) | Cut / verify engineering benchmark candidate |
| [Non-claims freeze (LTG-PR9)](non_claims_freeze.md) | Authoritative release limitation block |
| [Independent review (LTG-PR8)](../reviews/README.md) | Charter, protocol, unsigned slots, PR9 claim gate |
| [Hospital lab workflow](../architecture/hospital_lab_workflow.md) | Narrative blood-sciences flow |
| [Determinism contract](determinism_contract.md) | Replay / seed guarantees |
| [Official benchmark pack](official_benchmark_pack.md) | Pack run commands |
| [External integrations](../agents/external_integrations.md) | LTG-PR7 pinned-release adapter gate |
| [Security attack suite](../risk-and-security/security_attack_suite.md) | SEC-* attacks |
| [PCS index](../pcs/index.md) | Proof-carrying science (separate vocab) |
| [Verifier assurance](../verifier_assurance/README.md) | Dual oracle / holdouts |
| [Evaluation checklist](evaluation_checklist.md) | Operator checklist |

## Hazard coverage classes

Inspectable matrix classes (see YAML for GS-*/SEC-* mappings and **explicit gaps**):

* specimen identity
* chain of custody
* quality-control release
* critical-result escalation
* stability windows
* role authorization
* zone access
* token validity
* catalog drift
* multi-site handoff
* adversarial coordination
* insider misuse
