# Coordination

Coordination at scale: methods, scale configs, matrix, studies, and benchmark cards. Coordination methods used for comparison in this repo are **LLM-based** (see `policy/coordination/coordination_methods.v0.1.yaml`: `llm_based: true`); the goal of multiple methods is to compare LLM coordination strategies on the same baseline. Kernel and deterministic baselines are components or building blocks, not coordination methods for comparison.

## Methods and scale

| Document | Description |
|----------|-------------|
| [Coordination methods](coordination_methods.md) | Baselines and methods at scale. |
| [How coordination methods work (detailed)](coordination_methods_how_they_work.md) | Algorithms, data flow, invariants, and design choices for every method. |
| [Coordination method contract (v0.1)](coordination_method_contract.md) | Method contract and schema. |
| [Coordination and environment](coordination_and_env.md) | Data flow: runner owns env; coord methods never call env. |
| [Coordination scale](coordination_scale.md) | Scale generator and configs. |
| [Coordination matrix](coordination_matrix.md) | Matrix build and usage. |
| [Coordination matrix contract (v0.1)](coordination_matrix_contract.md) | Matrix contract. |
| [Fidelity notes](fidelity_notes.md) | Algorithm and invariant fidelity per method. |
| [Learning methods implementation strategy](learning_methods_implementation_strategy.md) | Implementation strategy for learning-based methods. |
| [Handoff protocol](handoff_protocol.md) | Hub-to-region handoff and ACK protocol. |
| [Multi-LLM protocols](multi_llm_protocols.md) | Multi-LLM coordination protocols. |
| [Phase 5 LLM upgrades](phase5_llm_upgrades.md) | Phase 5 LLM coordination upgrades. |

## Studies and reports

| Document | Description |
|----------|-------------|
| [Coordination studies](coordination_studies.md) | Run studies, Pareto, summarization; SOTA leaderboard (main + full), method-class comparison; output layout and summarize-coordination. |
| [Coordination benchmark card](coordination_benchmark_card.md) | Task G/H and metrics; SOTA and method-class report artifacts. |
| [Coordination methods audit](coordination_methods_audit.md) | Method audit. |
| [Generalization and limits](generalization_and_limits.md) | What was tested, what was not; comparison with other benchmarks. |

## Risk and coverage

| Document | Description |
|----------|-------------|
| [Method and pack matrix](../risk-and-security/method_and_pack_matrix.md) | Method x risk coverage and pack (method x scale x injection) views; scale taxonomy (number of agents); CLI and CSV export. |

## How-to

| Document | Description |
|----------|-------------|
| [Add a coordination method](../operations/howto_add_coordination_method.md) | Register and implement a new method. |
