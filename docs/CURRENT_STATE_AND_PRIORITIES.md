# Current state and priorities

This document gives a structured view of **current state**, **gaps**, **what to work on next**, and **what is not yet in scope** for this release. For full implementation detail see [STATUS](STATUS.md).

## Current state (summary)

- **Contract freeze:** v0.1.0. Frozen contracts: runner output, queue, invariant registry, enforcement, receipt, evidence bundle, FHIR, results v0.2/v0.3. See [Frozen contracts](frozen_contracts.md).
- **Core path:** Policy load/validate, golden runner, audit/hashchain, RBAC, tokens, zones, specimens, QC, critical, queueing, transport, invariants, enforcement. Golden suite: 34 scenarios. PettingZoo Parallel and AEC wrappers.
- **Benchmarks and baselines:** throughput_sla through coord_risk; scripted, adversary, insider, LLM, MARL, coordination. Official pack v0.1/v0.2, security suite, safety case, prompt-injection defense. Export: receipts, FHIR R4 (data-absent-reason; no placeholder IDs), ui-export, risk register, validate-coverage.
- **CI:** Lint, typecheck, test (fast suite), golden job, policy-validate, risk-register-gate, quick-eval, baseline-regression, docs. Optional: bench-smoke, coordination-smoke, determinism-golden (schedule or path-filtered), e2e-artifacts-chain, llm_live smoke. See [CI](ci.md).

## Gaps and what demands attention

| Area | Status | Action |
|------|--------|--------|
| **ui_fixtures evidence bundle** | Manifest lists `enforcement_actions.jsonl` and `invariant_eval_trace.jsonl`; fixture dir must contain them with hashes matching manifest (e.g. empty files). | Add missing files so `verify_bundle` passes in risk-register-gate. |
| **Long-running tests** | package_release, golden suite can be slow; no timeout or `@pytest.mark.slow` consistently. | Add `@pytest.mark.slow` and pytest timeout for package_release/golden; keep default CI fast with `-m "not slow"`. |
| **Golden suite in CI** | Golden job runs on every push/PR (or determinism-golden on path-filtered). | Decided: golden in CI; document in [CI](ci.md). Determinism-report: optional job or manual. |
| **E2E with real LLM** | No automated E2E asserting non-empty model/latency/cost. | Optional CI job when API key set; document in workflow and [CI](ci.md). |
| **Determinism-report** | Separate manual/CI step. | Optional CI job (e.g. schedule); document. |
| **Reserved injection IDs** | Legacy IDs (e.g. `inj_tool_selection_noise`, `inj_prompt_injection`) are NoOpInjector; not implemented as full injectors. | Document as "reserved / out of scope for this release" in [Risk register](risk_register.md) and [Coordination studies](coordination_studies.md). Prefer INJ-* from injections.v0.2. |
| **Engine layout** | state.py, event.py, errors.py not split out; state is dict-based. | Optional refactor; not required for functionality. |
| **CURRENT_STATE_AND_PRIORITIES.md** | This doc; referenced from STATUS. | Keep updated as gaps are closed. |

## What to work on next (prioritized)

1. **Stability:** Fix ui_fixtures evidence bundle for verify-bundle; add `@pytest.mark.slow` and timeouts for package_release/golden.
2. **Documentation:** Reserved injection IDs (risk register + coordination); pre-online hardening (deterministic default, LLM behind flag, API keys from env, non-deterministic labeled); paths with special characters and quickstart in installation/troubleshooting.
3. **Testing:** Pytest timeout plugin or `pytest.ini` timeout; coverage; optional CI matrix (Linux/Windows); smoke script.
4. **Code (optional):** Policy loading in hot path; policy path resolution; large JSONL; single-pass summarize/export; no ambient randomness.
5. **Pre-online:** Ensure deterministic baseline remains default; real LLM behind flag; API keys from environment only; non-deterministic runs clearly labeled (document in [CI](ci.md) and [Contributing](contributing.md)).

## What is not in scope for this release

- **B003** public-release redaction (security).
- **Jupyter notebooks** (docs/examples).
- **state.py / event.py / errors.py** as separate engine modules (optional refactor).
- **Full injectors for reserved injection IDs** (e.g. inj_tool_selection_noise, inj_prompt_injection); they remain NoOpInjector for compatibility; use INJ-* for active injections.
- **Published benchmark results** (optional artifact).

## References

- [STATUS](STATUS.md) — Full implementation and testing audit.
- [Improvements before online](STATUS.md#improvements-before-online-checklist) — Checklist in STATUS.
- [CI](ci.md) — Gates, optional jobs, deterministic vs non-deterministic.
- [Contributing](contributing.md) — Verification and audit steps.
