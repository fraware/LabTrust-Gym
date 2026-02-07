# Risk Register Viewer

Static, dataset-driven viewer for RiskRegisterBundle.v0.1. No hardcoded content: swap datasets (fixtures vs paper release) without changing UI code.

## Run

Open `index.html` in a browser (file:// or serve the `viewer/` directory). Load a bundle via:

- **Local file:** Choose a `RISK_REGISTER_BUNDLE.v0.1.json` (or a zip containing it).
- **URL:** Enter a URL to a bundle JSON (optional; offline-first default).

## Build a bundle

```bash
labtrust export-risk-register --out <dir> --runs ui_fixtures
# Then open <dir>/RISK_REGISTER_BUNDLE.v0.1.json in the viewer (file picker).
```

See [Risk register viewer](../docs/risk_register_viewer.md) for loader API and UX (search, filters, risk detail, reproduce commands).
