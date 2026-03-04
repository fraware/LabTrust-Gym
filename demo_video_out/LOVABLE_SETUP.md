# Lovable portal: using demo_video_out data

This directory contains the artifacts produced by the full demo pipeline. The Lovable-built LabTrust Portal can consume them in two ways: **Live** (from a URL) or **local/file** (from this repo).

## Option A: Live mode (deployed viewer-data)

When the portal is deployed and the Docs workflow has built and published `viewer-data/latest/`:

1. In the Lovable project (or the platform Lovable deploys to), set the **build** environment variable:
   - **Name:** `VITE_DATA_BASE_URL`
   - **Value:** `https://<owner>.github.io/<repo>/viewer-data/latest/`  
     Replace `<owner>` and `<repo>` with your GitHub org/user and repository (e.g. `https://github-user.github.io/LabTrust-Gym/viewer-data/latest/`). Include the trailing slash.

2. Rebuild and redeploy the portal.

3. In the UI, switch to **Live** and channel **latest**. The portal will fetch `latest.json` and the referenced `RISK_REGISTER_BUNDLE.v0.1.json` from that URL.

4. **Verification:** In DevTools → Network, requests should go to `{VITE_DATA_BASE_URL}latest.json` and `{VITE_DATA_BASE_URL}RISK_REGISTER_BUNDLE.v0.1.json`.

To populate `viewer-data/latest/` from this demo run, use the repo script (from repo root, Unix/macOS or WSL):

```bash
# From repo root; requires bash
scripts/build_viewer_data_from_release.sh
# Then copy viewer-data/latest/ into your Docs deploy or static host
```

Or build the risk register and place it where your static host serves it (see Option B for bundle location).

## Option B: Local / file mode (demo_video_out)

For local development or a demo that does not depend on a deployed URL:

1. **Risk register bundle (primary):**  
   Path: `demo_video_out/risk_out/RISK_REGISTER_BUNDLE.v0.1.json`  
   If the portal supports "Load from file" or "Load from URL", point it at this file (e.g. via a local static server or `file://` if the app allows it).

2. **Release UI bundle (run data + optional risk register):**  
   Path: `demo_video_out/release_ui_bundle.zip`  
   The portal may support loading a zip produced by `labtrust ui-export`. This zip contains `index.json`, `events.json`, `receipts_index.json`, `reason_codes.json` and is the primary input for the UI per the [UI data contract](../docs/contracts/ui_data_contract.md). If the portal can inject the risk register into the same zip or load both zip and bundle, use:
   - `demo_video_out/release_ui_bundle.zip` for run/event data
   - `demo_video_out/risk_out/RISK_REGISTER_BUNDLE.v0.1.json` for risk register

3. **Serving locally (e.g. for VITE_DATA_BASE_URL in dev):**  
   From repo root, run:
   ```powershell
   .\demo_video_out\build_viewer_data_latest.ps1
   ```
   This creates `demo_video_out/viewer_data_latest/` with `latest.json` and `RISK_REGISTER_BUNDLE.v0.1.json`. Serve that folder (e.g. `npx serve demo_video_out/viewer_data_latest -p 8080`) and set `VITE_DATA_BASE_URL` to `http://localhost:8080/` so the portal can load "latest" from localhost.

## Artifacts in this directory

| Artifact | Path | Use in portal |
|----------|------|----------------|
| Viewer-data layout (Live URL) | `viewer_data_latest/` (latest.json + bundle) | Serve this folder; set VITE_DATA_BASE_URL to its URL for Live mode |
| Risk register bundle | `risk_out/RISK_REGISTER_BUNDLE.v0.1.json` | Risks, controls, evidence, coverage status |
| Release UI bundle | `release_ui_bundle.zip` | Run index, events, receipts index, reason codes |
| Release dir | `release/` | Full release (receipts, EvidenceBundles, MANIFEST); for verify-release and deep links |
| Pack summary | `coord_pack/pack_summary.csv` | Coordination method × scale × injection metrics |
| Pack gate | `coord_pack/pack_gate.md` | Per-cell PASS/FAIL/not_supported |
| Lab report | `coord_pack/LAB_COORDINATION_REPORT.md` | Stakeholder-facing coordination summary |

## Reference

- [LabTrust Portal context](../docs/labtrust-portal-context.md) — Portal vision, data plane, and live data connection.
- [UI data contract](../docs/contracts/ui_data_contract.md) — Schema and layout for ui-export and portal input.
- [Risk register contract](../docs/contracts/risk_register_contract.v0.1.md) — RISK_REGISTER_BUNDLE.v0.1 schema.
