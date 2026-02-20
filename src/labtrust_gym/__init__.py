"""
LabTrust-Gym: multi-agent simulation for a self-driving hospital lab.

This package provides a Gym/PettingZoo-style environment where multiple agents
(coordination, operations, runners) act in a simulated lab. Behavior is driven by
versioned policy under policy/: invariants, tokens, reason codes, zones, and
golden scenarios. Correctness is defined by the golden test suite and related
contracts; see docs/ and policy/golden/.
"""

from labtrust_gym.version import __version__

__all__ = ["__version__"]
