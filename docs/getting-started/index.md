# Getting started

Get LabTrust-Gym installed, run your first benchmarks, and optionally fork and extend for your organization.

## I want to...

| I want to... | First step |
|--------------|------------|
| Run benchmarks only | `pip install labtrust-gym[env,plots]` then `labtrust quick-eval` |
| Add my coordination method (or task) | [Extension development](../agents/extension_development.md) + entry_points; see [examples/extension_example](https://github.com/fraware/LabTrust-Gym/tree/main/examples/extension_example) for a minimal plugin |
| Fork and customize policy | [Forker guide](forkers.md) and `labtrust forker-quickstart` |
| Use as a library without forking | [Extension development](../agents/extension_development.md) + `--profile` + `extension_packages` in a lab profile |
| Run the full security suite | `labtrust run-security-suite`; full suite needs `.[env]`; use `--skip-system-level` when env is not installed |
| Connect the LabTrust Portal (Lovable) to live data | Set `VITE_DATA_BASE_URL` in the portal to this repo’s deployed viewer-data URL; see [Portal context — Portal live data connection](../labtrust-portal-context.md#portal-live-data-connection) |
| Export a UI bundle (tables + coordination charts) for the portal | `labtrust ui-export --run <dir> --out <zip>`; when run has coordination pack output, zip includes SOTA leaderboards and **coordination/graphs/** HTML charts. See [Frontend handoff](../reference/frontend_handoff_ui_bundle.md). |

## New to the project

| Document | Description |
|----------|-------------|
| [Installation](installation.md) | Pip install, extras, environment variables, development setup. |
| [Build your own agent](build_your_own_agent.md) | Implement an agent and run it with `eval-agent` (5–10 min). |
| [Example agents](example_agents.md) | Reference agents and run commands. |
| [Example experiments](example_experiments.md) | Reproducible experiments (trust vs performance). |

## Forkers and operators

| Document | Description |
|----------|-------------|
| [Forker guide](forkers.md) | Fork, customize policy, run the full pipeline, add partner overlays and coordination methods. |
| [Demo readiness](demo_readiness.md) | Prerequisites, Windows notes, and risk-register usage for the three presentation demos. |
| [Recommended Windows setup](windows_setup.md) | Path, shell, file-lock mitigation, and locale for Windows-only users. |
| [Troubleshooting](troubleshooting.md) | Common issues and fixes. |

## Next steps

- [Repository structure](../reference/repository_structure.md) — where to put outputs and how the repo is laid out.
- [Architecture](../architecture/index.md) — system design and threat model.
- [Benchmarks](../benchmarks/index.md) — tasks, studies, and reproduction.
- [Frontend handoff (UI bundle)](../reference/frontend_handoff_ui_bundle.md) — for frontend engineers: zip layout, coordination_artifacts, and how to display SOTA tables and charts.
