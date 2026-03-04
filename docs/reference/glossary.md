# Glossary

Definitions of terms used across the documentation to avoid ambiguity.

## Lab terminology (hospital lab, pathology lab, blood sciences lab)

Documentation uses a three-level hierarchy for lab scope:

- **Hospital lab** (broad): Any lab operated within or for a hospital—specimen handling, diagnostics, point-of-care, etc. LabTrust-Gym is framed as an environment for hospital lab automation in this broad sense.

- **Pathology lab** (more precise): A lab that performs diagnostic pathology (histopathology, clinical chemistry, haematology, immunology, microbiology, etc.). Blood sciences is one branch of pathology.

- **Blood sciences lab** / **blood sciences lane** (most precise): The specific workflow modeled in LabTrust-Gym: specimen reception, accessioning, pre-analytics, routine and STAT analytics, QC, critical result notification, release, and multi-site transport with chain-of-custody. The domain adapter is registered as `hospital_lab`; the simulated workflow is a blood sciences lane (a type of pathology lab within the broader hospital lab category).

When describing **what is implemented**, use "blood sciences lane" or "blood sciences lab." When describing **applicability or motivation**, use "hospital labs" or "pathology labs" as appropriate.

## Baseline

The word "baseline" is used in two distinct ways in this repo:

- **Official baselines (v0.2):** The frozen result set produced by `labtrust generate-official-baselines`. Used for regression: the baseline regression guard compares exact metrics against these results. Stored under `benchmarks/baselines_official/v0.2/`. Tasks are defined in `benchmarks/baseline_registry.v0.1.yaml` (core tasks and optionally coord_scale/coord_risk). Regenerate with `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes N --seed N --force`.

- **Baseline ID / coordination method (for coord tasks):** For coord_scale and coord_risk, the pack YAML key `baselines` maps each task to a **coordination method ID** (e.g. `kernel_scheduler_or`). The pack often uses a versioned name (e.g. `kernel_scheduler_or_v0`); the runner strips the `_v0` suffix to obtain the method_id. In prose, prefer **"coordination method"** or **"coord method"** when referring to this, to avoid confusion with the official baselines (v0.2) result set.

See [Official benchmark pack](../benchmarks/official_benchmark_pack.md) and [Benchmark card](../benchmarks/benchmark_card.md) for how these are used in practice.

## Simulation

The LabTrust-Gym benchmark and env runs: deterministic or stochastic runs under policy. Used for development, regression, and security/safety evaluation.

## Production

Live deployment with real users, keys, and adversaries. Transfer of results from simulation to production is not claimed; production assurance is the integrator's responsibility. See [Threat model](../architecture/threat_model.md) and [State of the art and limits](state_of_the_art_and_limits.md).
