# Security coverage

Risk -> control -> tests -> artifacts mapping (from security_attack_suite).

## Risk to controls

- **R-CAP-001** (Jailbreak attacks)
  - Controls: CTRL-LLM-SHIELD
  - Attacks: SEC-PI-001, SEC-PI-002, SEC-PI-003, SEC-PI-004, SEC-PI-005, SEC-PI-006, SEC-PI-007, SEC-PI-008, SEC-PI-009, SEC-PI-010, SEC-LLM-ATTACK-001, SEC-LLM-ATTACK-002, SEC-LLM-ATTACK-003, SEC-LLM-ATTACK-004

- **R-COMMS-001** (Identity spoofing (agent impersonation))
  - Controls: CTRL-COORD-IDENTITY
  - Attacks: SEC-COORD-001, SEC-COORD-RT-001

- **R-COMMS-002** (Agent communication poisoning)
  - Controls: CTRL-COORD-IDENTITY, CTRL-DETECTOR-ADVISOR
  - Attacks: SEC-DETECTOR-001, SEC-COORD-MATRIX-001

- **R-DATA-001** (Untrusted Data Exchange Risk)
  - Controls: CTRL-OBSERVABILITY
  - Attacks: SEC-OBS-001

- **R-DATA-003** (Memory poisoning (long-horizon state))
  - Controls: CTRL-MEMORY
  - Attacks: SEC-MEM-001

- **R-SYS-002** (Agent collusion (multi-agent))
  - Controls: CTRL-COORD-IDENTITY
  - Attacks: SEC-COORD-RT-002

- **R-TOOL-006** (Tool Vulnerability Exploitation Risk)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-001

## Control to tests
- **CTRL-COORD-IDENTITY** (Signed coordination and replay protection): tests.test_coordination_identity_bus, tests.test_coord_red_team_definitions, tests.test_coord_red_team_definitions, tests.test_coordination_security_pack::test_sec_coord_matrix_001_reduced_matrix
- **CTRL-DETECTOR-ADVISOR** (LLM detector throttle advisor): tests.test_detector_advisor_taskh
- **CTRL-LLM-SHIELD** (LLM shield and constrained decoding): PI-SPECIMEN-001, PI-SPECIMEN-002, PI-TRANSPORT-001, PI-TRANSPORT-002, PI-V02-UNTRUSTED-001, PI-SPECIMEN-005, PI-SPECIMEN-006, PI-SPECIMEN-007, PI-SPECIMEN-008, PI-SCENARIO-004, SEC-LLM-ATTACK-001, SEC-LLM-ATTACK-002, SEC-LLM-ATTACK-003, SEC-LLM-ATTACK-004
- **CTRL-MEMORY** (Memory hardening and poison filtering): tests.test_memory_hardening
- **CTRL-OBSERVABILITY** (Observability and forensic freeze): tests.test_export_receipts
- **CTRL-TOOL-SANDBOX** (Tool sandbox and egress limits): tests.test_tool_sandbox

## Artifacts
- SECURITY/attack_results.json
- receipts/