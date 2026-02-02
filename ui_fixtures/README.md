# UI fixtures (v0.1.0)

Minimal deterministic fixtures for UI development. No benchmark runs required.

| File / directory | Description |
|------------------|-------------|
| results_v0.2.json | One task (TaskA), one episode, schema v0.2. Valid against results.v0.2.schema.json. |
| episode_log.jsonl | One episode step (JSONL line). Same format as engine step log. |
| evidence_bundle/ | One EvidenceBundle.v0.1 directory: manifest + one receipt. Valid for verify-bundle. |
| fhir_bundle.json | Minimal FHIR R4 Bundle (Bundle, type collection, one entry). |

**Acceptance:** UI team can build UI with zero running of benchmarks; they just import fixtures from this directory (results, episode log, evidence bundle, FHIR bundle) for deterministic, offline behaviour.

**UI data contract:** For production, the UI should consume **ui-export** output as primary input, not raw internal logs. Run `labtrust ui-export --run <dir> --out ui_bundle.zip` on a quick-eval or package-release run; the zip contains normalized `index.json`, `events.json`, `receipts_index.json`, and `reason_codes.json`. See [docs/ui_data_contract.md](../docs/ui_data_contract.md).
