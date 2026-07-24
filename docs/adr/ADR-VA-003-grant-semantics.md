# ADR-VA-003: Grant semantics for authorization attacks (LT-VA-11)

- **Status:** Accepted (LT-VA-00 foreshadow / LT-VA-11 binding)
- **Date:** 2026-07-24

## Context

Authorization attack campaigns refer to “replayed grants.” LabTrust-Gym already has token dual-approval and RBAC/signature machinery. Introducing a parallel grant object risks forking authority semantics.

## Decision

**Do not invent a separate production grant authority.** For VA-11:

- Map “grant” onto existing **token + dual-approval** objects (`TokenStore`, `validate_dual_approval`, key registry lifecycle).
- A VA **GrantRecord** is an explicit research adapter: immutable snapshot of `{token_id, approvals, key_ids, issued_ts, expires_ts, scope}` used for replay/race scenarios.
- “Replayed grant” means replaying a previously consumed/expired dual-approval token payload against the runtime, not a new crypto primitive.
- PF-Core adapter checks small machine-checked predicates over exported traces:
  - Prefer injected checker (tests) or real `pf_core` when importable.
  - Offline CI may use `LocalFakePFCoreChecker` (`allow_local_fake=True`) for completeness.
  - Unavailable / unknown predicates → `indeterminate` — never fabricated acceptance.
  - Do not invent a parallel predicate language in-repo.

## Consequences

- Attack fixtures speak in GrantRecord terms but bind to tokens underneath.
- Docs must not claim these adapters are hospital IAM products or that local fake PF-Core equals external machine-checked assurance.
