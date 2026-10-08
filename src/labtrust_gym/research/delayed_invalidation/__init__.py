"""Delayed evidence invalidation study primitives.

The effective study protocol is frozen under:
research/delayed_evidence_invalidation/study_contract.v0.1.2.yaml
"""

from .campaign import (
    CampaignConfig,
    CampaignRun,
    ExperimentPolicy,
    ExperimentRecord,
    PolicyObservation,
    SeedBundle,
    derive_seed_bundle,
    run_campaign,
    run_clean_counterfactual,
)
from .control import CheckStandardResult, SuspectInterval
from .failure import DriftKind, DriftSchedule
from .instrument import LadsAlignedPhMeter, PhMeasurement
from .surface import benchmark_ph_surface, benchmark_utility

__all__ = [
    "CampaignConfig",
    "CampaignRun",
    "CheckStandardResult",
    "DriftKind",
    "DriftSchedule",
    "ExperimentPolicy",
    "ExperimentRecord",
    "LadsAlignedPhMeter",
    "PhMeasurement",
    "PolicyObservation",
    "SeedBundle",
    "SuspectInterval",
    "benchmark_ph_surface",
    "benchmark_utility",
    "derive_seed_bundle",
    "run_campaign",
    "run_clean_counterfactual",
]
