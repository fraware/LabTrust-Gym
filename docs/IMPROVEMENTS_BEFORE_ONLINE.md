# Improvements Before Going Online and Non-Deterministic

Checklist of things to improve **before** adding online APIs, real LLM providers, and non-deterministic runs. Completing these strengthens the deterministic/offline foundation and makes the transition safer.

---

## 1. Stability and correctness

| # | Item | Notes |
|---|------|--------|
| 1.1 | **Fix ui_fixtures evidence bundle** | `verify-bundle` fails on `ui_fixtures/evidence_bundle/EvidenceBundle.v0.1` (manifest hashes don't match file contents). Regenerate manifest from current files so UI team and docs examples pass verify-bundle. |
| 1.2 | **Stabilize long-running tests** | `test_package_release_determinism` (and similar) can hit pytest timeout. Either: increase default timeout in pyproject.toml, mark as `@pytest.mark.slow` and exclude from default run, or split into smaller tests. |
| 1.3 | **Golden suite in CI** | Decide whether to run full golden suite (`LABTRUST_RUN_GOLDEN=1`) in CI or keep it optional; document in CONTRIBUTING and ci.md. |
| 1.4 | **Determinism report coverage** | Ensure determinism-report is run (or runnable) for at least one task in CI so regressions in reproducibility are caught. |

---

## 2. Code optimization

| # | Item | Notes |
|---|------|--------|
| 2.1 | **Policy loading in hot path** | `CoreEnv.reset()` loads several policy files (stability, invariants, sites, equipment) every reset. Consider: (a) loading once and reusing when `repo_root`/policy path unchanged, or (b) accepting pre-loaded `effective_policy` and avoiding redundant disk reads in tight benchmark loops. |
| 2.2 | **Policy path resolution** | `reset()` uses `Path("policy/...")` relative to cwd in some branches. Ensure all callers pass `repo_root` or `effective_policy` so path resolution is consistent and minimal. |
| 2.3 | **Large JSONL handling** | Episode logs and ui-export `events.json` can grow large. For very long runs, consider: streaming JSONL write, chunked ui-export (e.g. `events_0.json`, `events_1.json`), or optional compression in the zip. |
| 2.4 | **Summarize and export** | `summarize-results` and `ui-export` iterate over many files; ensure single pass where possible and avoid re-reading the same file. |
| 2.5 | **Optional engine refactor** | STATUS mentions optional `state.py`, `event.py`, `errors.py`. If refactoring: extract immutable state/event shapes for clearer contracts and potential reuse (e.g. serialization, replay). Not blocking for online. |
| 2.6 | **RNG and reproducibility** | Single RNG wrapper is good; ensure no ambient randomness (e.g. `random` or `time.time()`) in engine or baselines so determinism remains auditable. |

---

## 3. Testing

| # | Item | Notes |
|---|------|--------|
| 3.1 | **Pytest configuration** | Set a sensible default `--timeout` (e.g. 60 or 120s) in `pyproject.toml` or `pytest.ini`; use `@pytest.mark.slow` for package_release and golden so `pytest -q` stays fast. |
| 3.2 | **Test coverage** | Run coverage (e.g. `pytest --cov=src/labtrust_gym --cov-report=term-missing`); add tests for uncovered branches in CLI, export, or policy loader. |
| 3.3 | **CI matrix** | Consider testing on both Linux and Windows (path encoding, line endings) so issues like "Matéo" path are caught. |
| 3.4 | **Smoke test script** | Add a single script (e.g. `scripts/smoke.sh` / `smoke.ps1`) that runs validate-policy, quick-eval, and one short benchmark; document in README for "does it work?" check. |

---

## 4. Documentation and UX

| # | Item | Notes |
|---|------|--------|
| 4.1 | **Path with special characters** | Document clearly: avoid project paths with accented or special characters (e.g. "Matéo"); add to installation troubleshooting and README. |
| 4.2 | **Quickstart script robustness** | Ensure quickstart (e.g. `scripts/quickstart_paper_v0.1.sh`) works when run from repo root and when policy is from package data; avoid hard-coded paths. |
| 4.3 | **Error messages** | Review CLI errors (e.g. "Run directory not found", "Unrecognized run layout") for clarity and suggest next steps (e.g. "Run labtrust quick-eval first"). |
| 4.4 | **Jupyter / notebooks** | STATUS notes "Example notebooks: None". Optional: one minimal notebook (install, validate-policy, quick-eval, load results) for onboarding. |
| 4.5 | **API reference** | Ensure mkdocstrings picks up all public modules (e.g. `export.ui_export`); add short "Usage" examples where helpful. |

---

## 5. Infrastructure and CI

| # | Item | Notes |
|---|------|--------|
| 5.1 | **CI workflow** | Keep quick-eval and validate-policy on every push; optionally run bench-smoke or package-release on a schedule or manual trigger only. |
| 5.2 | **Release artifact** | Document how to attach determinism reports and paper_v0.1 artifact to GitHub Release (or external storage); CONTRACTS.md already references this. |
| 5.3 | **Dependency pinning** | Consider pinning key deps (e.g. PettingZoo, Gymnasium) to minor versions in pyproject.toml or CI to avoid surprise breakages. |

---

## 6. Security and secrets (pre-online)

| # | Item | Notes |
|---|------|--------|
| 6.1 | **No secrets in repo** | Confirm no API keys, tokens, or credentials in code or policy; .gitignore already ignores .env if added. |
| 6.2 | **Document secret handling** | When adding real LLM/API: document that API keys must come from environment (or a secure secret store), not from config files in repo; keep optional .env loading explicit and documented. |
| 6.3 | **Audit log sensitivity** | Evidence bundles and episode logs may contain sensitive data; document retention and sharing policy before enabling online/non-deterministic runs. |

---

## 7. Pre-online readiness (summary)

Before introducing **online** and **non-deterministic** behaviour:

- **Deterministic baseline must stay default:** All CI, quick-eval, bench-smoke, and package-release must remain reproducible with seeded RNG and deterministic backends.
- **Real LLM behind a flag:** e.g. `--llm-provider openai` or `use_real_llm=True`; default remains `DeterministicConstrainedBackend(seed)`.
- **API keys:** Only from environment (or secure store); never committed. Document in installation and llm_baselines.
- **Metrics and comparison:** Non-deterministic runs should not be compared to deterministic baselines without clear labeling (e.g. "exploratory", "non-reproducible").

Use this list to tick off items; when the checklist is in good shape, the project is in a strong position to add online APIs and non-deterministic modes without undermining reproducibility.
