"""Campaign generator for delayed evidence invalidation studies.

The generator separates the policy-visible trace from hidden adjudication state.
It implements the campaign physics and measurement-control boundary only; no
recovery method is implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from .control import CheckStandardResult, SuspectInterval, evaluate_check_standard, suspect_interval_from_history
from .failure import DriftKind, DriftSchedule
from .instrument import LadsAlignedPhMeter, PhMeasurement
from .surface import benchmark_ph_surface


@dataclass(frozen=True)
class PolicyObservation:
    """Information available to the adaptive scientific policy."""

    experiment_index: int
    x: float
    reported_ph: float


class ExperimentPolicy(Protocol):
    """Stateless-from-history policy interface used by the study harness."""

    def choose_x(
        self,
        observations: Sequence[PolicyObservation],
        *,
        experiment_index: int,
        rng: np.random.Generator,
    ) -> float:
        """Choose the next x in [0, 1] using policy-visible information only."""
        ...


@dataclass(frozen=True)
class SeedBundle:
    """Independent deterministic RNG streams."""

    measurement_seed: int
    check_seed: int
    failure_seed: int
    policy_seed: int


@dataclass(frozen=True)
class CampaignConfig:
    """Frozen primary campaign parameters from protocol v0.1.2."""

    total_experiments: int = 240
    initial_design_points: int = 16
    check_interval: int = 20
    check_replicates: int = 5
    check_reference_ph: float = 7.0
    temperature_c: float = 25.0
    drift_onset_min: int = 60
    drift_onset_max: int = 120
    drift_rate_sigma_per_experiment: float = 0.125
    drift_direction: int = 1
    application_validity_tolerance_sigma0: float = 1.0

    def __post_init__(self) -> None:
        if self.total_experiments <= 0:
            raise ValueError("total_experiments must be positive")
        if not 0 < self.initial_design_points < self.total_experiments:
            raise ValueError("initial_design_points must lie inside the campaign")
        if self.check_interval <= 0 or self.check_replicates <= 0:
            raise ValueError("check interval and replicates must be positive")
        if not 1 <= self.drift_onset_min <= self.drift_onset_max <= self.total_experiments:
            raise ValueError("drift onset range must lie inside the one-based campaign")
        if self.drift_rate_sigma_per_experiment < 0:
            raise ValueError("drift rate must be non-negative")
        if self.drift_direction not in (-1, 1):
            raise ValueError("drift_direction must be -1 or 1")
        if self.application_validity_tolerance_sigma0 <= 0:
            raise ValueError("application validity tolerance must be positive")


@dataclass(frozen=True)
class ExperimentRecord:
    """Full hidden adjudication record for one scientific experiment."""

    experiment_index: int
    sample_id: str
    x: float
    true_ph: float
    measurement: PhMeasurement
    systematic_bias_ph: float
    scientifically_valid: bool


@dataclass(frozen=True)
class CampaignRun:
    """One pre-recovery or full campaign realization."""

    master_seed: int
    seed_bundle: SeedBundle
    sigma0: float
    config: CampaignConfig
    drift_enabled: bool
    physical_drift_onset: int | None
    scientific_invalidity_onset: int | None
    first_alarm_index: int | None
    false_positive_alarm: bool
    eligible_for_primary_recovery_estimand: bool
    suspect_interval: SuspectInterval | None
    experiments: tuple[ExperimentRecord, ...]
    policy_observations: tuple[PolicyObservation, ...]
    checks: tuple[CheckStandardResult, ...]


def _derived_seed(master_seed: int, stream_id: int) -> int:
    """Derive a stable uint64 seed without shared mutable RNG state."""
    seq = np.random.SeedSequence([int(master_seed), int(stream_id)])
    return int(seq.generate_state(1, dtype=np.uint64)[0])


def derive_seed_bundle(master_seed: int) -> SeedBundle:
    """Create independent streams for measurement, QC, failure, and policy."""
    return SeedBundle(
        measurement_seed=_derived_seed(master_seed, 1),
        check_seed=_derived_seed(master_seed, 2),
        failure_seed=_derived_seed(master_seed, 3),
        policy_seed=_derived_seed(master_seed, 4),
    )


def initial_design_x(index_one_based: int, n_points: int) -> float:
    """Deterministic midpoint space-filling initial design on [0, 1]."""
    if not 1 <= index_one_based <= n_points:
        raise ValueError("initial-design index out of range")
    return (index_one_based - 0.5) / n_points


def _validate_policy_x(x: float) -> float:
    value = float(x)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"policy produced x outside [0, 1]: {value}")
    return value


def _sample_drift_onset(config: CampaignConfig, failure_rng: np.random.Generator) -> int:
    """Sample the registered inclusive one-based onset interval."""
    return int(failure_rng.integers(config.drift_onset_min, config.drift_onset_max + 1))


def _scientific_invalidity_onset(
    experiments: Sequence[ExperimentRecord],
) -> int | None:
    for record in experiments:
        if not record.scientifically_valid:
            return record.experiment_index
    return None


def run_campaign(
    policy: ExperimentPolicy,
    *,
    master_seed: int,
    sigma0: float,
    config: CampaignConfig | None = None,
    meter: LadsAlignedPhMeter | None = None,
    drift_enabled: bool = True,
    stop_at_first_alarm: bool = True,
) -> CampaignRun:
    """Run one registered campaign realization.

    Event ordering is scientific experiment, then any scheduled check under the
    same current metrological state, then optional stop after the first alarm.

    The adaptive policy sees only PolicyObservation objects. Hidden true pH,
    drift parameters, systematic bias, validity labels, and QC readings are
    never passed to choose_x.
    """
    if sigma0 <= 0:
        raise ValueError("sigma0 must be positive")
    cfg = config or CampaignConfig()
    ph_meter = meter or LadsAlignedPhMeter()
    seeds = derive_seed_bundle(master_seed)

    measurement_rng = np.random.default_rng(seeds.measurement_seed)
    check_rng = np.random.default_rng(seeds.check_seed)
    failure_rng = np.random.default_rng(seeds.failure_seed)
    policy_rng = np.random.default_rng(seeds.policy_seed)

    onset = _sample_drift_onset(cfg, failure_rng) if drift_enabled else None
    drift = (
        DriftSchedule(
            onset_index=onset,
            rate_sigma_per_experiment=cfg.drift_rate_sigma_per_experiment,
            sigma0=sigma0,
            kind=DriftKind.OFFSET,
            direction=cfg.drift_direction,
        )
        if onset is not None
        else None
    )

    experiments: list[ExperimentRecord] = []
    visible: list[PolicyObservation] = []
    checks: list[CheckStandardResult] = []
    first_alarm_index: int | None = None

    validity_tolerance = cfg.application_validity_tolerance_sigma0 * sigma0

    for t in range(1, cfg.total_experiments + 1):
        if t <= cfg.initial_design_points:
            x = initial_design_x(t, cfg.initial_design_points)
        else:
            x = _validate_policy_x(
                policy.choose_x(
                    tuple(visible),
                    experiment_index=t,
                    rng=policy_rng,
                )
            )

        true_ph = benchmark_ph_surface(x)
        if drift is None:
            physical_offset, physical_slope = 0.0, 100.0
        else:
            physical_offset, physical_slope = drift.instrument_parameters_at(t)

        systematic_bias = ph_meter.systematic_bias_ph(
            true_ph,
            temperature_c=cfg.temperature_c,
            physical_offset_ph=physical_offset,
            physical_slope_pct=physical_slope,
        )
        measurement = ph_meter.measure(
            true_ph,
            rng=measurement_rng,
            temperature_c=cfg.temperature_c,
            physical_offset_ph=physical_offset,
            physical_slope_pct=physical_slope,
        )
        record = ExperimentRecord(
            experiment_index=t,
            sample_id=f"SAMPLE_{master_seed}_{t:04d}",
            x=x,
            true_ph=true_ph,
            measurement=measurement,
            systematic_bias_ph=systematic_bias,
            scientifically_valid=abs(systematic_bias) <= validity_tolerance,
        )
        experiments.append(record)
        visible.append(
            PolicyObservation(
                experiment_index=t,
                x=x,
                reported_ph=measurement.reported_ph,
            )
        )

        if t % cfg.check_interval == 0:
            check_values = tuple(
                ph_meter.measure(
                    cfg.check_reference_ph,
                    rng=check_rng,
                    temperature_c=cfg.temperature_c,
                    physical_offset_ph=physical_offset,
                    physical_slope_pct=physical_slope,
                ).reported_ph
                for _ in range(cfg.check_replicates)
            )
            check = evaluate_check_standard(
                check_values,
                experiment_index=t,
                sigma0=sigma0,
                reference_ph=cfg.check_reference_ph,
            )
            checks.append(check)
            if not check.in_control and first_alarm_index is None:
                first_alarm_index = t
                if stop_at_first_alarm:
                    break

    invalidity_onset = _scientific_invalidity_onset(experiments)
    false_positive = (
        first_alarm_index is not None
        and (invalidity_onset is None or first_alarm_index < invalidity_onset)
    )
    eligible = (
        first_alarm_index is not None
        and invalidity_onset is not None
        and invalidity_onset <= first_alarm_index
    )

    return CampaignRun(
        master_seed=int(master_seed),
        seed_bundle=seeds,
        sigma0=float(sigma0),
        config=cfg,
        drift_enabled=bool(drift_enabled),
        physical_drift_onset=onset,
        scientific_invalidity_onset=invalidity_onset,
        first_alarm_index=first_alarm_index,
        false_positive_alarm=false_positive,
        eligible_for_primary_recovery_estimand=eligible,
        suspect_interval=suspect_interval_from_history(checks),
        experiments=tuple(experiments),
        policy_observations=tuple(visible),
        checks=tuple(checks),
    )


def run_clean_counterfactual(
    policy: ExperimentPolicy,
    *,
    master_seed: int,
    sigma0: float,
    config: CampaignConfig | None = None,
    meter: LadsAlignedPhMeter | None = None,
) -> CampaignRun:
    """Run the no-drift hidden clean reference for the full registered horizon."""
    return run_campaign(
        policy,
        master_seed=master_seed,
        sigma0=sigma0,
        config=config,
        meter=meter,
        drift_enabled=False,
        stop_at_first_alarm=False,
    )
