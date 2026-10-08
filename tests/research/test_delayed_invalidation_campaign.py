from __future__ import annotations

from dataclasses import fields
from typing import Sequence

import numpy as np

from labtrust_gym.research.delayed_invalidation.campaign import (
    CampaignConfig,
    PolicyObservation,
    derive_seed_bundle,
    run_campaign,
    run_clean_counterfactual,
)
from labtrust_gym.research.delayed_invalidation.instrument import LadsAlignedPhMeter


class FixedPolicy:
    def choose_x(
        self,
        observations: Sequence[PolicyObservation],
        *,
        experiment_index: int,
        rng: np.random.Generator,
    ) -> float:
        del observations, experiment_index, rng
        return 0.5


def test_policy_observation_excludes_hidden_oracle_fields() -> None:
    assert {field.name for field in fields(PolicyObservation)} == {
        "experiment_index",
        "x",
        "reported_ph",
    }


def test_rng_streams_are_deterministic_and_separate() -> None:
    a = derive_seed_bundle(123)
    b = derive_seed_bundle(123)
    assert a == b
    assert len({a.measurement_seed, a.check_seed, a.failure_seed, a.policy_seed}) == 4


def test_clean_counterfactual_stays_valid_without_measurement_noise() -> None:
    meter = LadsAlignedPhMeter(raw_noise_half_width_mv=0.0)
    run = run_clean_counterfactual(
        FixedPolicy(),
        master_seed=1,
        sigma0=0.01,
        meter=meter,
    )
    assert len(run.experiments) == 240
    assert run.physical_drift_onset is None
    assert run.scientific_invalidity_onset is None
    assert run.first_alarm_index is None
    assert run.suspect_interval is None
    assert not run.false_positive_alarm
    assert not run.eligible_for_primary_recovery_estimand
    assert all(record.scientifically_valid for record in run.experiments)
    assert all(check.in_control for check in run.checks)


def test_registered_fixture_orders_drift_invalidity_and_detection() -> None:
    meter = LadsAlignedPhMeter(raw_noise_half_width_mv=0.0)
    config = CampaignConfig(
        drift_rate_sigma_per_experiment=0.125,
        application_validity_tolerance_sigma0=1.0,
    )
    run = run_campaign(
        FixedPolicy(),
        master_seed=1,
        sigma0=0.01,
        config=config,
        meter=meter,
        drift_enabled=True,
        stop_at_first_alarm=True,
    )

    assert run.physical_drift_onset == 98
    assert run.scientific_invalidity_onset == 106
    assert run.first_alarm_index == 120
    assert len(run.experiments) == 120
    assert run.eligible_for_primary_recovery_estimand
    assert not run.false_positive_alarm

    assert run.suspect_interval is not None
    assert run.suspect_interval.last_in_control_index == 100
    assert run.suspect_interval.detection_index == 120
    assert run.suspect_interval.contains(run.scientific_invalidity_onset)


def test_policy_trace_never_contains_hidden_true_ph_or_validity() -> None:
    meter = LadsAlignedPhMeter(raw_noise_half_width_mv=0.0)
    run = run_campaign(
        FixedPolicy(),
        master_seed=1,
        sigma0=0.01,
        meter=meter,
    )
    for observation in run.policy_observations:
        assert not hasattr(observation, "true_ph")
        assert not hasattr(observation, "systematic_bias_ph")
        assert not hasattr(observation, "scientifically_valid")


def test_same_seed_replays_same_hidden_failure_and_measurements() -> None:
    policy = FixedPolicy()
    meter = LadsAlignedPhMeter()
    sigma0 = meter.estimate_sigma0(seed=20261008, readings=1000)
    a = run_campaign(policy, master_seed=42, sigma0=sigma0, meter=meter)
    b = run_campaign(policy, master_seed=42, sigma0=sigma0, meter=meter)

    assert a.physical_drift_onset == b.physical_drift_onset
    assert a.scientific_invalidity_onset == b.scientific_invalidity_onset
    assert a.first_alarm_index == b.first_alarm_index
    assert [x.measurement.reported_ph for x in a.experiments] == [
        x.measurement.reported_ph for x in b.experiments
    ]
    assert [x.mean_reported_ph for x in a.checks] == [
        x.mean_reported_ph for x in b.checks
    ]
