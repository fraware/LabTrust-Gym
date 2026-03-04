# Generalization and limits

What was tested, what was not, and how to compare with other benchmarks.

## What was tested

### Scale grid

The coordination benchmark uses scale configs defined in [policy/coordination/scale_configs.v0.1.yaml](https://github.com/fraware/LabTrust-Gym/blob/main/policy/coordination/scale_configs.v0.1.yaml). The study spec ([policy/coordination/coordination_study_spec.v0.1.yaml](https://github.com/fraware/LabTrust-Gym/blob/main/policy/coordination/coordination_study_spec.v0.1.yaml)) and pack presets ([policy/coordination/coordination_security_pack.v0.1.yaml](https://github.com/fraware/LabTrust-Gym/blob/main/policy/coordination/coordination_security_pack.v0.1.yaml)) define which scale IDs are run. Results are defined only for these scale configs and for cells (scale_id, method_id, injection_id) in the study or pack matrix.

| scale_id | num_agents_total | num_sites | horizon_steps |
|----------|------------------|-----------|---------------|
| corridor_heavy | 200 | 2 | 150 |
| small_smoke | 4 | 1 | 50 |
| small_8 | 8 | 1 | 60 |
| medium_stress_signed_bus | 75 | 2 | 300 |

### Injection list

The study spec's `injections` list and [policy/coordination/injections.v0.2.yaml](https://github.com/fraware/LabTrust-Gym/blob/main/policy/coordination/injections.v0.2.yaml) define which risk injections are applied. Only listed injection IDs with configured intensity and application_phase (when applicable) are used. Injection families include:

- **Identity:** INJ-ID-SPOOF-001
- **Replay:** INJ-REPLAY-001, INJ-COORD-PLAN-REPLAY-001, INJ-ID-REPLAY-COORD-001
- **Comms / poisoning:** INJ-COMMS-POISON-001, INJ-COMMS-FLOOD-LLM-001
- **Collusion / bid:** INJ-COLLUSION-001, INJ-BID-SPOOF-001, INJ-COLLUSION-MARKET-001, INJ-COORD-BID-SHILL-001
- **Prompt / LLM:** INJ-COORD-PROMPT-INJECT-001, INJ-LLM-PROMPT-INJECT-COORD-001
- **Tool:** INJ-TOOL-MISUSE-001, INJ-LLM-TOOL-ESCALATION-001
- **Memory:** INJ-MEMORY-POISON-001, INJ-MEMORY-POISON-COORD-001
- **Other:** INJ-SLOW-POISON-001, INJ-CONSENSUS-POISON-001, INJ-TIMING-QUEUE-001, INJ-PARTIAL-OBS-001, INJ-BLAME-SHIFT-001, inj_dos_flood, inj_memory_tamper, inj_tool_selection_noise

### Cells and metrics

Results (throughput, violations, resilience, sec.*) are defined only for cells (scale_id, method_id, injection_id) that appear in the study or pack matrix. No claim is made for cells outside that matrix.

## What was not tested / out of scope

- **Scales or topologies not in the grid:** e.g. 500+ agents, 5+ sites, or different role mixes and device counts than those in scale_configs.v0.1.yaml.
- **Injection types or parameters not in the injection list:** no claim for "all possible" or "similar" attacks; only the configured injection IDs and their parameters are exercised.
- **Extrapolation:** no claim that a method that wins on the tested grid is best at other scales or under other threat models.
- **Comparison with other benchmarks:** when comparing to other benchmarks, align scale and threat model (injection set) or state differences explicitly. This benchmark reports only for the specified scale grid and injection list.

## References

- [Coordination benchmark card](coordination_benchmark_card.md) – "What this benchmark is NOT measuring"
- [Coordination studies](coordination_studies.md) – study spec and matrix
- [Coordination scale](coordination_scale.md) and [Scale and operational limits](../benchmarks/scale_operational_limits.md)
- [State of the art and limits](../reference/state_of_the_art_and_limits.md)
