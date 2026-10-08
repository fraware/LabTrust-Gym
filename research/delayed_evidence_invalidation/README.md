# Delayed Evidence Invalidation Study

**Status:** preregistration v0.1.1 effective / no primary results inspected  
**Branch:** `research/delayed-evidence-invalidation-v0`  
**Base commit:** `7e361583fb3e8ca4f482b072f4ac190e30cc69a5`

This directory freezes the first study in the long-horizon scientific-state assurance programme.

## Research object

The study asks what a continuously adaptive laboratory should do when evidence previously admitted into its scientific state is later found invalid.

The central distinction is between:

- **validity dependence**: an artifact, model, or claim depends on evidence whose own validity has failed; and
- **selection dependence**: an experiment was selected by a scientific state influenced by invalid evidence, although the experiment or later measurement may remain scientifically usable.

The first benchmark uses delayed calibration-drift discovery in an OPC UA LADS-aligned pH-measurement loop. Metrology owns detection that the measurement process has left control. The study begins at that detection event and evaluates propagation and recovery.

## Frozen artifacts

- `PREREGISTRATION.md` — original v0.1 hypotheses, prior-art boundary, design, baselines, outcomes, analysis, ablations, and kill criteria.
- `AMENDMENT_0.1.1.md` — pre-outcome amendment separating physical drift onset from scientific invalidity onset.
- `study_contract.v0.1.yaml` — historical machine-readable v0.1 contract.
- `study_contract.v0.1.1.yaml` — **effective** machine-readable contract for implementation and analysis.
- `REFERENCES.md` — literature and standards that define the prior-art boundary.

## Claim discipline

This study is a simulation / reference-integration study. It does not establish production laboratory safety, clinical validity, general real-world failure rates, or a universal theory of scientific recovery. Those claims require external laboratory data and independent replication.

No implementation decision may silently weaken a frozen baseline, outcome definition, or kill criterion. Any protocol change after primary outcomes are inspected must be versioned and reported as post-registration.

## Effective protocol

Implementation and primary analysis must follow `study_contract.v0.1.1.yaml` together with `AMENDMENT_0.1.1.md`. The v0.1 files remain immutable historical records of the original preregistration.
