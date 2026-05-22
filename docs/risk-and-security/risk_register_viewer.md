# Risk Register Viewer

The viewer is a **dataset-driven** site over a stable RiskRegisterBundle.v0.1 dataset. All content comes from the loaded bundle, so you can swap datasets (fixtures versus paper release) without changing UI code.

## Loader (three modes, offline-first)

The loader (`viewer/load_bundle.js`) supports:

| Mode | Input | Default |
|------|--------|---------|
| **Local file** | User selects a `.json` file (RiskRegisterBundle.v0.1.json). | Yes (offline-first). |
| **Inside ui-export zip** | User selects a `.zip` that contains `RISK_REGISTER_BUNDLE.v0.1.json` at root. Optional: embed the bundle in ui-export so one zip serves both run data and risk register. | No (optional). |
| **Remote URL** | URL to a JSON bundle (future). | No; offline-first remains default. |
| **Latest release** | Load from `viewer-data/latest/`: fetches `latest.json` then the referenced bundle file. | When served over HTTP; the **docs** workflow deploys the site with `viewer/` and `viewer-data/latest/` to GitHub Pages, so "Load latest release" works at the repo Pages URL. |

The loader API is `loadRiskRegisterBundle(source)` → `Promise<Bundle>`.

- `source` may be a **string** (URL), a **File** from `<input type="file">`, or **`{ url: string }`**.
- For a **File**, read `.json` as text and `JSON.parse`; for `.zip`, use JSZip to find `RISK_REGISTER_BUNDLE.v0.1.json` (or `risk_register_bundle.v0.1.json`) and parse.
- For a **URL**, call `fetch(source)` then `.json()`.
- The function returns the parsed bundle and validates minimal shape (`bundle_version`, `risks` array).

## Core UX primitives (CPS-native)

- **Global search** covers `risk_id`, title (name), description, control names, and evidence summaries.
- **Faceted filters** include `risk_domain`, `applies_to`, `coverage_status`, “has evidence” (yes/no), and “failed evidence” (yes/no). Failed means `status` is missing or `summary.failed` &gt; 0.
- The **risk detail page** shows the risk definition, claimed controls, evidence list, and **“How to reproduce”** commands.

## How to reproduce (generated, not written)

Reproduction commands are **stored in the bundle** under `reproduce[]`, so the UI is dumb and always consistent:

- Each `reproduce` entry has `evidence_id`, `label`, `commands` (array of strings).
- Commands are **generated** at bundle build time by evidence type, e.g.:
  - **Security suite:** `labtrust run-security-suite --out <output_dir> --seed 42`
  - **Coordination study:** `labtrust run-coordination-study --spec <study_spec> --out <output_dir>` (and optional single-cell `run-benchmark --task coord_risk ...`)
  - **Safety case:** `labtrust safety-case --out <output_dir>`
  - **Official pack:** `labtrust run-official-pack --out <output_dir> [--seed-base 42]` (add `--pipeline-mode llm_live --allow-network` for live LLM; produces TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json)
  - **Bundle verification:** `labtrust verify-bundle --bundle <run_dir>` or `package-release --profile paper_v0.1 --out <output_dir>`
  - **Evidence gap:** empty `commands[]`; label indicates “Evidence not yet collected”.

Template variables `<output_dir>` and `<study_spec>` can be substituted by the user when copying the command.

## What reviewers see (beyond PASS/FAIL)

- **EvidenceBundle verification summary.** When a run directory contains an EvidenceBundle (for example `receipts/<task>/EvidenceBundle.v0.1`), the bundle builder runs verification and attaches `verification_summary` to the manifest evidence, including manifest hash validity, schema validity, hashchain proof, invariant trace, and policy fingerprints (RBAC, coordination identity, memory, tool registry). The viewer surfaces these fields so reviewers see what was verified.
- **Blocked actions (reason codes).** For security suite evidence, when `attack_results.json` includes `reason_code_counts` per attack, the builder merges them into `reason_code_distribution` on the evidence entry. The viewer shows top reason codes so reviewers understand how failures were detected and contained.
- **Coordination security and resilience.** For evidence from `summary_coord.csv`, the builder parses the CSV and attaches `summary.coord_metrics` with rows for `sec.attack_success_rate`, `sec.stealth_success_rate`, `sec.time_to_attribution_steps`, `sec.blast_radius_proxy`, `robustness.resilience_score`, `perf.p95_tat`, `perf.throughput`, and `safety.violations_total`. The viewer renders a sample table with security and resilience metrics together.

## Acceptance

- **Swap datasets:** Load bundle derived from `tests/fixtures/ui_fixtures` or a paper-release bundle; same viewer code, no changes.
- **Every risk page shows** the definition (name, description, `typical_failure_mode`), claimed controls, evidence list (with status, summary, verification summary when present, reason-code distribution when present, coordination metrics when present), and reproduction commands per evidence.
- **Reviewers can see** what failed, how it was detected, what contained it, and which invariant or control is implicated through verification summary, reason codes, and evidence links.

## Running the viewer

Open `viewer/index.html` in a browser (or serve the `viewer/` directory over HTTP if you need to load a URL). Choose a RiskRegisterBundle.v0.1.json file (or a zip containing it), or enter a URL to a bundle. The viewer renders search, filters, risk list, and risk detail from the bundle only.
