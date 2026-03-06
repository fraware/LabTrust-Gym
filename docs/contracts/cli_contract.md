# CLI output contract

This document defines the contract for all LabTrust-Gym CLI commands: exit codes, minimal smoke arguments, expected output paths, and schema references. Used by the CLI smoke matrix and for consistent "expected results in a similar structured way."

## Conventions

- **Exit code:** 0 = success, 1 = failure. All commands use stderr for progress and errors; only `labtrust --version` prints to stdout.
- **Output paths:** Commands write to explicit paths (e.g. `--out`, `--out-dir`, `--run` plus derived paths). Paths are relative to process CWD unless absolute.
- **Schema refs:** Where applicable, output files conform to versioned schemas under `policy/schemas/` or contracts in `docs/`.
- **Pipeline modes:** Benchmark result files (results.json and summaries built from them) always record **pipeline_mode**, **llm_backend_id**, **allow_network**, and **non_deterministic**. Regression and official baselines require deterministic pipelines. See [Outputs and results](../reference/outputs_and_results.md#11-pipeline-modes-and-result-audit) and [Metrics contract](metrics_contract.md).
- **Verbosity:** Global flags `-v` / `--verbose` and `-q` / `--global-quiet` control output detail. Default (normal): info, success, warnings, errors on stderr. Verbose: plus debug logs, progress detail, tracebacks. Quiet: minimal output (errors and summary only). Progress and errors remain on stderr in all cases.
- **Output format:** When the optional `.[cli]` extra (Rich) is installed, stderr output may use colors and structured formatting. Without Rich, the same messages are printed in plain text. Critical one-line messages (e.g. "Policy validation OK.", "Wrote &lt;path&gt;") are stable for scripting.

## Contract table

| Command | Minimal smoke args | Exit | Expected output paths | Schema / contract ref |
|---------|--------------------|------|------------------------|----------------------|
| validate-policy | (none) or `--partner hsl_like` or `--domain <domain_id>` | 0 | (none; success message on stderr) | policy schemas. With `--domain`, loads and validates policy merged from base plus `policy/domains/<domain_id>/`. Checks schema and structural validity only; does **not** check logical correctness (e.g. zone connectivity, invariant feasibility, or that controls match risks). |
| forker-quickstart | `--out <dir>` | 0 | `<out>/pack/pack_summary.csv`, `<out>/pack/COORDINATION_DECISION.v0.1.json`, `<out>/risk_out/RISK_REGISTER_BUNDLE.v0.1.json` | risk_register_contract.v0.1 |
| quick-eval | `--seed 42 --out-dir <dir>` | 0 | `<dir>/quick_eval_*/throughput_sla.json`, `adversarial_disruption.json`, `multi_site_stat.json`, `logs/*.jsonl`, `summary.md` | results.v0.2, ui_data_contract |
| run-benchmark | `--task throughput_sla --episodes 1 --seed 42 --out <path>` | 0 | `<path>` (results.json) | results.v0.2, metrics_contract |
| eval-agent | `--task throughput_sla --episodes 1 --agent examples.external_agent_demo:SafeNoOpAgent --out <path> --seed 42` | 0 | `<path>` (results.json) | results.v0.2 |
| bench-smoke | `--seed 42` | 0 | (writes under CWD or labtrust_runs; results JSON per task) | results.v0.2 |
| export-receipts | `--run <log.jsonl> --out <dir>` | 0 | `<dir>/EvidenceBundle.v0.1/manifest.json`, receipt_*.v0.1.json | EvidenceBundle.v0.1 |
| export-fhir | `--receipts <dir> --out <dir>` | 0 | `<out>/fhir_bundle.json` (default filename) | fhir_export.md |
| validate-fhir | `--bundle <path> --terminology <path>` [--strict] | 0 or 1 | (none; violations on stderr; exit 1 with --strict if any code outside value set) | Optional; not part of minimal benchmark. See fhir_export.md. |
| verify-bundle | `--bundle <EvidenceBundle.v0.1 dir>` or `--strict-fingerprints` | 0 | (none; PASS on stderr) | frozen_contracts.md, trust_verification.md |
| verify-release | `--release-dir <dir>` optional `--strict-fingerprints` | 0 | (none; summary on stderr; validates EvidenceBundles, risk register, RELEASE_MANIFEST hashes) | frozen_contracts.md, trust_verification.md |
| build-release-manifest | `--release-dir <dir>` | 0 | `<release-dir>/RELEASE_MANIFEST.v0.1.json` | trust_verification.md |
| run-security-suite | `--out <dir> --smoke` | 0 | `<dir>/SECURITY/attack_results.json` | security_attack_suite.md |
| safety-case | `--out <dir>` | 0 | `<dir>/SAFETY_CASE/safety_case.json`, `safety_case.md` | risk_register.md, trust_verification.md |
| run-official-pack | `--out <dir> --smoke` | 0 | `<dir>/pack_manifest.json`, `baselines/`, `baselines/results/`, `SECURITY/`, `SAFETY_CASE/` | official_benchmark_pack.md |
| ui-export | `--run <dir> --out <zip>` | 0 | `<out>` (zip: index.json, events.json, receipts_index.json, reason_codes.json) | ui_data_contract.md |
| export-risk-register | `--out <dir>` or `--out <dir> --runs tests/fixtures/ui_fixtures` | 0 | `<out>/RISK_REGISTER_BUNDLE.v0.1.json` | risk_register_contract.v0.1.md |
| build-risk-register-bundle | `--out <path>` | 0 | `<path>` (risk_register_bundle.v0.1.json) | risk_register_contract.v0.1.md |
| validate-coverage | `--bundle <path>` or `--out <dir>` (bundle in dir) | 0 or 1 | (none; reports on stderr; exit 1 with `--strict` if any required_bench cell has no evidence) | risk_register.md |
| show-method-risk-matrix | (none) or `--format table\|csv\|markdown` `--out <path>` | 0 or 1 | stdout or `<path>` (method x risk table/csv/markdown from method_risk_matrix.v0.1.yaml) | method_and_pack_matrix.md |
| show-pack-matrix | (none) or `--matrix-preset hospital_lab` `--format table\|csv\|markdown` `--out <path>` | 0 or 1 | stdout or `<path>` (method x scale x injection with scale taxonomy; from coordination_security_pack) | method_and_pack_matrix.md |
| show-pack-results | `--run <dir>` (pack run with pack_summary.csv, SECURITY/coordination_risk_matrix.*) `--format markdown\|table\|csv` `--out <path>` | 0 or 1 | stdout or `<path>` (result matrix with real metrics and verdicts; no placeholders) | method_and_pack_matrix.md |
| run-study | `--spec <yaml> --out <dir>` | 0 | `<out>/` (condition dirs, results, manifest) | studies.md |
| run-coordination-study | `--spec <yaml> --out <dir>` | 0 | `<out>/summary/summary_coord.csv`, `summary/pareto.md`, cells/ | coordination_studies.md |
| run-coordination-security-pack | `--out <dir> --seed 42` | 0 | `<out>/pack_summary.csv`, `pack_gate.md`, `pack_results/` | security_attack_suite.md |
| summarize-coordination | `--in <dir> --out <dir>` | 0 | `<out>/summary/sota_leaderboard.csv`, `sota_leaderboard.md`, `sota_leaderboard_full.csv`, `sota_leaderboard_full.md`, `method_class_comparison.csv`, `method_class_comparison.md` | coordination_studies.md, hospital_lab_metrics.md |
| recommend-coordination-method | `--run <dir> --out <dir>` | 0 | `<out>/COORDINATION_DECISION.v0.1.json`, `COORDINATION_DECISION.md` | howto_selection_policy.md |
| build-coordination-matrix | `--run <dir> --out <path>` | 0 | `<path>` or `<path>/coordination_matrix.v0.1.json` | coordination studies |
| build-episode-bundle | `--run-dir <path>` [--out <path>] | 0 | `<run-dir>/episode_bundle.json` or `<out>` (if --out given) | episode_viewer.md |
| make-plots | `--run <dir>` [--theme light\|dark] | 0 | `<run>/figures/` (PNG/SVG, data_tables/, RUN_REPORT.md) | studies.md, pipeline_overview.md |
| reproduce | `--profile minimal --out <dir>` | 0 | `<dir>/` (sweep results, figures) | reproduce.md |
| package-release | `--profile minimal --out <dir>` | 0 | `<dir>/MANIFEST.v0.1.json`, `_repr/`, `receipts/`, `FIGURES/` (paper_v0.1) | paper_ready.md, trust_verification.md |
| generate-official-baselines | `--out <dir> --episodes 2 --seed 42 --force` | 0 | `<dir>/results/` (throughput_sla through insider_key_misuse plus coord_scale, coord_risk JSON), `summary.csv`, `summary.md`, `summary_v0.2.csv`, `summary_v0.3.csv`, `metadata.json` | baseline_registry.v0.1.yaml, metrics_contract |
| summarize-results | `--in <dir_or_file> --out <dir> --basename summary` | 0 | `<out>/summary_v0.2.csv`, `summary_v0.3.csv`, `summary.csv`, `summary.md`; when run metadata present: `run_info.csv`, Run info section in summary.md | metrics_contract.md |
| determinism-report | `--task throughput_sla --episodes 2 --seed 42 --out <dir>` | 0 | `<dir>/determinism_report.json`, `determinism_report.md` (checks summary, run config, hash comparison) | reproducible_builds.md, benchmarks.md |
| train-ppo | `--task throughput_sla --timesteps 100 --seed 42 --out <dir>` | 0 | `<dir>/model.zip` (or run dir with model) | marl_baselines.md |
| eval-ppo | `--model <model.zip> --task throughput_sla --episodes 2 --seed 42 --out <path>` | 0 | `<path>` (metrics JSON) or stderr | marl_baselines.md |
| serve | `--host 127.0.0.1 --port <port>` | 0 | (server runs; GET /v0/summary returns 200) | security_online.md, output_controls.md |

## Optional / conditional commands

- **train-ppo**, **eval-ppo:** Require `.[marl]` extra (stable-baselines3, torch). Smoke tests may skip if not installed.
- **serve:** Long-running; smoke test starts server, GET /v0/summary, then terminates. Optional in CI.
- **forker-quickstart:** Depends on validate-policy and coordination pack; full flow can be slow (timeout ~180s in smoke).
- **run-official-pack:** With `--smoke` is faster; full pack has higher timeout.
- **run-coordination-study:** Use minimal spec (e.g. `tests/fixtures/coordination_study_llm_smoke_spec.yaml`) for smoke.

## Timeouts (smoke matrix)

Suggested per-command timeouts for minimal runs:

- Light (30s): validate-policy, verify-bundle, verify-release, safety-case, deps-inventory, build-risk-register-bundle, export-risk-register (with fixtures), summarize-results, summarize-coordination, recommend-coordination-method, build-coordination-matrix, ui-export.
- Medium (60s): quick-eval, run-benchmark (1 ep), eval-agent (1 ep), bench-smoke, export-receipts, export-fhir, run-security-suite (smoke), make-plots (small run), determinism-report (2 ep).
- Heavy (120–180s): forker-quickstart, run-study (minimal spec), run-coordination-study (smoke spec), run-coordination-security-pack, reproduce (minimal), package-release (minimal), generate-official-baselines (2 ep), run-official-pack (smoke).
- Optional / skip: train-ppo, eval-ppo (marl), serve (start + GET + stop).
