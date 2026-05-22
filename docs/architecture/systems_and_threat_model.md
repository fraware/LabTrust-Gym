# Systems and threat model

This page summarises the LabTrust-Gym **system** and **threat model**, and states how the design applies beyond the current domain. Lab terminology runs from **hospital lab** (broad) to **pathology lab** (more precise) to **blood sciences lab/lane** (most precise, what we model). See [Glossary – Lab terminology](../reference/glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab).

## System summary

LabTrust-Gym is a **multi-agent simulation environment** (PettingZoo/Gym style) for hospital lab automation. The implemented workflow is a **blood sciences lane** (a type of pathology lab). The core provides:

- A **policy-driven trust skeleton**: RBAC, signed actions, an append-only hash-chained audit log, invariants, and reason codes. All of this is configured via versioned YAML/JSON under `policy/` and validated against schemas.
- **Benchmarks and studies** for throughput, safety, and coordination (e.g. throughput_sla, adversarial_disruption, insider_key_misuse, coord_scale, coord_risk). Golden scenarios define correctness; the simulator is correct when the golden suite passes.

The engine enforces invariants and blocks unsafe actions with explicit reason codes; there is no silent failure. See [Architecture](architecture.md) and [Frozen contracts](../contracts/frozen_contracts.md) for technical detail.

## Threat model

The design aims to enforce specific **trust and safety properties** in simulation and benchmarking. Production security audits and operational controls remain integrator responsibilities.

See [Threat model](threat_model.md) for the full list of properties, including audit integrity, token lifecycle, reason codes, emits vocabulary, and runtime control (SYSTEM + RBAC + signature for UPDATE_ROSTER and INJECT_SPECIMEN). Integrators own deployment, key management, and operational security.

## Applicability to other settings

This design is **motivated by hospital labs** (broadly) and **pathology labs** (specimens, devices, QC, transport). The same trust skeleton and policy-as-data approach apply to other self-driving labs and cyber-physical settings (for example warehouse, factory, field operations), where roles, audit, invariants, and signed control support accountability and safety.

- To add another domain (e.g. warehouse, factory), provide a workflow spec and a domain adapter that implements the runner interface. See [Workflow / domain spec](workflow_domain_spec.md).
- For a roadmap on extending the platform to other organisations and workflows without losing the blood sciences (pathology lab) core, see [Forker guide](../getting-started/forkers.md).

## Out of scope

Integrators own deployment, key management, and operational security. The threat model document describes what the simulation enforces; production hardening sits in integrator runbooks and controls.
