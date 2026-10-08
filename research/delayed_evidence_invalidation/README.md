# Delayed Evidence Invalidation Study

**Status:** preregistration / no primary results inspected  
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

- `PREREGISTRATION.md` — hypotheses, prior-art boundary, design, baselines, outcomes, analysis, ablations, and kill criteria.
- `study_contract.v0.1.yaml` — machine-readable design contract.
- `REFERENCES.md` — literature and standards that define the prior-art boundary.

## Claim discipline

This study is a simulation / reference-integration study. It does not establish production laboratory safety, clinical validity, general real-world failure rates, or a universal theory of scientific recovery. Those claims require external laboratory data and independent replication.

No implementation decision may silently weaken a frozen baseline, outcome definition, or kill criterion. Any protocol change after primary outcomes are inspected must be versioned and reported as post-registration.
