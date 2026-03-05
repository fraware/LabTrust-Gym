# Security coverage

Risk -> control -> tests -> artifacts mapping (from security_attack_suite).

## Layers

Each attack in coverage.json has a `layer` (`agent_shield` or `system`) and `uses_env` (true for coord_pack_ref). Filter by layer for agent-only vs system-level evidence.

## Risk to controls

- **R-CAP-001** (Jailbreak attacks)
  - Controls: CTRL-LLM-SHIELD
  - Attacks: SEC-PI-001, SEC-PI-002, SEC-PI-003, SEC-PI-004, SEC-PI-005, SEC-PI-006, SEC-PI-007, SEC-PI-008, SEC-PI-009, SEC-PI-010, SEC-PI-011, SEC-PI-012, SEC-PI-013, SEC-PI-014, SEC-PI-017, SEC-PI-018, SEC-PI-019, SEC-PI-015, SEC-PI-016, SEC-PI-020, SEC-PI-021, SEC-LLM-ATTACK-001, SEC-LLM-ATTACK-002, SEC-LLM-ATTACK-003, SEC-LLM-ATTACK-004, SEC-LLM-ATTACK-005, SEC-LLM-ATTACK-006, SEC-LLM-ATTACK-007, SEC-LLM-ATTACK-008, SEC-LLM-ATTACK-009, SEC-LLM-ATTACK-010

- **R-COMMS-001** (Identity spoofing (agent impersonation))
  - Controls: CTRL-COORD-IDENTITY
  - Attacks: SEC-COORD-001, SEC-COORD-RT-001

- **R-COMMS-002** (Agent communication poisoning)
  - Controls: CTRL-DETECTOR-ADVISOR, CTRL-COORD-IDENTITY
  - Attacks: SEC-DETECTOR-001, SEC-COORD-MATRIX-001

- **R-COORD-001** (Coordination security pack (multi-agentic combine path))
  - Controls: CTRL-COORD-IDENTITY
  - Attacks: SEC-COORD-PACK-MULTI-AGENTIC

- **R-DATA-001** (Untrusted Data Exchange Risk)
  - Controls: CTRL-OBSERVABILITY
  - Attacks: SEC-OBS-001, SEC-DATA-PROV-001

- **R-DATA-002** (Data poisoning (train/run-time))
  - Controls: CTRL-MEMORY
  - Attacks: SEC-DATA-PROV-002

- **R-DATA-003** (Memory poisoning (long-horizon state))
  - Controls: CTRL-MEMORY
  - Attacks: SEC-MEM-001

- **R-FLOW-001** (Action Inefficiency Risk)
  - Controls: CTRL-OBSERVABILITY
  - Attacks: SEC-FLOW-INEF-001

- **R-FLOW-002** (Action Progress Risk)
  - Controls: CTRL-OBSERVABILITY
  - Attacks: SEC-FLOW-PROGRESS-001

- **R-SYS-002** (Agent collusion (multi-agent))
  - Controls: CTRL-COORD-IDENTITY
  - Attacks: SEC-COORD-RT-002

- **R-TOOL-001** (Tool Selection Errors)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-SELECT-001

- **R-TOOL-002** (Tool Execution Failure)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-EXECFAIL-001

- **R-TOOL-003** (Unverified Tool Risk)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-UNVERIFIED-001

- **R-TOOL-004** (Tool Misuse Risk)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-MISUSE-001

- **R-TOOL-005** (Function Call Misparameterization)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-MISPARAM-001, SEC-TOOL-MISPARAM-FUZZ-001, SEC-TOOL-MISPARAM-LLM-001

- **R-TOOL-006** (Tool Vulnerability Exploitation Risk)
  - Controls: CTRL-TOOL-SANDBOX
  - Attacks: SEC-TOOL-001, SEC-TOOL-002, SEC-TOOL-003, SEC-TOOL-DATACLASS-001

## Control to tests
- **CTRL-COORD-IDENTITY** (Signed coordination and replay protection): tests.test_coordination_identity_bus, tests.test_coord_red_team_definitions, tests.test_coord_red_team_definitions, SEC-COORD-MATRIX-001, SEC-COORD-PACK-MULTI-AGENTIC
- **CTRL-DETECTOR-ADVISOR** (LLM detector throttle advisor): tests.test_detector_advisor_taskh
- **CTRL-LLM-SHIELD** (LLM shield and constrained decoding): PI-SPECIMEN-001, PI-SPECIMEN-002, PI-TRANSPORT-001, PI-TRANSPORT-002, PI-V02-UNTRUSTED-001, PI-SPECIMEN-005, PI-SPECIMEN-006, PI-SPECIMEN-007, PI-SPECIMEN-008, PI-SCENARIO-004, PI-SPECIMEN-009, PI-SPECIMEN-010, PI-DETECTOR-BYPASS-001, PI-SPECIMEN-011, PI-EVASION-HOMOGLYPH, PI-EVASION-B64, PI-EVASION-SPLIT, PI-CHAIN-001, PI-MULTITURN-001, PI-SPECIMEN-012, SEC-PI-021, SEC-LLM-ATTACK-001, SEC-LLM-ATTACK-002, SEC-LLM-ATTACK-003, SEC-LLM-ATTACK-004, SEC-LLM-ATTACK-005, SEC-LLM-ATTACK-006, SEC-LLM-ATTACK-007, SEC-LLM-ATTACK-008, SEC-LLM-ATTACK-009, SEC-LLM-ATTACK-010
- **CTRL-MEMORY** (Memory hardening and poison filtering): tests.test_memory_hardening, tests.test_data_provenance_r_data_002::test_poisoned_observation_blocked_or_constrained
- **CTRL-OBSERVABILITY** (Observability and forensic freeze): tests.test_flow_risks::test_flow_inefficiency_metrics_computed, tests.test_flow_risks::test_flow_progress_no_release_zero_throughput, tests.test_export_receipts, tests.test_export_receipts::test_evidence_bundle_manifest_has_tool_registry_fingerprint
- **CTRL-TOOL-SANDBOX** (Tool sandbox and egress limits): tests.test_tool_sandbox, tests.test_tool_sandbox::test_tool_sandbox_stress_egress_and_caps, tests.test_tool_sandbox::test_unregistered_tool_denied, tests.test_tool_sandbox::test_data_class_violation_phi_not_allowed, tests.test_tool_sandbox::test_unregistered_tool_denied, tests.test_tool_execution_failure, tests.test_llm_misparam_rejected, tests.test_tool_arg_fuzz, SEC-TOOL-MISPARAM-LLM-001, tests.test_tool_sandbox::test_tool_misuse_wrong_device_blocked, tests.test_tool_sandbox::test_tool_selection_wrong_tool_blocked_by_registry

## Artifacts
- SECURITY/attack_results.json
- receipts/