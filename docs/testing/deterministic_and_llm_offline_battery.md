# Deterministic and llm_offline test battery

This document lists the exact commands and pytest invocations that together verify deterministic and llm_offline pipelines. Running them in order constitutes the "deterministic and llm_offline battery."

## Battery sequence

Run from the repository root. Any step that fails should be fixed before considering the battery passed.

1. **Determinism report (throughput_sla, deterministic)**  
   ```bash
   labtrust determinism-report --task throughput_sla --episodes 2 --seed 42 --out ./det_report
   ```  
   Check: `det_report/determinism_report.json` exists and `passed` is true.

2. **Determinism report (coord_risk, deterministic)**  
   ```bash
   labtrust determinism-report --task coord_risk --coord-method kernel_centralized_edf --episodes 2 --seed 42 --out ./det_report_coord
   ```  
   Check: `det_report_coord/determinism_report.json` exists and `passed` is true.

3. **Determinism report (throughput_sla, llm_offline)** (optional)  
   ```bash
   labtrust determinism-report --task throughput_sla --episodes 2 --seed 42 --out ./det_llm_offline --pipeline-mode llm_offline --llm-backend deterministic_constrained
   ```  
   Check: `det_llm_offline/determinism_report.json` exists and `passed` is true. Proves bit-level determinism of llm_offline with deterministic_constrained.

4. **Golden suite**  
   ```bash
   LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q
   ```

5. **LLM fault model tests**  
   ```bash
   pytest tests/test_llm_fault_model.py -q
   ```

6. **Pipeline mode tests**  
   ```bash
   pytest tests/test_pipeline_mode.py -q
   ```

## CI

CI runs steps 1, 2, and 4 in the golden and determinism-golden jobs. Step 3 may be added optionally. Steps 5 and 6 are part of the default pytest collection when running the full test suite (e.g. `pytest -q` or `pytest -m "not slow"`); the battery checklist above makes the full sequence explicit for local verification or release checks.
