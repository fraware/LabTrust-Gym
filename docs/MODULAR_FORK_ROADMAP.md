# Modular Fork Roadmap: Reusable Platform and Hospital Lab Core

This document lays out the remaining steps to (1) capture and fix remaining repo errors, (2) make the repo modular and forkable so different organizations can run their own cyber-physical workflows and coordination benchmarks, and (3) preserve the hospital lab / HSL design as the reference core. It is a design and implementation roadmap, not a specification freeze.

---

## 1. Capturing remaining errors

### 1.1 Fixed in this pass

- **Risk register evidence type:** The bundle export used `type: "coordination_pack"` for pack run evidence, but the schema enum did not include it. **Done:** `policy/schemas/risk_register_bundle.v0.1.schema.json` now includes `"coordination_pack"` in the evidence `type` enum.
- **Risk register snapshot:** The contract gate snapshot `tests/fixtures/risk_register_bundle_ui_fixtures.v0.1.json` had drifted (new controls/evidence). **Done:** Snapshot regenerated from `ui_fixtures` with the same script referenced in the test (build_risk_register_bundle with include_generated_at=False, include_git_hash=False).

### 1.2 Remaining gaps (from STATUS implementation audit and STATUS)

| Gap | Priority | Action |
|-----|----------|--------|
| No automated E2E run with real LLM (non-empty model/latency/cost in artifacts) | Low | Optional CI job when API key set; already partially covered by llm_live_optional_smoke.yml. |
| Phase 2A (determinism-report, LABTRUST_RUN_GOLDEN golden suite) not in same CI context as pack changes | Medium | Add optional job or block pack-related PRs on a job that runs determinism-report and golden suite. |
| E2E artifacts chain (package-release -> verify-release -> export-risk-register) | Done | e2e-artifacts-chain.yml runs verify-release (all EvidenceBundles); make target and workflow run on PR/schedule/dispatch. |
| Document audit and bar in README/CONTRIBUTING | Low | Add a short "Testing and contracts" subsection pointing to STATUS (implementation audit) and frozen_contracts. |

### 1.3 Suggested next checks

- Run full test suite and fix any other failing tests (e.g. environment-dependent or flaky).
- Run `labtrust validate-policy` and fix any policy/schema drift.
- Run `make e2e-artifacts-chain` (or equivalent) and confirm it passes.
- Optionally: add a single CI job that runs risk-register-gate + coordination contract gate + one coordination-security-pack smoke so PRs cannot merge with contract or pack breakage.

---

## 2. Modular repo and forkability: goals

Goals for organizations that fork the repo:

1. **Design their cyber-physical workflows** within the same trust and coordination model (or a policy-restricted subset).
2. **Run coordination at scale** using the same tasks (coord_scale/coord_risk), scale configs, and coordination methods.
3. **Report on benchmarks** (summarize-coordination, SOTA leaderboard, method-class comparison).
4. **Run the security and safety suite** (run-coordination-security-pack, run-security-suite, safety-case) and get a risk register.
5. **Determine the best coordination technique at scale** for their organization via recommend-coordination-method and build-lab-coordination-report.

The codebase should stay **modular** and the **end-to-end pipeline** (validate -> run matrix -> summarize -> recommend -> report -> risk register) should work for a forking organization with minimal changes. The **hospital lab / HSL** design remains the **reference core**: default policy, default tasks, and default partner overlay.

---

## 3. Current extensibility vs target

### 3.1 What is already reusable (no fork required)

- **Pipeline commands:** All of the following work with the in-repo policy and tasks: `validate-policy`, `run-benchmark`, `run-coordination-study`, `run-coordination-security-pack`, `summarize-coordination`, `recommend-coordination-method`, `build-lab-coordination-report`, `build-coordination-matrix`, `run-security-suite`, `run-official-pack`, `export-risk-register`, `package-release`. A forker can run these as-is on the hospital lab core.
- **Partner overlays:** Policy overlays (e.g. `hsl_like`) allow different critical thresholds, stability, enforcement without changing engine code. A forker can add a new partner in `policy/partners/` and use `--partner <id>`.
- **Policy as data:** Coordination methods, scale configs, study specs, injections, security attack suite, and risk registry are YAML/JSON under `policy/`. Forkers can add or tune methods, scales, and injections within the existing schemas.
- **Coordination interface:** New coordination methods are registered in `coordination_methods.v0.1.yaml` and implement the same interface (reset, propose_actions); the benchmark and study runners are method-agnostic.

### 3.2 Where the repo is still domain-tight

