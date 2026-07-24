# Architecture

System design, threat model, and workflow specification for LabTrust-Gym.

## Core design

| Document | Description |
|----------|-------------|
| [System overview](system_overview.md) | How the pieces fit together, including layering, env construction, per-step flow, golden vs benchmark runner, and CLI to components. |
| [Architecture](architecture.md) | High-level architecture and components. |
| [Hospital lab workflow (blood sciences)](hospital_lab_workflow.md) | High-level and detailed workflow views; deterministic vs LLM live pipeline. |
| [Systems and threat model](systems_and_threat_model.md) | System summary, threat model, applicability to other labs. |
| [Threat model](threat_model.md) | Detailed threat model (includes LT-VA verifier-assurance extension). |
| [Verifier Assurance (LT-VA)](../verifier_assurance/README.md) | Dual oracle, offline PPO, sealed IPC, campaign reconstruction; [architecture notes](../verifier_assurance/architecture.md). |
| [Diagrams](diagrams.md) | Architecture diagrams. |
| [Coordination and env data flow](../coordination/coordination_and_env.md) | Per-step flow (obs, mutate_obs, coord, mutate_actions, env.step); runner owns env. |
| [Simulation, LLMs, and agentic systems](simulation_llm_agentic.md) | How PettingZoo, LLM agents, and agentic coordination fit together; who uses the PZ env. |
| [Design choices log](design_choices.md) | Reference log of design choices for orchestration, scale, coordination, security, and backward compatibility. |

## Specification

| Document | Description |
|----------|-------------|
| [Workflow and domain spec](workflow_domain_spec.md) | Workflow and domain specification. |

## Design artifacts

Design-time YAML and schemas live under [design/](design/README.md) (policy pack examples, compiler contract, runtime enforcement API).
