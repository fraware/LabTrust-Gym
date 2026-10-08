"""Deterministic, benchmark-local pH measurement semantics aligned to OPC UA LADS.

Source model:
  opcua-lads/lads-server-collection
  servers/lads-ph-meter/src/ph-meter-unit-simulator.ts

The upstream simulator computes a Nernst-based raw millivolt signal from a
simulated physical pH, temperature, slope and offset, adds small raw-signal
noise, and reconstructs reported pH using the sensor calibration values.

This module ports that algebraic measurement boundary for reproducible research
runs. It is not a production OPC UA device implementation and it does not claim
bit-for-bit equivalence to the upstream server state machine, timers,
historization, or random-number source.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

R_GAS = 8.314
FARADAY = 96485.0
CELSIUS_TO_KELVIN = 273.15


@dataclass(frozen=True)
class PhMeasurement:
    """One benchmark pH observation with state required for adjudication."""

    true_ph: float
    temperature_c: float
    raw_mv: float
    reported_ph: float
    physical_offset_ph: float
    physical_slope_pct: float
    calibration_offset_ph: float
    calibration_slope_pct: float
    raw_noise_mv: float


@dataclass(frozen=True)
class LadsAlignedPhMeter:
    """Steady-state pH signal model derived from the LADS reference simulator."""

    raw_noise_half_width_mv: float = 0.25

    @staticmethod
    def _thermal_factor(temperature_c: float) -> float:
        if temperature_c <= -CELSIUS_TO_KELVIN:
            raise ValueError("temperature_c must exceed absolute zero")
        return np.log(10.0) * R_GAS * (temperature_c + CELSIUS_TO_KELVIN) / FARADAY

    def raw_signal_mv(
        self,
        true_ph: float,
        *,
        temperature_c: float = 25.0,
        physical_offset_ph: float = 0.0,
        physical_slope_pct: float = 100.0,
    ) -> float:
        """Return the noiseless simulated electrode signal in millivolts."""
        if physical_slope_pct <= 0:
            raise ValueError("physical_slope_pct must be positive")
        thermal = self._thermal_factor(temperature_c)
        return (
            1000.0
            * thermal
            * (7.0 + physical_offset_ph - true_ph)
            * 0.01
            * physical_slope_pct
        )

    def reconstruct_ph(
        self,
        raw_mv: float,
        *,
        temperature_c: float = 25.0,
        calibration_offset_ph: float = 0.0,
        calibration_slope_pct: float = 100.0,
    ) -> float:
        """Reconstruct pH from raw signal and calibration state."""
        if calibration_slope_pct <= 0:
            raise ValueError("calibration_slope_pct must be positive")
        thermal = self._thermal_factor(temperature_c)
        return (
            7.0
            + calibration_offset_ph
            - 0.001 * raw_mv / (0.01 * calibration_slope_pct) / thermal
        )

    def systematic_bias_ph(
        self,
        true_ph: float,
        *,
        temperature_c: float = 25.0,
        physical_offset_ph: float = 0.0,
        physical_slope_pct: float = 100.0,
        calibration_offset_ph: float = 0.0,
        calibration_slope_pct: float = 100.0,
    ) -> float:
        """Expected reporting bias with raw measurement noise removed."""
        noiseless_raw = self.raw_signal_mv(
            true_ph,
            temperature_c=temperature_c,
            physical_offset_ph=physical_offset_ph,
            physical_slope_pct=physical_slope_pct,
        )
        reported = self.reconstruct_ph(
            noiseless_raw,
            temperature_c=temperature_c,
            calibration_offset_ph=calibration_offset_ph,
            calibration_slope_pct=calibration_slope_pct,
        )
        return float(reported - true_ph)

    def measure(
        self,
        true_ph: float,
        *,
        rng: np.random.Generator | None = None,
        temperature_c: float = 25.0,
        physical_offset_ph: float = 0.0,
        physical_slope_pct: float = 100.0,
        calibration_offset_ph: float = 0.0,
        calibration_slope_pct: float = 100.0,
        raw_noise_mv: float | None = None,
    ) -> PhMeasurement:
        """Measure one value with explicit or seeded raw-signal perturbation."""
        noiseless = self.raw_signal_mv(
            true_ph,
            temperature_c=temperature_c,
            physical_offset_ph=physical_offset_ph,
            physical_slope_pct=physical_slope_pct,
        )
        if raw_noise_mv is None:
            if rng is None or self.raw_noise_half_width_mv == 0:
                noise = 0.0
            else:
                noise = float(
                    rng.uniform(
                        -self.raw_noise_half_width_mv,
                        self.raw_noise_half_width_mv,
                    )
                )
        else:
            noise = float(raw_noise_mv)

        raw_mv = noiseless + noise
        reported = self.reconstruct_ph(
            raw_mv,
            temperature_c=temperature_c,
            calibration_offset_ph=calibration_offset_ph,
            calibration_slope_pct=calibration_slope_pct,
        )
        return PhMeasurement(
            true_ph=float(true_ph),
            temperature_c=float(temperature_c),
            raw_mv=float(raw_mv),
            reported_ph=float(reported),
            physical_offset_ph=float(physical_offset_ph),
            physical_slope_pct=float(physical_slope_pct),
            calibration_offset_ph=float(calibration_offset_ph),
            calibration_slope_pct=float(calibration_slope_pct),
            raw_noise_mv=float(noise),
        )

    def estimate_sigma0(
        self,
        *,
        seed: int,
        readings: int = 1000,
        reference_ph: float = 7.0,
        temperature_c: float = 25.0,
    ) -> float:
        """Estimate baseline reported-pH standard deviation for registered scaling."""
        if readings < 2:
            raise ValueError("readings must be >= 2")
        rng = np.random.default_rng(seed)
        values: NDArray[np.float64] = np.asarray(
            [
                self.measure(
                    reference_ph,
                    rng=rng,
                    temperature_c=temperature_c,
                ).reported_ph
                for _ in range(readings)
            ],
            dtype=float,
        )
        return float(np.std(values, ddof=1))