- **Engine and tasks are hospital-lab specific:** The engine action set (specimens, QC, critical, queue, zones, devices, transport) and the task initial_state generators (specimens, panels, zones, devices) are tailored to the lab. There is no first-class "workflow type" or "domain adapter" that would allow a different sector (e.g. warehouse, factory) to plug in a different semantics without touching core_env or tasks.
- **Default policy and vocabulary:** Emits, reason codes, zones, equipment, and catalogue are lab-oriented. A forker can replace or overlay policy but must keep schema compliance and runner output contract.

### 3.3 Target balance: platform vs reference core

- **Keep the core:** Hospital lab (and HSL-like partner) remain the default and primary use case. Default tasks (throughput_sla through coord_risk), default policy tree, and default partner `hsl_like` stay in the main repo and drive the golden suite and frozen contracts.
- **Enable forkability without a big refactor:** Forking organizations can:
  - **Path A (policy + partner only):** Use the same engine and tasks; add a new partner overlay and optionally new scale configs / coordination methods / injections. Run the same pipeline (pack -> report -> risk register). Best when their workflow is "lab-like" (resources, queues, zones, devices).
  - **Path B (policy + custom tasks):** Fork, add a new partner and new task definitions (new initial_state generators and episode lengths) in `benchmarks/tasks.py` and register them in the benchmark runner. Keep the same action set and runner output contract so coordination and security pipeline stay unchanged. Requires code change in one place (tasks).
  - **Path C (future, larger):** Introduce a "domain adapter" or "workflow spec" that maps abstract resources and locations to engine actions and state, with the hospital lab as one implementation. This would allow a second domain (e.g. warehouse) without forking engine logic. Not required for the immediate balance; document as a future option.

---

## 4. Remaining steps for a modular, end-to-end, forkable design

### 4.1 Documentation (high impact, low code change)

1. **Forker guide:** See [Forker guide](FORKER_GUIDE.md) for:
   - How to fork and run the full pipeline (validate-policy, run-coordination-security-pack, build-lab-coordination-report, export-risk-register) out of the box; how to add a partner overlay and use `--partner`; how to add or select coordination methods and scales via policy; how to interpret COORDINATION_DECISION and LAB_COORDINATION_REPORT for "best technique at scale"; and that the engine and tasks are lab-centric by design (Path B custom tasks, Path C future domain adapter).

2. **Single-page pipeline:** Ensure `docs/pipeline_overview.md` (or a one-pager linked from README) lists the exact sequence for "run matrix -> get recommendation -> get risk register" so forkers can copy-paste.

3. **Contract and testing bar:** In README or CONTRIBUTING, link to `docs/frozen_contracts.md` and `docs/STATUS.md` (Implementation and testing audit section) so contributors and forkers know what must not regress and what is covered by tests vs manual checks.

### 4.2 Contract and CI (stability for forkers)

1. **Keep frozen contracts:** Do not weaken runner output, queue, coordination interface, or risk register schema without a version bump and doc update.
2. **CI:** Ensure at least one job runs: policy validation, risk-register-gate (schema + snapshot + crosswalk + coverage), coordination interface contract, and a minimal coordination-security-pack smoke. So any forker pulling from main gets a stable baseline.
3. **Optional:** Nightly or on-demand job that runs package-release minimal to verify-release to export-risk-register and asserts success (as in STATUS implementation audit recommendations).

### 4.3 Policy and config only (no engine change)

1. **Coordination selection policy:** Document `policy/coordination/coordination_selection_policy.v0.1.yaml` so forkers can set hard constraints and objective (e.g. resilience vs throughput) for their organization.
2. **Matrix presets:** Document `--matrix-preset hospital_lab` and any other presets so forkers can run a lab-tailored matrix or extend presets for their own scales/methods.
3. **Official pack and risk register:** Document that run-official-pack and export-risk-register work on any run dir that has the expected layout (pack_summary.csv, SECURITY/, etc.) so forkers can plug their own pack output into the risk register.

### 4.4 Code modularity (optional, for Path B/C)

1. **Task registration:** If not already trivial, make task discovery more explicit (e.g. registry of task_id -> initial_state builder, episode_length) so adding a new task in a fork is a single registration point.
2. **Partner as first-class in CLI:** Most commands already accept `--partner`; ensure run-coordination-security-pack, build-lab-coordination-report, and export-risk-register all respect partner when loading policy so forkers get consistent behavior.
3. **Future domain adapter:** Leave a short "Future work" note in the forker guide: a domain adapter layer could map abstract workflows to the current engine action set so that multiple sectors share the same coordination/benchmark/security pipeline without duplicating engine code. Hospital lab remains the reference implementation.

---

