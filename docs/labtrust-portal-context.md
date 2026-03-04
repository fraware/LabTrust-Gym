# LabTrust Portal: Context and Build Specification

This document provides all data and context necessary to implement the **LabTrust Portal**: a single website that serves as the public data plane and gated control plane for the LabTrust-Gym project. It aligns the product vision with the existing repo artifacts, CLI, schemas, and conventions.

---

## 1. Project Vision: One Portal, Two Planes

### Data plane (public, immutable)

Everything derived from **releases**:

- Risk register (risks, controls, evidence, coverage status)
- Benchmarks (runs, suites, method compare, pack results)
- Evidence (receipts, EvidenceBundle.v0.1, verification summaries)
- Manifests (MANIFEST.v0.1.json, RELEASE_MANIFEST.v0.1.json)
- Signatures and hashes (bundle verification, policy fingerprints)
- Claims snapshots (paper-facing outputs)

**Source of truth:** `public-data/<channel>/latest.json` (or equivalent) loads bundle, manifest, benchmark index, receipts. Client-side verification (hash + signature) is expected.

### Control plane (restricted, privileged)

Everything that **executes**:

- Run required bench pack
- Package-release (minimal / full)
- Verify-release
- Regenerate viewer-data / latest
- Diagnostics (doctor, audit-selfcheck)
- Claims regression and research surface (injectors, detection/containment eval)

**Access:** Everyone can browse the data plane. The control plane is **visible but gated** (buttons appear disabled with "requires maintainer access" or only after login).

---

## 2. Core Design: Lenses, Not Separate Sites

Instead of "developer vs stakeholder" sites, provide **three lenses** (UI presets) over the same pages and objects:

| Lens | Emphasis |
|------|----------|
| **Review** | Claims, risk, evidence sufficiency, waivers, integrity |
| **Operator** | Runbooks, workflows, environment checks, reproducibility |
| **Builder** | Method internals, registries, test harnesses, extension points |

**Mechanics:** A lens is:

- Default landing page
- Default sidebar grouping
- Which panels appear first on detail pages
- Which CTAs are prominent

**No duplicated content. Same URLs.** Only presentation and default focus change.

---

## 3. Navigation: Object-Centric

The portal should feel like a **browser over immutable objects**.

### Primary objects

| Object | Description | Repo / artifact reference |
|--------|-------------|---------------------------|
| **Release** | Version, git_sha, generated_at, manifest, gates | `package-release` output; `MANIFEST.v0.1.json`, `RELEASE_MANIFEST.v0.1.json`; see [Trust verification](risk-and-security/trust_verification.md) and [CI](operations/ci.md) |
| **Risk** | risk_id, narrative, controls, evidence, coverage | `policy/risks/risk_registry.v0.1.yaml`; RiskRegisterBundle.v0.1 `risks[]`; [Risk register contract](contracts/risk_register_contract.v0.1.md) |
| **Method** | method_id, family, contract, invariants, benchmark results | `policy/coordination/coordination_methods.v0.1.yaml`; [How coordination methods work](coordination/coordination_methods_how_they_work.md) |
| **Benchmark run / suite** | Pack results, verdicts, metrics | `run-coordination-security-pack` output; `pack_summary.csv`, `SECURITY/coordination_risk_matrix.csv`; results.v0.2/v0.3 |
| **Evidence item / receipt** | evidence_id, type, path, status, summary | RiskRegisterBundle.v0.1 `evidence[]`; EvidenceBundle.v0.1 dirs under `receipts/<task>/`; [Risk register contract](contracts/risk_register_contract.v0.1.md) |
| **Waiver** | required_bench cell waived with rationale/expiry | `policy/risks/waivers.v0.1.yaml`; `validate-coverage --strict` uses these |
| **Claim snapshot** | Paper-facing claims per release | Output of claims/safety-case pipeline; link from release detail |

Everything else (filters, compare views, runbooks) is a **view over these objects**.

---

## 4. Information Architecture: Six Top-Level Sections

### A) Home

Single high-signal dashboard for the **currently selected release channel** (latest, candidate, vX.Y.Z).

**Display:**

- **Release ID:** version, git_sha, generated_at (from `latest.json` or release manifest)
- **Gate status:** verify-release strict, strict coverage, required bench pack, viewer-data build (from e2e-artifacts-chain / release checklist)
- **What changed since previous:** policy digests, risk diffs, benchmark deltas (when compare data available)
- **Integrity badge:** hash + signature verified (or not); link to right-drawer verification panel

