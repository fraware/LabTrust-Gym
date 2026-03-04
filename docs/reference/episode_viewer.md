# Episode / simulation viewer

The episode simulation viewer visualizes multi-agent PettingZoo steps and maps every action to the blood sciences (pathology lab) design. Use it to inspect runs, debug coordination, and verify that all lab stages (zones, devices, specimen lifecycle) are present and mappable.

## Purpose

- **Visualize** every step of an episode: actions per agent, status (ACCEPTED/BLOCKED), coordination decisions, violations, and optional LLM/security audit fields.
- **Expose the full blood sciences design**: all 10 zones in workflow order, 6 devices, and specimen status order so that every lab stage is visible and actions can be mapped to zones and equipment.
- **Offline-first**: load a single episode bundle JSON or raw JSONL files (episode log plus optional METHOD_TRACE and coord_decisions).

## Data sources

| Source | When produced | Contents |
|--------|----------------|----------|
| Episode log (JSONL) | Benchmark run with `log_path` set | One line per engine step (per agent): t_s, agent_id, action_type, status, args, emits, violations, etc. |
| METHOD_TRACE.jsonl | Run with coordination method and `run_dir` | One line per step: method_id, t_step, stage, hash_or_summary. |
| coord_decisions.jsonl | Run with coordination method and `log_path` | One line per step: method_id, t_step, actions, view_age_ms, safety_shield_applied, etc. |

The viewer groups episode log lines by `t_s` into steps and merges METHOD_TRACE and coord_decisions by step index. Lab design (zones, devices, specimen statuses) is defined in `src/labtrust_gym/logging/lab_design.py` and embedded in the bundle or used as a built-in default when loading raw JSONL.

## Building a bundle

From a run directory that contains at least an episode log (`episode_log.jsonl` or `logs/*.jsonl`):

```bash
labtrust build-episode-bundle --run-dir <path> [--out <path>]
```

If `--out` is omitted, the bundle is written to `<run-dir>/episode_bundle.json`. Alternatively use the script:

```bash
python scripts/build_episode_bundle.py --run-dir <path> [--episode-log <path>] --out <path>
```

The bundle (episode_bundle.v0.1) contains `version`, `lab_design`, `agents`, and `steps` (each step has `stepIndex`, `t_s`, `entries`, and optional `method_trace` and `coord_decision`). Lab design is taken from `src/labtrust_gym/logging/lab_design.py`; the builder lives in `src/labtrust_gym/export/episode_bundle.py`.

## Using the viewer

1. Serve the `viewer-episode/` directory (e.g. `python -m http.server 8765` from inside `viewer-episode/`) and open the URL in a browser. Or open `viewer-episode/index.html` directly (file://).
2. Click **Load demo** to load the built-in `demo_episode_bundle.json` (only works when served over HTTP). Or use **Load** to select:
   - An **episode_bundle.json** file (from the bundle builder), or
   - **Episode log** JSONL (required) plus optional METHOD_TRACE.jsonl and coord_decisions.jsonl.
3. Views: lab pipeline strip (all 10 zones), step x agent grid (sticky header), zone-centric table, detail panel (click a cell). Filters: agent, action type, status. The UI is desktop-optimized (full-height layout, clear typography).

See [viewer-episode/README.md](../../viewer-episode/README.md) for details.

## Lab design (single source of truth)

Zones, devices, and specimen status order are defined in `src/labtrust_gym/logging/lab_design.py` and aligned with the env (`pz_parallel.DEFAULT_ZONE_IDS`, `DEFAULT_DEVICE_IDS`, and the observation status order). The bundle builder embeds this in the bundle; the viewer uses it from the bundle or from a built-in default so the pipeline strip and zone-centric view always show all 10 zones in the same order.
