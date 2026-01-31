"""
Study runner: executes benchmark tasks with controlled ablations and outputs
a reproducible artifact directory (manifest, conditions, results, logs).
"""

from labtrust_gym.studies.study_runner import run_study

__all__ = ["run_study"]
