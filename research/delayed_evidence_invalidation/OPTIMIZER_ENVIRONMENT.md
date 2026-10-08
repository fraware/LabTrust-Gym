# Optimizer environment — protocol v0.1.3

The Bayesian-optimization study environment is intentionally separate from the
LabTrust-Gym base dependency graph.

## Standard and sliding-window GP-UCB

Create a Python 3.12 environment and install:

```bash
python -m pip install -r research/delayed_evidence_invalidation/optimizer_requirements.txt
```

The pinned versions mirror the official RCGP release environment for the common
scientific stack:

- torch 2.8.0
- BoTorch 0.15.1
- GPyTorch 1.14
- NumPy 1.26.4
- SciPy 1.12.0

The study-local policy code uses BoTorch directly. No Torch dependency is added
to the base LabTrust installation.

## RCGP comparator

Reference:

- repository: `EZZERG/RCGP`
- commit: `68bd978dfe4de28aed02184efc64ea343cfa9afc`
- upstream package metadata: `rcgp-ucb==0.1.0`
- upstream Python requirement: `>=3.12,<3.13`

The pinned public repository does not contain a root LICENSE file. Do **not**
vendor or redistribute upstream source into LabTrust-Gym. For the preregistered
external comparator, use a separately obtained checkout pinned to the commit
above and record its tree/commit identity in run artifacts.

The LabTrust adapter should consume only posterior mean/variance or action
outputs from that separately installed environment. If redistribution becomes
desirable, obtain explicit licensing clarification or implement the published
mathematics independently after legal/licensing review.

## Reproducibility

Primary runs must record:

- Python/platform;
- package versions;
- Torch device and dtype;
- optimizer/model fitting seed;
- model-fit warnings/failures;
- exact RCGP commit where used;
- study-contract digest.

No failed fit is silently rerun with a new seed.
