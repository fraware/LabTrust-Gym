# Latest release bundle (viewer)

This directory is populated by CI workflow **viewer-data-from-release**: it contains the risk register bundle and a `latest.json` pointer so the viewer can show "the risk register for the latest release artifact chain."

Contents (generated, not committed by default):

- `latest.json` — `{ "git_sha", "version", "generated_at", "bundle_file": "RISK_REGISTER_BUNDLE.v0.1.json" }`
- `RISK_REGISTER_BUNDLE.v0.1.json` — bundle built from package-release (minimal) + export-risk-register

The viewer can load this via "Load latest release" when served from a host that has this directory (e.g. GitHub Pages after the workflow runs and deploys).
