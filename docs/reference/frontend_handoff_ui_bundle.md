# Frontend handoff: UI bundle and coordination artifacts

This document is for frontend engineers integrating the LabTrust UI bundle. It describes the zip structure, how to read it, and how to present coordination results (SOTA leaderboards and charts).

---

## 1. What you receive

**Artifact:** A zip file produced by:

```bash
labtrust ui-export --run <run_dir> --out ui_bundle.zip
```

**Typical run_dir:** Output of `labtrust run-official-pack --include-coordination-pack` (e.g. `demo_video_out/pack_llm`) or any directory that contains `baselines/`, `SECURITY/` or `SAFETY_CASE/`, and optionally `coordination_pack/` (or `pack_summary.csv` + `summary/` at root).

---

## 2. Zip contents (top level)

| Entry | Format | Purpose |
|-------|--------|---------|
| `index.json` | JSON | **Start here.** Run metadata, episodes, tasks, and list of coordination artifacts (paths + labels). |
| `events.json` | JSON | Normalized step-level events; optional for coordination views. |
| `receipts_index.json` | JSON | Receipt file refs; optional for coordination. |
| `reason_codes.json` | JSON | Reason code registry; optional for coordination. |
| `coordination/<path>` | Mixed | All coordination artifacts. Paths match `index.coordination_artifacts[].path` prefixed by `coordination/`. |

**Rule:** Resolve any coordination artifact as: **zip entry = `coordination/` + `index.coordination_artifacts[i].path`**.

---

## 3. index.json shape (relevant fields)

```json
{
  "ui_bundle_version": "0.1",
  "run_type": "full_pipeline",
  "tasks": [...],
  "episodes": [...],
  "baselines": [...],
  "coordination_artifacts": [
    { "path": "pack_summary.csv", "label": "Pack summary" },
    { "path": "summary/sota_leaderboard.md", "label": "SOTA leaderboard" },
    { "path": "summary/sota_leaderboard_full.md", "label": "SOTA leaderboard (full metrics)" },
    { "path": "summary/sota_leaderboard_full.csv", "label": "SOTA leaderboard full CSV" },
    { "path": "summary/method_class_comparison.md", "label": "Method class comparison" },
    { "path": "graphs/sota_key_metrics.html", "label": "SOTA key metrics (chart)" },
    { "path": "graphs/throughput_by_method.html", "label": "Throughput by method (chart)" },
    { "path": "graphs/violations_by_method.html", "label": "Violations by method (chart)" },
    { "path": "graphs/resilience_by_method.html", "label": "Resilience by method (chart)" },
    { "path": "graphs/method_class_comparison.html", "label": "Method class comparison (chart)" }
  ]
}
```

- **`coordination_artifacts`** may be missing (no coordination run). If present, use it to build nav/links.
- **`path`** is relative; the file in the zip is **`coordination/` + `path`** (e.g. `coordination/graphs/sota_key_metrics.html`).

---

## 4. Presenting coordination artifacts

### 4.1 Tables (Markdown / CSV)

- **Markdown (`.md`):** Read zip entry as UTF-8 text; render as Markdown (table, headers, run metadata block at top of main leaderboard).
- **CSV (e.g. `summary/sota_leaderboard_full.csv`):** Parse for custom tables or charts. Columns include method_id, throughput_mean, violations_mean, resilience_score_mean, blocks_mean, attack_success_rate_mean, etc.

**Suggested UX:** Primary view = main SOTA leaderboard (`summary/sota_leaderboard.md`). Link “Full metrics” to `sota_leaderboard_full.md` or `.csv`, and “By method class” to `method_class_comparison.md`.

### 4.2 Charts (HTML)

- **Format:** Self-contained HTML; Chart.js loaded from CDN. No iframe sandbox restrictions needed for same-origin zip content; ensure CSP allows `cdn.jsdelivr.net` if you inject the HTML into the page.
- **Zip path:** `coordination/graphs/<name>.html` (e.g. `coordination/graphs/sota_key_metrics.html`).
- **Content:** Each chart page includes a **results explanation** paragraph (class `chart-explanation`) below the canvas, describing how to read the chart (e.g. what each bar represents, normalization, “higher is better”). A short **footnote** (class `chart-footnote`) gives data source and scope. Preserve both when embedding or linking to the HTML.
- **How to show:**
  - **Option A:** Extract HTML string from zip, create a blob URL, open in new tab or set as `iframe.src`.
  - **Option B:** Inject the HTML into a sandboxed iframe or a dedicated “chart” container (with CSP that allows the Chart.js CDN).

**Charts included (when data exists):**

| path | label | Use |
|------|--------|-----|
| `graphs/sota_key_metrics.html` | SOTA key metrics (chart) | **Primary:** one chart with four metrics (throughput, resilience, safety, security) by method. |
| `graphs/throughput_by_method.html` | Throughput by method (chart) | Throughput (mean) per method. |
| `graphs/violations_by_method.html` | Violations by method (chart) | Violations (mean) per method. |
| `graphs/resilience_by_method.html` | Resilience by method (chart) | Resilience score per method. |
| `graphs/method_class_comparison.html` | Method class comparison (chart) | Throughput and resilience by method class. |

Each chart already includes a title, axis labels, and a source footnote. No extra config needed.

---

## 5. Minimal integration checklist

1. **Unzip** (or read from zip) and parse **`index.json`**.
2. If **`index.coordination_artifacts`** exists:
   - Build a list or nav of links using **`label`** and resolve each file as **`coordination/` + `path`** inside the zip.
   - For **`.md`**: read as text, render Markdown.
   - For **`.csv`**: read as text, parse CSV for tables or custom viz.
   - For **`graphs/*.html`**: read as UTF-8 string; display in iframe (blob URL or injected HTML with allowed CDN).
3. **Primary chart:** Prefer **`graphs/sota_key_metrics.html`** as the single “state of the art” view when showing coordination metrics.
4. **Fallback:** If `coordination_artifacts` is absent, hide or disable coordination / SOTA sections.

---

## 6. File resolution helper (pseudocode)

```text
function getCoordinationFile(zip, artifactPath) {
  const entryPath = "coordination/" + artifactPath;  // e.g. coordination/graphs/sota_key_metrics.html
  return zip.getEntry(entryPath)?.getContentAsString();  // or equivalent
}

// List artifacts for nav
const artifacts = index.coordination_artifacts || [];
artifacts.forEach(art => {
  const path = art.path;
  const label = art.label;
  const isChart = path.startsWith("graphs/");
  const isMarkdown = path.endsWith(".md");
  const isCsv = path.endsWith(".csv");
  // Render link or iframe based on type; resolve content via getCoordinationFile(zip, path)
});
```

---

## 7. References

- **Contract (canonical):** [UI data contract](../contracts/ui_data_contract.md)
- **Metrics meaning:** [Hospital lab key metrics](../benchmarks/hospital_lab_metrics.md)
- **CLI:** `labtrust ui-export --help`

---

## 8. Summary for product

- **Input:** One zip from `labtrust ui-export --run <dir> --out <file>`.
- **Entry point:** `index.json` → `coordination_artifacts[]` (path + label).
- **Resolve path:** Zip entry = `coordination/` + `path`.
- **Primary chart:** `graphs/sota_key_metrics.html` (one SOTA view; title and axes already in the HTML).
- **Tables:** `summary/sota_leaderboard.md` (main), `summary/sota_leaderboard_full.md` / `.csv`, `summary/method_class_comparison.md`.
- **Charts:** All under `graphs/*.html`; display in iframe or new tab from blob/injected HTML; allow Chart.js CDN if using CSP.