**CTAs:**

- Primary: "Open this release"
- Secondary: "Compare to…"

**Data sources:** `viewer-data/latest/latest.json` (git_sha, version, generated_at, bundle_file); RELEASE_MANIFEST.v0.1.json; [viewer-data build](risk-and-security/risk_register_viewer.md) (Load latest release).

---

### B) Releases

Release timeline and diff tooling.

**List:** Table with version, date, passing gates, notes.

**Release detail:**

- **Manifest:** Human-readable summary + raw JSON (MANIFEST.v0.1.json)
- **Inputs:** Policy digests, tool registry digests, prompt digests (from bundle or manifest)
- **Outputs:** Bundle, benchmark index, claims snapshots
- **Reproduce block:** Exact CLI commands and expected hashes (package-release, export-risk-register, build-release-manifest, verify-release)

**Anchor:** This is the "unit of truth" for the release. Repo unit of truth: `tests/fixtures/release_fixture_minimal` and e2e-artifacts-chain.

**CLI:** `labtrust package-release`, `labtrust verify-release`, `labtrust build-release-manifest`; see [CLI contract](contracts/cli_contract.md).

---

### C) Risk Register

Flagship view. The existing [Risk register viewer](risk-and-security/risk_register_viewer.md) becomes one tab or mode inside this section.

**List view filters (for builders and reviewers):**

- Severity / criticality
- Coverage status (strict, waived, missing) — from RiskRegisterBundle.v0.1 `coverage_status`
- Evidence freshness
- Methods that claim mitigation — from method_risk_matrix and bundle
- Attack surface tags (comms, memory, tool selection, routing, market…) — from risk_registry risk_domain and policy

**Risk detail page (tri-pane, collapsible):**

1. **Risk narrative:** Definition, impact, invariants, detection signals (from risk_registry.v0.1.yaml and bundle `risks[]`)
2. **Controls:** Mitigations mapped to methods + enforcement points (shield, validator, router constraints); from bundle `controls[]` and `claimed_controls`
3. **Evidence:** Receipts, benchmark outcomes, waiver status; from bundle `evidence[]`, `evidence_refs`, `reproduce[]`

**Feature:** "Show me the chain" button opens the evidence graph for this risk (risk → receipts → runs → checks).

**Artifacts:** RISK_REGISTER_BUNDLE.v0.1.json; schema `policy/schemas/risk_register_bundle.v0.1.schema.json`. Build: `labtrust export-risk-register`, `labtrust build-risk-register-bundle`. See [Risk register](risk-and-security/risk_register.md), [Risk register contract](contracts/risk_register_contract.v0.1.md).

---

### D) Benchmarks

Move from "leaderboard" to **explainable comparison**.

**Views:**

- **Suites:** e.g. coord_risk, security suite — from `policy/coordination/coordination_security_pack.v0.1.yaml`, pack presets (hospital_lab, hospital_lab_full, full_matrix)
- **Compare methods:** Deltas vs baseline, reliability (valid_rate, blocked_rate), cost (tokens/latency) — from pack_summary.csv, results.v0.2/v0.3
- **Scenario drilldown:** Per scenario, failure modes and traces — from run dirs and SECURITY/attack_results, coordination_risk_matrix

**Key feature: Method x Risk coverage heatmap**

- Evidence-grounded: cells link to exact evidence objects
- Missing cells show "what evidence would satisfy it" (contract from method_risk_matrix required_bench)
- Aligns with "coverage means evidence, not narration"

**Policy:** `policy/coordination/method_risk_matrix.v0.1.yaml`, `policy/coordination/coordination_security_pack.v0.1.yaml`, `policy/coordination/scale_configs.v0.1.yaml`, `policy/coordination/injections.v0.2.yaml`. CLI: `labtrust run-coordination-security-pack`, `labtrust show-pack-results`, `labtrust show-method-risk-matrix`. See [Method and pack matrix](risk-and-security/method_and_pack_matrix.md).

---

### E) Methods Atlas

Navigable UI over "how the coordination methods work" (the big doc as structured content).

**Method family pages:**

- Kernel-composed
- Market-based
- Hierarchical
- Decentralized / swarm
- LLM-based protocols
- MARL / learning

**Method detail:**

- Contract + invariants
- Authority boundary (LLM role, shield points)
- Inputs/outputs schemas
- Test matrix and reproducibility metadata
- Benchmark results for this method across releases

