# Systems and threat model

This page summarises the LabTrust-Gym **system** and **threat model**, and states how the design applies beyond the current domain. Lab terminology: **hospital lab** (broad), **pathology lab** (more precise), **blood sciences lab/lane** (most precise—what we model); see [Glossary – Lab terminology](../reference/glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab).

## System summary

LabTrust-Gym is a **multi-agent simulation environment** (PettingZoo/Gym style) for hospital lab automation. The implemented workflow is a **blood sciences lane** (a type of pathology lab). The core provides:

- A **policy-driven trust skeleton**: RBAC, signed actions, an append-only hash-chained audit log, invariants, and reason codes. All of this is configured via versioned YAML/JSON under `policy/` and validated against schemas.
- **Benchmarks and studies** for throughput, safety, and coordination (e.g. throughput_sla, adversarial_disruption, insider_key_misuse, coord_scale, coord_risk). Golden scenarios define correctness; the simulator is correct when the golden suite passes.

The engine enforces invariants and blocks unsafe actions with explicit reason codes; there is no silent failure. See [Architecture](architecture.md) and [Frozen contracts](../contracts/frozen_contracts.md) for technical detail.

## Threat model

The design aims to enforce specific **trust and safety properties** in simulation and benchmarking. This is not a production security audit.

See [Threat model](threat_model.md) for the full list of properties: audit integrity, token lifecycle, reason codes, emits vocabulary, and runtime control (SYSTEM + RBAC + signature for UPDATE_ROSTER, INJECT_SPECIMEN). Deployment, key management, and operational security are the responsibility of integrators.

## Applicability to other settings

This design is **motivated by hospital labs** (broadly) and **pathology labs** (specimens, devices, QC, transport). The same trust skeleton and policy-as-data approach are **applicable to other self-driving labs and cyber-physical settings** (e.g. warehouse, factory, field operations): roles, audit, invariants, and signed control map to any multi-agent workflow where accountability and safety are required.

- To add another domain (e.g. warehouse, factory), provide a workflow spec and a domain adapter that implements the runner interface. See [Workflow / domain spec](workflow_domain_spec.md).
- For a roadmap on extending the platform to other organisations and workflows without losing the blood sciences (pathology lab) core, see [Forker guide](../getting-started/forkers.md).

## Out of scope

Deployment, key management, and operational security are the responsibility of integrators. The threat model document describes what the *simulation* enforces, not production hardening.
