"""
Study runners: run benchmark tasks with controlled ablations and outputs.

Exposes run_study for research-grade studies: Cartesian product of conditions,
deterministic seeds, and reproducible artifact directories (manifest,
conditions, results, logs). Coordination studies (scale x method x injection)
and package-release use the same patterns.
"""

from labtrust_gym.studies.study_runner import run_study

__all__ = ["run_study"]
