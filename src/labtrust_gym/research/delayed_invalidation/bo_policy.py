"""Research-only Bayesian-optimization policies for protocol v0.1.3.

Heavy dependencies are imported lazily so the LabTrust-Gym base package remains
lightweight. Install the frozen study environment from the optimizer
requirements file under research/delayed_evidence_invalidation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

import numpy as np

from .campaign import PolicyObservation


def observed_utility(reported_ph: float, *, target_ph: float = 7.40) -> float:
    """Optimizer-visible scalar objective frozen in protocol v0.1.3."""
    return -((float(reported_ph) - float(target_ph)) ** 2)


def latent_utility(true_ph: float, *, target_ph: float = 7.40) -> float:
    """Hidden adjudication utility; never expose this value to acquisition."""
    return -((float(true_ph) - float(target_ph)) ** 2)


def theory_guided_ucb_multiplier(adaptive_iteration_zero_based: int) -> float:
    """Released-code theory-guided UCB multiplier frozen in protocol v0.1.3."""
    if adaptive_iteration_zero_based < 0:
        raise ValueError("adaptive_iteration_zero_based must be non-negative")
    return max(
        1.0,
        1.7 * math.sqrt(2.0 * math.log(adaptive_iteration_zero_based + 2.0)),
    )


class MissingResearchDependency(RuntimeError):
    """Raised when a research-only optimizer dependency is unavailable."""


def _load_botorch() -> tuple[Any, Any, Any, tuple[Any, Any]]:
    try:
        import torch
        from botorch.fit import fit_gpytorch_mll
        from botorch.models import SingleTaskGP
        from botorch.models.transforms.outcome import Standardize
        from gpytorch.mlls import ExactMarginalLogLikelihood
    except ImportError as exc:
        raise MissingResearchDependency(
            "GP-UCB research policy requires the frozen optimizer environment; "
            "install the study optimizer requirements file"
        ) from exc
    return torch, fit_gpytorch_mll, SingleTaskGP, (Standardize, ExactMarginalLogLikelihood)


@dataclass
class GpUcbPolicy:
    """Matched full-history or sliding-window GP-UCB policy.

    The policy models observed utility derived from reported pH. It refits a
    standardized SingleTaskGP at every adaptive decision and maximizes UCB over
    the frozen 1001-point grid. A null window is the primary full-history
    policy; windows 20, 40, and 80 are preregistered non-stationarity controls.
    """

    target_ph: float = 7.40
    window_size: int | None = None
    grid_points: int = 1001
    initial_design_points: int = 16

    def __post_init__(self) -> None:
        if self.window_size is not None and self.window_size <= 0:
            raise ValueError("window_size must be positive or None")
        if self.grid_points < 2:
            raise ValueError("grid_points must be >= 2")
        if self.initial_design_points <= 0:
            raise ValueError("initial_design_points must be positive")

    def _training_observations(
        self,
        observations: Sequence[PolicyObservation],
    ) -> Sequence[PolicyObservation]:
        if self.window_size is None:
            return observations
        return observations[-self.window_size :]

    def choose_x(
        self,
        observations: Sequence[PolicyObservation],
        *,
        experiment_index: int,
        rng: np.random.Generator,
    ) -> float:
        """Choose the next x using only policy-visible observations."""
        if experiment_index <= self.initial_design_points:
            raise ValueError("GpUcbPolicy should only be called after initial design")
        if not observations:
            raise ValueError("observations must be non-empty")

        torch, fit_gpytorch_mll, SingleTaskGP, support = _load_botorch()
        Standardize, ExactMarginalLogLikelihood = support

        training = self._training_observations(observations)
        x_values = np.asarray([obs.x for obs in training], dtype=float)
        y_values = np.asarray(
            [
                observed_utility(obs.reported_ph, target_ph=self.target_ph)
                for obs in training
            ],
            dtype=float,
        )

        train_x = torch.tensor(x_values, dtype=torch.double).unsqueeze(-1)
        train_y = torch.tensor(y_values, dtype=torch.double).unsqueeze(-1)

        fit_seed = int(rng.integers(0, 2**31 - 1))
        torch.manual_seed(fit_seed)

        model = SingleTaskGP(
            train_x,
            train_y,
            outcome_transform=Standardize(m=1),
        )
        mll = ExactMarginalLogLikelihood(model.likelihood, model)
        fit_gpytorch_mll(mll)
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


def full_history_gp_ucb() -> GpUcbPolicy:
    """Primary full-history policy."""
    return GpUcbPolicy(window_size=None)


def sliding_window_gp_ucb(window_size: int) -> GpUcbPolicy:
    """Preregistered non-stationarity comparator factory."""
    if window_size not in (20, 40, 80):
        raise ValueError("preregistered sliding windows are 20, 40, and 80")
    return GpUcbPolicy(window_size=window_size)
