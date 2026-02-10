# Implementation strategy: learning-style coordination methods

"Group-Evolving Agents" implies open-ended improvement across episodes. That conflicts with CI determinism unless behaviour is split into a **deterministic track** (CI-safe, frozen) and a **study track** (research mode, reproducible via seed-base and artifact logs). This document records the design decision and the concrete metadata convention.

---

## Two-track coordination method mode

### Deterministic track (CI-safe)

- Uses **fixed heuristics** or **fixed update rules** (e.g. loaded policy, no training step).
- **No cross-run learning persistence** unless it is fully seeded and controlled (e.g. same checkpoint path + seed yields identical behaviour).
- Runs in **`pipeline_mode=deterministic`**.
- Suitable for: CI, regression tests, contract tests, and any run that must be bit-reproducible from seed alone.
- Learning-style methods (e.g. MARL PPO) in this track: **inference-only** from a fixed checkpoint; no `train()` or buffer updates during the run.

### Study track (research mode)

- **Can evolve across episodes** (e.g. policy updates, experience replay, evolution).
- Must save and reference:
  - **Experience buffer snapshots** (or equivalent) when applicable.
  - **Policy / genome checkpoints** (e.g. per N episodes or at end of run).
  - **Mutation / update logs** (what changed, when).
- **Reproducibility** is achieved via:
  - **seed_base** (and episode seeds derived from it).
  - **Explicit algorithm version hash** (e.g. code or config fingerprint).
  - **Checkpoint hashing** in MANIFEST or run manifests (so a run can be reproduced from seed + checkpoint hash + algorithm version).
- Not required to be bit-identical across runs; same seed_base + same checkpoint + same algorithm version must yield **reproducible behaviour** (same metrics within expected variance when the method is stochastic).
- Study-track runs should **not** be used as the sole basis for CI gates; use deterministic-track or inference-only baselines for that.

---

## Optional learning metadata in results (v0.2 compatible)

Results schema v0.2 allows optional top-level **metadata** with `additionalProperties: true`. To support learning-style methods without breaking compatibility, the following **optional** nested structure is defined. When a coordination method uses learning (study track), the runner can populate:

**Location:** `results.metadata.coordination.learning`

| Field | Type | Description |
|-------|------|-------------|
| **enabled** | boolean | True when this run used a learning/evolving coordination method (study track). |
| **checkpoint_sha** | string (optional) | Hash (e.g. SHA-256) of the policy or genome checkpoint used at **start** of the run, or at end if reporting final checkpoint. Enables reproducibility (re-run with same checkpoint + seed_base). |
| **update_count** | integer (optional) | Number of policy/parameter updates (e.g. gradient steps, mutations) performed during this run. Zero for inference-only. |
| **buffer_size** | integer (optional) | Size of the experience buffer (or equivalent) at end of run, when applicable. |

- If **enabled** is false or absent, the run is treated as deterministic-track (no learning during the run).
- **checkpoint_sha** and **buffer_size** can be included in MANIFEST or run manifests for study-track reproducibility.
- Consumers (summarize-results, risk register, CI) should treat presence of `coordination.learning.enabled === true` as an indication that the run is study-track and may not be bit-reproducible from seed alone; reproducibility is then via seed_base + algorithm version + checkpoint_sha (and optionally buffer snapshot).

---

## How methods expose learning metadata

- Coordination methods that support the **study track** may implement an optional **`get_learning_metadata() -> dict[str, Any] | None`**. When non-None, the runner merges it into `results.metadata.coordination.learning` after the run.
- Deterministic and inference-only methods do not implement it (or return None); the runner does not add `coordination.learning` in that case.
- The dict returned by `get_learning_metadata()` should contain at most the keys above (`enabled`, `checkpoint_sha`, `update_count`, `buffer_size`); additional keys are allowed for forward compatibility but may be ignored by downstream tools.

---

## Reproducibility checklist (study track)

When running or publishing a study-track coordination run:

1. Record **seed_base** (and episode seeds if different).
2. Record **algorithm version** (e.g. git SHA, or a hash of code/config).
3. Save **checkpoint(s)** and record **checkpoint_sha** in metadata and/or MANIFEST.
4. If experience buffers are part of the method, save **buffer snapshots** or document that reproducibility is conditional on same buffer state (e.g. same prior run).
5. Optionally save **mutation/update logs** (e.g. which updates were applied, in what order).

CI and regression gates should use only **deterministic-track** runs (or inference-only learning methods with a fixed checkpoint and no updates during the run).
