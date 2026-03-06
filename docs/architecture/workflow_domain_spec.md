# Workflow / domain spec

This document describes the **workflow or domain spec** (v0.1): an abstract schema for resources, locations, constraints, and allowed actions that are independent of a specific sector. The first concrete instance is a **pathology lab**—specifically a **blood sciences** lane (hospital lab in the broad sense). Future domains (e.g. warehouse, factory) can be added by providing a spec and an adapter that maps the spec to the engine (or a thin variant of the engine). See [Glossary – Lab terminology](../reference/glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab).

## Schema

The schema is defined in `policy/schemas/workflow_spec.v0.1.schema.json`. A workflow spec has:

- **workflow_id**: Unique identifier (e.g. `hospital_lab`, `warehouse_pick`).
- **version**: Spec version (e.g. `0.1`).
- **resources**: List of abstract resource types (e.g. specimen, order, pallet) with optional descriptions.
- **locations**: List of location or zone identifiers (e.g. reception, corridor, device zones).
- **constraints**: Optional domain constraints (capacity, connectivity, safety).
- **allowed_actions**: List of allowed action type identifiers (e.g. move, process, handoff).

Specs are JSON or YAML. They are validated against the schema when loaded. The engine and runner do not interpret the spec directly; a **domain adapter** maps the spec (and domain-specific state) to engine actions and state.

## First instance: pathology lab (blood sciences lane)

The reference implementation is a **blood sciences lab** (pathology lab). The domain is registered as `hospital_lab` in code. A minimal lab workflow spec might look like:

```yaml
workflow_id: hospital_lab
version: "0.1"
resources:
  - resource_type: specimen
    description: Lab specimen (e.g. tube, plate)
  - resource_type: order
    description: Work order or request
locations:
  - location_id: reception
  - location_id: corridor
  - location_id: device_zone
constraints: []
allowed_actions:
  - move
  - process
  - handoff
  - create_accession
  - qc_check
```

The **lab adapter** (see below) maps these to the existing engine action set and state (zones, devices, tokens, audit log) for the blood sciences lane. Other domains would provide their own adapter and spec.

## Domain adapter layer

The codebase provides a **domain adapter** registry in `src/labtrust_gym/domain/`: a factory (given a workflow spec and config) returns a `LabTrustEnvAdapter` that the golden runner and benchmark runner use. The interface is in `src/labtrust_gym/domain/adapter.py` (`DomainAdapterFactory` protocol); the blood sciences (pathology lab) implementation is in `src/labtrust_gym/domain/lab_adapter.py` and registered under `hospital_lab` in `src/labtrust_gym/domain/registry.py`. Forkers can call `register_domain(domain_id, factory)` to add a new domain; `get_domain_adapter_factory(domain_id)` resolves the factory.

A **domain adapter** (the factory’s return value) implements the runner’s `LabTrustEnvAdapter` interface so that:

1. **Reset**: Initialize state for a new episode (from the workflow spec and scale/config).
2. **Step**: Accept an event and return the next state, emits, violations, and hashchain in the runner output contract shape.
3. **Query**: Return current state or metrics for the runner (e.g. for scenario assertions).

The `hospital_lab` (blood sciences) factory returns `CoreEnv()`, which already implements `LabTrustEnvAdapter`. A forker adding a new domain (e.g. warehouse) would:

1. Define a workflow spec (YAML/JSON) conforming to `workflow_spec.v0.1.schema.json`.
2. Implement an adapter that maps the spec and domain state to engine actions and state (or to a thin variant of the engine).
3. Register the adapter under a **domain_id** (see Extension points).

## Extension points and policy layout

Forkers can add a new domain without forking the core engine by:

1. **Registry**: Register `domain_id -> factory` via `register_domain(domain_id, factory)` in `src/labtrust_gym/domain/registry.py`. The runner selects the adapter by `domain_id` (e.g. from CLI `--domain hospital_lab` or from policy) using `get_domain_adapter_factory(domain_id)`.
2. **Policy layout**: Place domain-specific policy under `policy/domains/<domain_id>/` (e.g. emits, reason codes, catalogue, zone layout). The loader resolves base policy plus optional `policy/domains/<domain_id>/` when that domain is active. A shared abstract vocabulary (e.g. common reason codes) can live in base policy; domain-specific extensions in `policy/domains/<domain_id>/`.

When `domain_id` is set, the runner and `validate-policy` use `load_policy_for_domain(root, domain_id, partner_id)` so that policy is merged from base policy plus `policy/domains/<domain_id>/`. Without a domain_id, the lab uses the existing `policy/` layout only.

## Status

- **Schema**: `workflow_spec.v0.1.schema.json` is defined and can be used to validate workflow specs.
- **Adapter interface and lab adapter**: `src/labtrust_gym/domain/` provides `DomainAdapterFactory` (protocol), `lab_domain_adapter_factory` (returns `CoreEnv()`), and a registry mapping `domain_id` to factory. The runner can resolve an adapter via `get_domain_adapter_factory("hospital_lab")` and build an env from a workflow spec and config.
- **Registry**: Implemented in `src/labtrust_gym/domain/registry.py`; forkers can `register_domain(domain_id, factory)` to add new domains. The runner and CLI resolve the adapter via `get_domain_adapter_factory(domain_id)`.
- **Policy layout (policy/domains/)**: `load_policy_for_domain(root, domain_id=None, partner_id=None)` in `src/labtrust_gym/policy/loader.py` loads base policy via `load_effective_policy`, then when `policy/domains/<domain_id>/` exists loads all YAML files from that directory. Returns `(effective_policy, fingerprint, partner_id, calibration_fingerprint, domain_overrides)`. Call sites (runner, validate_policy) use this when `domain_id` is set. Domain-specific emits, reason codes, and catalogue live under that path; merge rules are application-specific (domain_overrides extend or override base for keys explicitly loaded).

## See also

- [Forker guide](../getting-started/forkers.md) – Path C (domain abstraction).
- [Architecture](architecture.md) – engine and runner overview.
- [Forker guide](../getting-started/forkers.md) – extending the repo.
