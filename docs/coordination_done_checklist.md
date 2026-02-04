# Coordination-at-scale done checklist

Acceptance gates for coordination work before UI/Lovable work starts. All items must pass.

## Policy validation

- [ ] **Policy validation passes**  
  Risk registry, method registry, method-risk matrix, and coordination study spec validate.

  ```bash
  labtrust validate-policy
  ```

  Ensures: `policy/risks/risk_registry.v0.1.yaml`, `policy/coordination/coordination_methods.v0.1.yaml`, `policy/coordination/method_risk_matrix.v0.1.yaml`, and `policy/coordination/coordination_study_spec.v0.1.yaml` (and their schemas under `policy/schemas/`) are valid.

## Tasks runnable

- [ ] **TaskG_COORD_SCALE runnable**  
  Coordination at scale under nominal conditions.

  ```bash
  labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 1 --seed 42 --coord-method centralized_planner --out /tmp/taskg.json
  ```

- [ ] **TaskH_COORD_RISK runnable**  
  Coordination under injected risks (at least one injection).

  ```bash
  labtrust run-benchmark --task TaskH_COORD_RISK --episodes 1 --seed 42 --coord-method market_auction --injection INJ-COLLUSION-001 --out /tmp/taskh.json
  ```

## Coordination methods

- [ ] **At least 5 coordination methods implemented**  
  Centralized, hierarchical, market, gossip, swarm; optional LLM.

  Required: `centralized_planner`, `hierarchical_hub_rr`, `market_auction`, `gossip_consensus`, `swarm_reactive`. Optional: `llm_constrained`, `marl_ppo` (stub ok if deps missing).

  Verify: `labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 1 --seed 42 --coord-method <method_id> --out /tmp/out.json` for each method.

## Risk injections

- [ ] **At least 5 injections implemented**  
  Including spoofing (must be blocked when strict signatures) and communication poisoning.

  Minimum: INJ-COMMS-POISON-001, INJ-ID-SPOOF-001 (blocked by signatures/RBAC), INJ-DOS-PLANNER-001, INJ-COLLUSION-001, INJ-TOOL-MISPARAM-001, INJ-MEMORY-POISON-001 (or equivalent set).

- [ ] **Spoofing blocked**  
  INJ-ID-SPOOF-001 must yield `attack_success_rate=0` when `strict_signatures=True`.

## Determinism

- [ ] **Scale generator determinism**  
  Same seed + same scale config produce identical agent IDs, device IDs, site IDs, initial specimen list, and placements.

  ```bash
  pytest -q tests/test_coordination_scale_determinism.py
  ```

- [ ] **Injections determinism**  
  Same seed produces same injection sequence.

  ```bash
  pytest -q tests/test_risk_injections_deterministic.py
  ```

## Study runner and Pareto

- [ ] **Study runner emits Pareto report**  
  Coordination study produces `summary/pareto.md` with per-scale Pareto front and robust winner.

  ```bash
  labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out /tmp/coord_out
  # Check: /tmp/coord_out/summary/pareto.md exists and contains "Pareto" and "Robust winner"
  ```

  For a fast smoke: set `LABTRUST_REPRO_SMOKE=1` or use a minimal spec (e.g. 1 scale, 1 method, 1 injection, 1 episode per cell).

## Benchmark card and docs

- [ ] **Benchmark card updated**  
  Mentions coordination suite (TaskG, TaskH), coordination methods, risk injections, and coordination metrics (e.g. sec.attack_success_rate, robustness.resilience_score). See [Benchmark card](benchmark_card.md).

## CI smoke (no secrets)

- [ ] **Coordination smoke job runnable**  
  CI gate runs without secrets: validate-policy, pytest coordination tests, TaskG and TaskH one-episode runs.

  ```bash
  labtrust validate-policy
  pytest -q tests/test_coordination_*
  labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 1 --seed 42 --coord-method centralized_planner --out /tmp/taskg.json
  labtrust run-benchmark --task TaskH_COORD_RISK --episodes 1 --seed 42 --coord-method market_auction --injection INJ-COLLUSION-001 --out /tmp/taskh.json
  ```

  The workflow job `coordination-smoke` is triggered on schedule (nightly) or via workflow_dispatch; it does not run on every push/PR to keep CI fast.
