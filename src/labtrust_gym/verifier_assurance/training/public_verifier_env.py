"""Gymnasium environment whose reward is V_public accept/reject (LT-VA-13)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    PublicVerifier,
    default_public_profile,
    deny_hidden_in_mapping,
)
from labtrust_gym.verifier_assurance.studies.outcome_process import (
    EXPLOIT_FAMILIES,
    seed_exploit_state,
)

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

# Discrete action vocabulary: exploit families the policy may attempt.
ACTION_FAMILIES: tuple[str, ...] = tuple(EXPLOIT_FAMILIES)


class PublicVerifierEnv:
    """
    Offline bandit/MDP wrapper: action selects an exploit family; reward is
    1.0 iff V_public accepts the seeded state. Observations never include
    hidden labels. Gymnasium-compatible API without requiring SB3.
    """

    metadata = {"render_modes": [], "claim_boundary": CLAIM_BOUNDARY}

    def __init__(
        self,
        public_verifier: PublicVerifier | None = None,
        *,
        horizon: int = 8,
        seed: int = 0,
        allowed_families: tuple[str, ...] | None = None,
    ) -> None:
        try:
            import gymnasium as gym
            from gymnasium import spaces
        except ImportError as exc:  # pragma: no cover - gymnasium is a core dep
            raise ImportError(
                'gymnasium is required for PublicVerifierEnv. Install with: pip install -e "."'
            ) from exc

        self._gym = gym
        self._public = public_verifier or PublicVerifier(default_public_profile())
        families = allowed_families or ACTION_FAMILIES
        for fam in families:
            if fam not in ACTION_FAMILIES:
                raise ValueError(f"unknown exploit family: {fam}")
        self._families = tuple(families)
        self._horizon = max(1, int(horizon))
        self._step_i = 0
        self._rng = np.random.default_rng(int(seed))
        self._last_reward = 0.0
        self._last_accepted = False
        n = len(self._families)
        # obs: [onehot(last_action or none), accepted_flag, step_frac]
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(n + 1 + 2,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(n)
        self._last_action: int | None = None

    @property
    def families(self) -> tuple[str, ...]:
        return self._families

    @property
    def public_verifier_id(self) -> str:
        return self._public.verifier_id

    def _obs(self) -> np.ndarray:
        n = len(self._families)
        onehot = np.zeros(n + 1, dtype=np.float32)
        if self._last_action is None:
            onehot[n] = 1.0
        else:
            onehot[int(self._last_action)] = 1.0
        accepted = 1.0 if self._last_accepted else 0.0
        step_frac = float(self._step_i) / float(self._horizon)
        return np.concatenate(
            [onehot, np.array([accepted, step_frac], dtype=np.float32)]
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        if seed is not None:
            self._rng = np.random.default_rng(int(seed))
        self._step_i = 0
        self._last_action = None
        self._last_reward = 0.0
        self._last_accepted = False
        info = {
            "public_verifier_id": self.public_verifier_id,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        if options:
            info["options_keys"] = sorted(str(k) for k in options.keys())
        obs = self._obs()
        deny_hidden_in_mapping({"obs": obs.tolist(), "info": info})
        return obs, info

    def step(self, action: int | np.integer) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        a = int(action)
        if a < 0 or a >= len(self._families):
            raise ValueError(f"action out of range: {a}")
        family = self._families[a]
        state = seed_exploit_state(family)
        deny_hidden_in_mapping(state)
        decision = self._public.evaluate(state)
        reward = 1.0 if decision.accepted else 0.0
        self._last_action = a
        self._last_reward = reward
        self._last_accepted = bool(decision.accepted)
        self._step_i += 1
        terminated = self._step_i >= self._horizon
        truncated = False
        info = {
            "family": family,
            "public_accepted": bool(decision.accepted),
            "public_verifier_id": self.public_verifier_id,
            "reason_codes": list(decision.reason_codes),
            "claim_boundary": CLAIM_BOUNDARY,
        }
        deny_hidden_in_mapping(info)
        return self._obs(), float(reward), terminated, truncated, info

    def close(self) -> None:
        return None
