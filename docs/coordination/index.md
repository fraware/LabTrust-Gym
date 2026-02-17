# Coordination

Coordination at scale: methods, scale configs, matrix, studies, and benchmark cards. Coordination methods used for comparison in this repo are **LLM-based** (see `policy/coordination/coordination_methods.v0.1.yaml`: `llm_based: true`); the goal of multiple methods is to compare LLM coordination strategies on the same baseline. Kernel and deterministic baselines are components or building blocks, not coordination methods for comparison.

## Methods and scale

| Document | Description |
|----------|-------------|
| [Coordination methods](coordination_methods.md) | Baselines and methods at scale. |
| [How coordination methods work (detailed)](coordination_methods_how_they_work.md) | Algorithms, data flow, invariants, and design choices for every method. |
| [Coordination method contract (v0.1)](coordination_method_contract.md) | Method contract and schema. |
| [Coordination scale](coordination_scale.md) | Scale generator and configs. |
| [Coordination matrix](coordination_matrix.md) | Matrix build and usage. |
| [Coordination matrix contract (v0.1)](coordination_matrix_contract.md) | Matrix contract. |
| [Fidelity notes](fidelity_notes.md) | Algorithm and invariant fidelity per method. |
| [SOTA methods at scale](sota_methods_at_scale.md) | SOTA coordination methods roadmap. |
| [Learning methods implementation strategy](learning_methods_implementation_strategy.md) | Implementation strategy for learning-based methods. |

## Studies and reports

| Document | Description |
|----------|-------------|
| [Coordination studies](coordination_studies.md) | Run studies, Pareto, summarization. |
| [Coordination benchmark card](coordination_benchmark_card.md) | Task G/H and metrics. |
| [Coordination methods audit](coordination_methods_audit.md) | Method audit. |
| [Lab coordination report](lab_coordination_report.md) | Canonical hospital lab flow. |

## How-to

| Document | Description |
|----------|-------------|
| [Add a coordination method](../operations/howto_add_coordination_method.md) | Register and implement a new method. |
