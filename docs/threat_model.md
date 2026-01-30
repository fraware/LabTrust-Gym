# Threat model

LabTrust-Gym is a simulation and benchmark environment. This section outlines the trust and safety properties the design aims to enforce, not a production security audit.

- **Audit integrity**: Append-only hash-chained log; chain break triggers forensic freeze. No silent mutation after BLOCKED.
- **Token lifecycle**: ACTIVE/EXPIRED/CONSUMED/REVOKED; single-use consumption; dual approval where required.
- **Reason codes**: Every BLOCKED, HOLD, REJECT must carry a reason code; missing reason code blocks with AUDIT_MISSING_REASON_CODE.
- **Emits**: Only vocabulary-listed event types may be emitted; unknown emits fail the golden suite.

Deployment, key management, and operational security are the responsibility of integrators.
