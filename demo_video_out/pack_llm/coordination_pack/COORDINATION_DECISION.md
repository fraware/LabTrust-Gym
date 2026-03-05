# Coordination Decision (artifact)

**Verdict:** admissible
**Generated:** 2026-03-05T16:07:56.765403+00:00
**Run dir:** C:\Users\mateo\LabTrust-Gym\demo_video_out\pack_llm\coordination_pack
**Policy:** coordination_selection_v0.1

## Scale decisions

### medium_stress_signed_bus

- **Chosen:** kernel_auction_whca_shielded
- **Overall score:** 1.0
- **Top candidates:** kernel_auction_whca_shielded (score=1.0, rank=1)

**Disqualified:**
- llm_detector_throttle_advisor: violation_rate_gate=32400
- llm_local_decider_signed_bus: violation_rate_gate=32400
- llm_repair_over_kernel_whca: violation_rate_gate=32400

### small_smoke

- **Chosen:** llm_local_decider_signed_bus
- **Overall score:** 1.0
- **Top candidates:** llm_local_decider_signed_bus (score=1.0, rank=1), llm_repair_over_kernel_whca (score=1.0, rank=2)

**Disqualified:**
- kernel_auction_whca_shielded: violation_rate_gate=257
- llm_detector_throttle_advisor: violation_rate_gate=283

## Risk register linkage

- **Chosen method evidence:** Chosen method(s) for deployment: kernel_auction_whca_shielded, llm_local_decider_signed_bus.
- **Rejected others rationale:** Rejected others: llm_detector_throttle_advisor: violation_rate_gate=32400; llm_local_decider_signed_bus: violation_rate_gate=32400; llm_repair_over_kernel_whca: violation_rate_gate=32400; kernel_auction_whca_shielded: violation_rate_gate=257; llm_detector_throttle_advisor: violation_rate_gate=283
- **Residual risk statement:** Residual risk: see per-scale disqualified methods and policy constraints.