## 5. End-to-end pipeline that must work (for us and forkers)

The following sequence should work from a clean clone (and from a forker’s repo) with no code changes, using the default hospital lab policy and partner:

1. `labtrust validate-policy` (and optionally `--partner hsl_like`)
2. `labtrust run-coordination-security-pack --out <dir> [--matrix-preset hospital_lab]`
3. `labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>]`
4. Open `COORDINATION_DECISION.v0.1.json` / `LAB_COORDINATION_REPORT.md` for recommended method per scale
5. `labtrust export-risk-register --out <dir2> --runs <dir>`
6. Optional: `labtrust run-official-pack --out <dir3>`, then `labtrust export-risk-register --runs <dir3>`

The same sequence should work for a forker who only adds a new partner overlay and points `--partner` to their overlay, provided their policy validates and uses the same coordination method IDs and scale IDs referenced in the study/pack.

---

## 6. Summary: what to do next

| Area | Action |
|------|--------|
| **Errors** | Schema and snapshot fixes are done. Run full test suite and address any other failures; add optional CI for Phase 2A and E2E chain if desired. |
| **Modularity** | Document the forker path (FORKER_GUIDE), pipeline one-pager, and contract/audit links. Keep contracts frozen and CI running contract gates and pack smoke. |
| **Forkability** | Rely on policy + partner overlays (Path A); document how to add tasks (Path B) and mention domain adapter as future (Path C). |
| **E2E pipeline** | Ensure the six-step flow above is documented and tested (e2e-artifacts-chain or equivalent). |
| **Hospital lab core** | Keep default policy, default partner hsl_like, and default tasks; do not dilute the lab semantics. Forkers extend or overlay; the core remains the reference. |

This balance keeps the codebase modular and the pipeline reusable for organizations that fork, while preserving the hospital lab and HSL-like design as the core use case and the reference implementation for coordination at scale, benchmarks, and security/safety evaluation.

---

## 7. Extended vision: work required to fully achieve the roadmap

Sections 1–6 describe the current balance and the steps already taken or planned. To **truly** achieve the vision—different organizations forking the repo, designing their own cyber-physical workflows, running coordination at scale, and determining the best technique for their organization with a robust security and safety story—the following additional work is required. This section does not replace 1–6; it makes explicit what remains beyond the immediate balance.

### 7.1 Fix and harden the E2E chain

- **verify-release:** The chain (package-release minimal to verify-release to export-risk-register) is implemented. The E2E script runs `labtrust verify-release --release-dir <release>`, which verifies every EvidenceBundle under the release; hashchain proof length is fixed so each bundle passes. To verify a minimal release in one step, use `labtrust verify-release --release-dir <out>`. See [Release checklist](release_checklist.md).
- **Determinism and golden suite in CI:** Run determinism-report and the full golden suite (`LABTRUST_RUN_GOLDEN=1`) in the same CI context as pack and coordination changes (e.g. required job or block on failure), so PRs cannot merge with non-deterministic or contract-breaking behavior.
- **E2E as a required gate:** Either run the full E2E artifacts chain on every PR (or on main after merge) and fail the build if any step fails, or document a release checklist that mandates passing E2E before tagging.

### 7.2 Domain and workflow abstraction (Path C, substantial)

- **Workflow/domain as first-class:** Today the engine and tasks are hospital-lab specific. To support organizations that need **non–lab-like** cyber-physical workflows (e.g. warehouse, factory, field ops), the repo would need:
  - A **workflow or domain spec** (schema): abstract resources, locations, constraints, and allowed actions that are independent of specimens/QC/critical.
  - A **domain adapter** layer that maps such a spec to engine actions and state (or to a variant of the engine). The hospital lab would be one concrete implementation of that adapter.
  - Extension points so a forker can add a new domain (new adapter + spec) without forking `core_env` or duplicating coordination/benchmark/security pipeline code.
- **Vocabulary and policy:** Emits, reason codes, and equipment are lab-oriented. A multi-domain design would require either a shared abstract vocabulary plus domain-specific extensions, or a clear policy layout (e.g. `policy/domains/<domain_id>/`) so each domain has its own emits, reason codes, and catalogue without colliding with the lab core.
- This is a **large design and implementation** effort; the roadmap currently treats it as future work and keeps the lab as the only reference domain.

### 7.3 Scale and operational readiness

