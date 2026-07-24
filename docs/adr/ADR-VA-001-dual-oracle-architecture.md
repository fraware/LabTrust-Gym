# ADR-VA-001: Dual-oracle architecture (`V_public` / `V_hidden`)

- **Status:** Accepted (LT-VA-00 / LT-VA-02)
- **Date:** 2026-07-24
- **Deciders:** LabTrust-Gym verifier-assurance program

## Context

Optimization-aware verifier assurance requires separating the signal available to policies/attackers from hidden ground truth used only for post-freeze adjudication. A single verifier that both trains policies and labels exploits collapses the evaluation.

## Decision

LabTrust-Gym implements a dual oracle:

1. **`V_public`** — process-boundary-visible verifier. Consumes only state declared in its verifier profile. Produces reward feedback and public accept/reject decisions.
2. **`V_hidden`** — trusted-kernel oracle. Inaccessible to policy workers, observations, logs, and public campaign artifacts while a campaign is active. Emits sealed label commitments; reveals adjudication only after campaign freeze according to policy.

### Boundary modes

| Mode | Use | Requirement |
|---|---|---|
| In-process façade | CI / unit tests | Hard API denial: no hidden attributes on env/`info`; leakage suite must fail closed |
| One-shot subprocess | Contract smoke | Fresh interpreter; sealed JSON payload; never imports policy code |
| Durable sealed worker | Release-grade campaigns | Long-lived subprocess + length-prefixed sealed IPC (`DurableSealedHiddenWorker`); commitments only until freeze; freeze token stays on trusted parent |

### Commitments

At episode end the kernel seals `commitment = H(hidden_adjudication || salt || campaign_id)`. Public packs carry commitments only until freeze allows private reveal packs.

## Consequences

- Positive: enables optimization against a public verifier while preserving independent exploit recovery.
- Negative: more engineering (IPC, leakage tests, commitment lifecycle).
- Compatibility: does not replace golden runner or PCS QC-release verifier; it adds a VA-specific dual path.

## Non-claims

This architecture does not constitute clinical validation, production assurance, or legal adjudication of responsibility.
