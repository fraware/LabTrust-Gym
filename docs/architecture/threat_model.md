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