- **"At scale" semantics:** Define what "coordination at scale" means for the platform: e.g. supported agent counts (100s vs 1000s), episode length, wall-clock and simulated timing, and any limits. Document and test at least one "at scale" profile (e.g. `corridor_heavy` or larger) so forkers know the intended envelope.
- **Persistence and replay:** If organizations are to run long or production-like evaluations, consider persistence of episode logs, checkpointing, and replay from checkpoint so runs can be resumed and audited.
- **Observability and ops:** Clear logging, metrics export (e.g. Prometheus/OpenTelemetry), and optional dashboards so forkers can monitor runs and debug failures without reading raw JSONL.

### 7.4 Organization-scoped policy and evidence

- **Per-org risk registry and security suite:** Allow a forker (or an org in a multi-tenant setup) to supply their own risk registry, security attack suite, or gate thresholds (e.g. under `policy/partners/<id>/risks/`, `policy/partners/<id>/golden/`) and have the pipeline use them when `--partner <id>` is set, without editing the core policy files.
- **Evidence and risk register:** Ensure the risk register and evidence bundle can aggregate runs from multiple partners or orgs with clear attribution (e.g. partner_id or org_id in evidence and links) so an organization’s report contains only their evidence and their risk view.
- **Selection policy and benchmark pack:** Already support partner overlay for selection policy; extend so an org can supply its own benchmark pack definition or study spec (e.g. different tasks or matrix) via partner or config, without changing the default pack.

### 7.5 Security and safety as first-class products

- **Security/safety gates that block the decision:** The "best coordination technique" should be invalidated (or clearly flagged) if security or safety regression is detected. That implies: (1) a defined security/safety gate (e.g. attack success rate, containment latency, or safety-case coverage) that can fail a run or a report; (2) integration of that gate into build-lab-coordination-report or recommend-coordination-method so "no admissible method" or "security gate failed" is a possible outcome; (3) documentation so forkers understand how to set and interpret these gates.
- **Security and safety reports as artifacts:** First-class artifacts (e.g. SECURITY_REPORT.md, SAFETY_CASE_REPORT.md) that summarize what was run, what passed or failed, and how that feeds into the coordination decision and risk register. Link them from LAB_COORDINATION_REPORT and the risk register so stakeholders get one coherent story.

### 7.6 CI and quality bar

- **Full coordination-security-pack on every PR (or main):** Today the pack smoke runs only when coordination-smoke is enabled (schedule or manual). To prevent contract or pack breakage from merging, run at least a minimal coordination-security-pack (e.g. fixed methods + critical injections) on every push/PR, or run the full pack on main after merge and fail the build if the gate fails.
- **Golden suite and determinism as required:** As in 7.1, make determinism-report and the full golden suite required for PRs that touch engine, runner, or coordination, so the baseline stays stable for forkers.
- **Test coverage and flakiness:** Run the full test suite regularly, fix flaky or environment-dependent tests, and document coverage expectations (e.g. critical paths covered by unit + integration tests).

### 7.7 Onboarding and documentation

- **One-command forker quickstart:** A single script or command (e.g. `labtrust forker-quickstart --out <dir>`) that, from a clean clone, runs validate-policy, run-coordination-security-pack (minimal matrix), build-lab-coordination-report, and export-risk-register, and prints where to find COORDINATION_DECISION and the risk register. Reduces friction for new forkers.
- **How-to guides:** Step-by-step docs: how to add a new coordination method (policy + code + test), how to add a new risk injection, how to tune the selection policy for a given org, and how to interpret and act on a failed security or gate result.
- **Troubleshooting:** Common failures (e.g. verify-bundle hashchain mismatch, policy validation errors, pack gate failures) and how to fix or work around them.

### 7.8 Summary: scope of "much more work"

| Theme | Scope | Priority |
|-------|--------|----------|
| E2E chain and verify-bundle | Fix so full chain passes; optionally make E2E required | High |
| Determinism and golden suite in CI | Required job(s) for pack/engine/coord changes | High |
| Domain/workflow abstraction (Path C) | Design + implementation for multi-domain platform | Large, longer term |
| Scale and operational readiness | Define scale envelope; persistence, replay, observability | Medium |
| Org-scoped policy and evidence | Partner-scoped risk suite, pack, evidence attribution | Medium |
| Security/safety gates and reports | Gates that can block decision; first-class security/safety reports | Medium |
| CI: pack and quality bar | Pack smoke or full pack on every PR; coverage and stability | High |
| Onboarding and how-to | One-command quickstart; how-to guides; troubleshooting | Medium |

Sections 1–6 remain the current roadmap and the basis for the existing implementation. Section 7 is the **extended backlog**: work that is needed to fully achieve the vision of a modular, forkable platform where different organizations design their cyber-physical workflows, run coordination at scale, and determine the best coordination technique for their organization with a robust security and safety story, without losing the hospital lab and HSL core.
