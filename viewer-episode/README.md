# Episode Simulation Viewer

Static, dataset-driven viewer for multi-agent simulation episodes. Shows all steps of the hospital lab design (10 zones in workflow order), step x agent grid, zone-centric view, and detail panel. Layout is desktop-optimized (full-height, sticky grid header, clear hierarchy). No hardcoded content: load an episode bundle or raw JSONL logs.

## Run

**Recommended:** Serve the directory over HTTP so the "Load demo" button works (demo bundle is loaded via fetch). From the repo root:

```bash
cd viewer-episode && python -m http.server 8765
```

Then open http://localhost:8765/ and click **Load demo** to view the built-in demo bundle.

You can also open `index.html` directly (file://); use the **Load** button to select `demo_episode_bundle.json` or your own bundle/log files.

## Load data

**Option 1 — Bundle (recommended)**  
Select an `episode_bundle.json` file produced by the bundle builder. Contains steps, agents, and lab design in one file.

Build a bundle from a run directory:

```bash
labtrust build-episode-bundle --run-dir <path> [--out <path>]
# or: python scripts/build_episode_bundle.py --run-dir <path> --out <path>
# Writes episode_bundle.json (default: <run-dir>/episode_bundle.json; or <out>/episode_bundle.json if --out is a dir)
```

**Option 2 — Raw JSONL**  
Select the episode log JSONL (required). Optionally select METHOD_TRACE.jsonl and coord_decisions.jsonl from the same run. The viewer parses and merges them client-side and uses a built-in lab design (all 10 zones, 6 devices).

## Producing logs

Run a benchmark with logging so the run directory contains at least an episode log:

- `labtrust run-benchmark --task throughput_sla --out <dir>` (writes logs under the output dir when configured)
- Or use `run_episode` with `log_path` and `run_dir` (see benchmark runner)

Episode log path is typically `episode_log.jsonl` or `logs/<task>.jsonl`; METHOD_TRACE.jsonl and coord_decisions.jsonl appear in the same directory when using a coordination method and run_dir.

## Views

- **Lab pipeline strip**: All 10 hospital lab zones in workflow order (Reception, Accessioning, Sorting, Preanalytics, Centrifuge, Aliquot, Analyzer A, Analyzer B, QC, Restricted). No zone is omitted.
- **Step x Agent**: Grid of simulation steps (rows) and agents (columns). Cell shows action type and status; color by action (NOOP/TICK grey, MOVE blue, QUEUE_RUN green, etc.) and status (BLOCKED red). Sticky header when scrolling. Click a cell to show full entry in the detail panel.
- **Zone-centric**: Table with zones in lab order; for each (zone, step) shows which agents and actions touch that zone (from MOVE args and device_id to zone).
- **Detail panel**: Full episode log entry (action_type, args, status, emits, violations, etc.) and optional method_trace and coord_decision for the selected step.

## Filters

Filter the grid by agent, action type, or status (ACCEPTED / BLOCKED).