**Source:** `policy/coordination/coordination_methods.v0.1.yaml`; [How coordination methods work](coordination/coordination_methods_how_they_work.md); [Coordination methods](coordination/coordination_methods.md). Useful for both builders and reviewers (authority and validation explicit).

---

### F) Build & Verify (Control plane, gated)

Visible to all; **executable only for authorized users**.

**Panels:**

| Panel | Purpose | Repo / CLI |
|-------|---------|-------------|
| **Workflows** | Run required bench pack, package-release minimal/full, verify-release, build viewer-data/latest, publish public-data/latest + versioned folder | `run_required_bench_matrix` scripts; `package-release`; `verify-release`; `build_viewer_data_from_release.sh` |
| **Doctor** | Environment checks (python path, extras, versions, permissions, line endings); "paste log" support; deterministic AUDIT_SELF_CHECK.json linked to run | `labtrust audit-selfcheck` |
| **Claims Regression** | Latest paper-facing snapshot and diff vs previous; require explicit "claims update" annotation to publish | Future; anchor in control plane |
| **Research Surface** | Reserved injectors status (implemented / noop); injection pack runs; detection/containment eval | policy/coordination/injections, security suite, run-coordination-security-pack |

Control-plane actions either shell out to CLI (local-first) or call a future runner API; portal still reads artifacts the same way.

---

## 5. Trust Boundary

**Public (read-only):**

- Reads `public-data/<channel>/latest.json` (or viewer-data/latest equivalent)
- Loads bundle, manifest, benchmark index, receipts (redacted as needed)
- Runs client-side verification (hash + signature)

**Restricted (write/execute):**

- Any action that: runs code, signs releases, calls LLM backends, uploads artifacts, mutates public-data/latest

**Implementation options:**

- Control-plane buttons only appear after login; or
- Buttons appear disabled with message "requires maintainer access"

A future runner service sits behind auth and only produces artifacts; the portal reads artifacts the same way.

---

## 6. URL and Layout Conventions

### Routes (stable, predictable)

| Route | Object |
|-------|--------|
| `/releases/:id` | Release |
| `/risks/:risk_id` | Risk |
| `/methods/:method_id` | Method |
| `/benchmarks/:suite/:run_id` | Benchmark run/suite |
| `/evidence/:evidence_id` | Evidence item |
| `/waivers/:waiver_id` | Waiver |
| `/build` | Control plane (gated) |
| `/compare?release=a&release=b` | Compare releases |

### Layout

- **Top bar:** Release selector + lens selector + search
- **Left sidebar:** Section nav (content varies by lens)
- **Main:** Content
- **Right drawer:** "Integrity / provenance" panel (always available) — keeps trust metadata visible without cluttering content

---

## 7. Search

Global search should index:

- Risks (title, tags)
- Methods (family, llm_based)
- Evidence (type, linked risk IDs)
- Waivers
- Scenarios
- Releases

**Requirement:** Search results show **release context** (which version produced this object) to avoid confusion.

---

## 8. Build Plan (Milestones)

### Milestone 1: Public data plane (2–3 weeks)

- Home (latest)
- Releases list + release detail
- Risk Register list + risk detail
- Benchmarks suite page + method compare
- Integrity verification panel

### Milestone 2: Methods Atlas + Evidence Graph

- Method pages; embed "How methods work" as navigable sections
- Evidence graph explorer (risk → receipts → runs → checks)

### Milestone 3: Control plane

- Workflows UI that shells out to CLI (local-first) or to a runner
- Doctor / selfcheck
- Claims regression UI

---

## 9. Lovable / Implementation Structure

In Lovable (or any single frontend project), structure as:

- **`src/app/public/…`** — Read-only data plane routes
- **`src/app/control/…`** — Gated control plane routes
- **Shared:** `src/lib/artifacts/` — Schemas, loaders, hash verification, indexing

Keep it **pure frontend initially**: control plane generates exact commands and validates outputs once pasted/loaded. Later, swap in a runner API without changing the portal’s conceptual model.

**Deployment:** Standard web app; sync and host externally as needed (e.g. static hosting + CI publishing of public-data). GitHub as backbone; existing `viewer-data-from-release` and `docs` workflows show the pattern.

### Portal live data connection

When the portal is deployed (e.g. via Lovable on a custom domain), **Live** mode fetches data from this repo’s deployed viewer-data. Configure the portal as follows:

- **Environment variable:** `VITE_DATA_BASE_URL`  
  The portal’s `getBaseUrl()` uses this for live mode (with trailing-slash normalization). If unset, it falls back to `/public-data/<channel>`.

