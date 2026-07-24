# Threat model

LabTrust-Gym is a simulation and benchmark environment. This section outlines the trust and safety properties the design aims to enforce in simulation and benchmarking. It supports assurance work; integrators still own production security audits and deployment hardening.

- **Audit integrity**: Append-only hash-chained log; chain break triggers forensic freeze. No silent mutation after BLOCKED.
- **Token lifecycle**: ACTIVE/EXPIRED/CONSUMED/REVOKED; single-use consumption; dual approval where required.
- **Reason codes**: Every BLOCKED, HOLD, REJECT must carry a reason code; missing reason code blocks with AUDIT_MISSING_REASON_CODE.
- **Emits**: Only vocabulary-listed event types may be emitted; unknown emits fail the golden suite.
- **Runtime control (UPDATE_ROSTER, INJECT_SPECIMEN)**: Always require SYSTEM agent_id, RBAC allowlist (R_SYSTEM_CONTROL), and a valid signature with the SYSTEM control key (ed25519:key_system_control). No bypass for strict_signatures; missing or wrong key → BLOCKED (SIG_MISSING, SIG_INVALID, or SIG_ROLE_MISMATCH). Step output includes control_decision (allowed, reason_code, role_id, signature_passed); logged and exported in evidence bundles.

Deployment, key management, and operational security are the responsibility of integrators.

**Trust boundary.** The benchmark runner, policy loaders, and process are **trusted** in the default threat model. Malicious or compromised runners, supply-chain attacks, and malicious policy sources sit outside that model. For high-assurance or hostile environments, add integrity verification for the runner and policy (for example signatures, TEE, or out-of-band verification). See [Optional integrity and supply-chain hardening](../risk-and-security/supply_chain_integrity.md).

**Out of scope:** Supply-chain attacks, compromised runner, and malicious policy are out of scope; integrators must address these if required.

## Verifier-assurance extension (LT-VA)

Optimization-aware verifier assurance adds attack surfaces beyond static policy misuse. See [ADR-VA-001](../adr/ADR-VA-001-dual-oracle-architecture.md), [ADR-VA-002](../adr/ADR-VA-002-claim-boundaries.md), and [docs/verifier_assurance/](../verifier_assurance/).

- **Optimization-induced verifier failure**: A policy trained against `V_public` may maximize public reward while violating process, authority, or side-effect constraints that only `V_hidden` checks. Terminal-state-only verifiers are especially exposed.
- **Label leakage**: Hidden adjudication labels, commitments salts, or process-boundary state must not appear in observations, logs, env vars, filesystem paths, exception text, sealed IPC public frames, or timing-sensitive public interfaces before freeze. Leakage suspicion fails closed (`indeterminate` / error), never silent acceptance.
- **Sealed process boundary**: Release-grade campaigns use a durable sealed hidden worker (length-prefixed IPC). Freeze tokens remain on the trusted parent; public surfaces receive commitments only until freeze.
- **Authorization attack surfaces**: Revoked/expired keys, replayed grants (token dual-approval mapping), cross-agent token transfer, authority expansion, policy rollback, verifier-service impersonation, approval laundering, collusion, revocation races, and stale auth caches. Controls live in existing token/RBAC/signature machinery; VA campaigns exercise them, they do not replace integrator IAM. PF-Core/OVK adapters are fail-closed: unavailable checker → `indeterminate`, never fabricated acceptance.
- **Claim boundary**: VA threat coverage is for simulation/research. It does not claim production clinical assurance. Causal/attribution graphs are a declared experimental model, not legal responsibility assignment.
