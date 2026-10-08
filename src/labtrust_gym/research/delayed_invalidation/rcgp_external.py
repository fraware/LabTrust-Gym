"""External RCGP comparator adapter for protocol v0.1.3.

This module contains no upstream RCGP source. It imports the separately installed
authors' package at runtime and applies the preregistered model settings and the
same deterministic UCB grid used by the standard GP policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .bo_policy import observed_utility, theory_guided_ucb_multiplier
from .campaign import PolicyObservation

EXPECTED_RCGP_COMMIT = "68bd978dfe4de28aed02184efc64ea343cfa9afc"


class MissingExternalRcgp(RuntimeError):
    """Raised when the separately obtained RCGP package is unavailable."""


def _load_external_rcgp() -> tuple[Any, Any]:
    try:
        import torch
        from bo_framework.models.factory import create_rcgp_model
    except ImportError as exc:
        raise MissingExternalRcgp(
            "RCGP comparator requires a separate checkout/environment for "
            "EZZERG/RCGP at the preregistered commit"
        ) from exc
    return torch, create_rcgp_model


@dataclass
class ExternalRcgpUcbPolicy:
    """Pinned empirical RCGP surrogate with matched UCB acquisition."""

    target_ph: float = 7.40
    grid_points: int = 1001
    initial_design_points: int = 16
    plateau_width: float = 1.96
    plateau_c: float = 1.0

    def __post_init__(self) -> None:
        if self.grid_points < 2:
            raise ValueError("grid_points must be >= 2")
        if self.plateau_width <= 0 or self.plateau_c <= 0:
            raise ValueError("RCGP plateau parameters must be positive")

    def choose_x(
        self,
        observations: Sequence[PolicyObservation],
        *,
        experiment_index: int,
        rng: np.random.Generator,
    ) -> float:
        """Choose the next point without access to hidden campaign state."""
        if experiment_index <= self.initial_design_points:
            raise ValueError("RCGP policy should only be called after initial design")
        if not observations:
            raise ValueError("observations must be non-empty")

        torch, create_rcgp_model = _load_external_rcgp()

        x_values = np.asarray([obs.x for obs in observations], dtype=float)
        y_values = np.asarray(
            [
                observed_utility(obs.reported_ph, target_ph=self.target_ph)
                for obs in observations
            ],
            dtype=float,
        )
        train_x = torch.tensor(x_values, dtype=torch.double).unsqueeze(-1)
        train_y = torch.tensor(y_values, dtype=torch.double).unsqueeze(-1)

        fit_seed = int(rng.integers(0, 2**31 - 1))
        torch.manual_seed(fit_seed)

        param_handling = {
            "plateau_width": {"method": "manual", "value": self.plateau_width},
            "c": {"method": "manual", "value": self.plateau_c},
            "sigma": {"method": "fit"},
            "mean": {"method": "fit"},
        }
        model = create_rcgp_model(
            train_x,
            train_y,
            param_handling_dict=param_handling,
            fitting_objective_type="wloo-cv",
            optimizer_type="lbfgs",
            standardize=True,
            fit_hyperparameters=True,
            verbose=False,
        )
        model.eval()

        grid = torch.linspace(
            0.0,
            1.0,
            self.grid_points,
            dtype=torch.double,
        ).unsqueeze(-1)
        adaptive_iteration = experiment_index - self.initial_design_points - 1
        beta = theory_guided_ucb_multiplier(adaptive_iteration)

        with torch.no_grad():
            posterior = model.posterior(grid)
            mean = posterior.mean.squeeze(-1)
            std = posterior.variance.clamp_min(0.0).sqrt().squeeze(-1)
            acquisition = mean + beta * std

        best_index = int(torch.argmax(acquisition).item())
        return float(grid[best_index, 0].item())