- **Value:** The base URL where `viewer-data/latest/` is publicly served. This repo deploys that folder via the **Docs** workflow (`.github/workflows/docs.yml`), which runs `scripts/build_viewer_data_from_release.sh` and copies `viewer-data/` into the site before deploy. The public URL is:
  - **`https://<owner>.github.io/<repo>/viewer-data/latest/`**  
  Replace `<owner>` and `<repo>` with the GitHub org/user and repository name (e.g. `https://our-org.github.io/LabTrust-Gym/viewer-data/latest/`). Include the trailing slash.

- **Where to set:** In the Lovable project (or the platform Lovable deploys to), set `VITE_DATA_BASE_URL` in the **build** environment so it is available when `vite build` runs. Then redeploy. Switching the UI to **Live** (and channel **latest**) will fetch `latest.json` and the risk register bundle from that URL.

- **Verification:** After deploy, open the portal, switch to Live + latest, and confirm the risk register (and any other data from the pointer) loads. In DevTools → Network, requests should go to `{VITE_DATA_BASE_URL}latest.json` and `{VITE_DATA_BASE_URL}RISK_REGISTER_BUNDLE.v0.1.json`. Ensure the Docs workflow has run on `main` so that URL is populated.

---

## 10. Acid Test

A single question determines whether the structure is correct:

> Can a reviewer click from a **claim** → the **risk** it addresses → the **evidence** → the **benchmark run** → the **release manifest** → **hash/signature verification**, without ever leaving the site or encountering "trust me"?

If yes, one site is not only possible — it’s better than two.

---

## 11. Repo Reference Quick Links

| Concept | Location / command |
|--------|--------------------|
| Risk register bundle | `RISK_REGISTER_BUNDLE.v0.1.json`; schema `policy/schemas/risk_register_bundle.v0.1.schema.json` |
| Risk registry | `policy/risks/risk_registry.v0.1.yaml` |
| Waivers | `policy/risks/waivers.v0.1.yaml` |
| Method–risk matrix | `policy/coordination/method_risk_matrix.v0.1.yaml` |
| Coordination methods | `policy/coordination/coordination_methods.v0.1.yaml` |
| Pack matrix / presets | `policy/coordination/coordination_security_pack.v0.1.yaml`; scale_configs.v0.1.yaml, injections.v0.2.yaml |
| Evidence bundle | EvidenceBundle.v0.1 dirs; manifest schema `policy/schemas/evidence_bundle_manifest.v0.1.schema.json` |
| Release manifest | MANIFEST.v0.1.json, RELEASE_MANIFEST.v0.1.json |
| Viewer-data latest | `viewer-data/latest/latest.json` + bundle; build: `scripts/build_viewer_data_from_release.sh` |
| Export risk register | `labtrust export-risk-register --out <dir> [--runs ...]` |
| Validate coverage | `labtrust validate-coverage --strict` |
| Package release | `labtrust package-release --profile minimal|paper_v0.1 --out <dir>` |
| Verify release | `labtrust verify-release --release-dir <dir> [--strict-fingerprints]` |
| Run pack | `labtrust run-coordination-security-pack --out <dir> --matrix-preset full_matrix|hospital_lab|hospital_lab_full`; optional `--scale-ids small_smoke` (one scale at a time). |
| Audit selfcheck | `labtrust audit-selfcheck --out <dir>` |
| Frozen contracts | [frozen_contracts.md](contracts/frozen_contracts.md) |
| CLI contract | [cli_contract.md](contracts/cli_contract.md) |
| UI data contract | [ui_data_contract.md](contracts/ui_data_contract.md) |

---

## 12. Existing Viewer and Data Loader

The current **Risk register viewer** (`viewer/`) already implements:

- **Loader:** Local file, zip (with RISK_REGISTER_BUNDLE.v0.1.json), URL, or "Load latest release" (viewer-data/latest/latest.json → bundle).
- **API:** `loadRiskRegisterBundle(source)` → Promise<Bundle>; minimal shape validation (bundle_version, risks).
- **UX:** Global search, faceted filters (risk_domain, applies_to, coverage_status, has evidence, failed evidence), risk detail with definition → controls → evidence → reproduce commands.

The portal should either **reuse** this loader and UX patterns for the Risk Register section or **replace** the standalone viewer with the portal’s Risk Register view, keeping the same data contract and bundle shape.

---

*This document is the single source of context for building the LabTrust Portal. Update it when new sections, artifacts, or gates are added.*
