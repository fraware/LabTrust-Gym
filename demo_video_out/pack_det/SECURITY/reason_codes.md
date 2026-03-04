# Reason codes (from reason_code_registry)

TOOL/COORD/MEM and related security-relevant codes.

| Code | Namespace | Severity | Description |
|------|-----------|----------|--------------|
| ADV_INJECTION_DETECTED | ADV | P2_HOLD_REVIEW | Adversarial or prompt-injection pattern detected in observat |
| ADV_JAILBREAK_PATTERN | ADV | P1_QUARANTINE | Jailbreak-style pattern detected (ignore instructions, etc.) |
| ADV_SUSPECTED_EXFIL | ADV | P1_QUARANTINE | Suspected data exfiltration pattern in input. |
| COORD_REPLAY_DETECTED | COORD | P0_STOP | Coordination message nonce already seen; replay rejected. |
| COORD_SENDER_NOT_AUTHORIZED | COORD | P0_STOP | Coordination message sender not authorized for this message  |
| COORD_SHIELD_REJECT_COLLISION | COORD | P0_STOP | Shield rejected plan: two agents would occupy same zone at s |
| COORD_SHIELD_REJECT_RBAC | COORD | P0_STOP | Shield rejected plan: agent action forbidden by RBAC or rest |
| COORD_SHIELD_REJECT_RESTRICTED | COORD | P0_STOP | Shield rejected plan: restricted edge used without token (IN |
| COORD_SIGNATURE_INVALID | COORD | P0_STOP | Coordination message signature verification failed (forged o |
| COORD_STALE_VIEW | COORD | P3_WARN | Agent acted on a view older than max_staleness_ms for a crit |
| MEM_POISON_DETECTED | MEM | P0_STOP | Poison or instruction-override pattern detected in memory co |
| MEM_RETRIEVAL_FILTERED | MEM | P3_WARN | Retrieval returned fewer results due to poison/instruction f |
| MEM_WRITE_SCHEMA_FAIL | MEM | P0_STOP | Memory entry failed schema or policy (allowed fields, max le |
| MEM_WRITE_UNAUTHENTICATED | MEM | P0_STOP | Memory write rejected: missing or invalid writer signature ( |
| TOOL_ARG_RANGE_FAIL | TOOL | P0_STOP | Tool call arguments failed range/semantic validation (min/ma |
| TOOL_ARG_SCHEMA_FAIL | TOOL | P0_STOP | Tool call arguments failed structural validation (missing re |
| TOOL_DATA_CLASS_VIOLATION | TOOL | P0_STOP | Tool output contained PII/PHI/IP or restricted data class no |
| TOOL_EGRESS_DENIED | TOOL | P0_STOP | Tool output attempted egress to non-allowlisted endpoint (de |
| TOOL_EGRESS_LIMIT_EXCEEDED | TOOL | P0_STOP | Tool output exceeded max bytes or max records limit (boundar |
| TOOL_EXEC_EXCEPTION | TOOL | P0_STOP | Tool execution raised an exception (non-fatal; converted to  |
| TOOL_NOT_ALLOWED_FOR_ROLE | TOOL | P0_STOP | Tool is in registry but not allowed for this agent/role by s |
| TOOL_NOT_IN_REGISTRY | TOOL | P0_STOP | Tool call references a tool_id not in the signed Tool Regist |
| TOOL_OUTPUT_MALFORMED | TOOL | P0_STOP | Tool returned output that failed schema or structural valida |
| TOOL_SELECTION_ERROR | TOOL | P4_METRIC | Tool call allowed by registry and RBAC but inapplicable for  |
| TOOL_TIMEOUT | TOOL | P0_STOP | Tool execution exceeded timeout (simulated or real). |