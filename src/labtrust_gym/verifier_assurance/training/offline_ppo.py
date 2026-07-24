"""
Deterministic offline PPO against V_public.

Default path is a pure-numpy clipped-surrogate trainer (no SB3) so CI stays
offline and non-flaky. Optional SB3 path is gated behind extras and records
frozen checkpoint digests the same way.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from labtrust_gym.util.json_utils import canonical_json
from labtrust_gym.verifier_assurance.oracle.dual_oracle import PublicVerifier
from labtrust_gym.verifier_assurance.training.public_verifier_env import (
    ACTION_FAMILIES,
    PublicVerifierEnv,
)

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

TrainerBackend = Literal["numpy_ppo", "sb3_ppo"]


@dataclass(frozen=True)
class OfflinePPOConfig:
    """Hyperparameters for offline-deterministic VA training."""

    seed: int = 42
    episodes: int = 24
    horizon: int = 8
    learning_rate: float = 0.05
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    ppo_epochs: int = 4
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    backend: TrainerBackend = "numpy_ppo"
    checkpoint_dir: Path | None = None
    claim_boundary: str = CLAIM_BOUNDARY


@dataclass(frozen=True)
class PolicyCheckpoint:
    checkpoint_id: str
    policy_id: str
    trained_against: str
    backend: TrainerBackend
    seed: int
    episodes: int
    mean_public_reward: float
    logits_digest: str
    path: str | None
    preferred_family: str
    claim_boundary: str = CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "policy_id": self.policy_id,
            "trained_against": self.trained_against,
            "backend": self.backend,
            "seed": self.seed,
            "episodes": self.episodes,
            "mean_public_reward": self.mean_public_reward,
            "logits_digest": self.logits_digest,
            "path": self.path,
            "preferred_family": self.preferred_family,
            "claim_boundary": self.claim_boundary,
        }


@dataclass
class TrainResult:
    checkpoint: PolicyCheckpoint
    episode_rewards: list[float]
    backend: TrainerBackend

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "episode_rewards": list(self.episode_rewards),
            "mean_public_reward": float(np.mean(self.episode_rewards)) if self.episode_rewards else 0.0,
            "episodes": len(self.episode_rewards),
            "trained_against": self.checkpoint.trained_against,
            "backend": self.backend,
            "policy_id": self.checkpoint.policy_id,
            "checkpoint_id": self.checkpoint.checkpoint_id,
            "claim_boundary": CLAIM_BOUNDARY,
        }


class _SoftmaxPolicy:
    """Categorical policy with linear logits over observation features."""

    def __init__(self, obs_dim: int, n_actions: int, rng: np.random.Generator) -> None:
        scale = 1.0 / max(1.0, float(np.sqrt(obs_dim)))
        self.W = rng.normal(0.0, scale, size=(n_actions, obs_dim)).astype(np.float64)
        self.b = np.zeros(n_actions, dtype=np.float64)
        self.v_w = rng.normal(0.0, scale, size=(obs_dim,)).astype(np.float64)
        self.v_b = 0.0

    def logits(self, obs: np.ndarray) -> np.ndarray:
        return self.W @ obs.astype(np.float64) + self.b

    def probs(self, obs: np.ndarray) -> np.ndarray:
        z = self.logits(obs)
        z = z - np.max(z)
        e = np.exp(z)
        return e / np.sum(e)

    def value(self, obs: np.ndarray) -> float:
        return float(self.v_w @ obs.astype(np.float64) + self.v_b)

    def act(self, obs: np.ndarray, rng: np.random.Generator) -> tuple[int, float, float]:
        p = self.probs(obs)
        action = int(rng.choice(len(p), p=p))
        logp = float(np.log(p[action] + 1e-12))
        return action, logp, self.value(obs)

    def digest(self) -> str:
        payload = {
            "W": self.W.tolist(),
            "b": self.b.tolist(),
            "v_w": self.v_w.tolist(),
            "v_b": self.v_b,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def preferred_action(self, obs: np.ndarray) -> int:
        return int(np.argmax(self.probs(obs)))


def _gae(
    rewards: list[float],
    values: list[float],
    dones: list[bool],
    *,
    gamma: float,
    lam: float,
) -> tuple[np.ndarray, np.ndarray]:
    advantages: list[float] = []
    gae = 0.0
    next_value = 0.0
    for t in reversed(range(len(rewards))):
        mask = 0.0 if dones[t] else 1.0
        delta = rewards[t] + gamma * next_value * mask - values[t]
        gae = delta + gamma * lam * mask * gae
        advantages.insert(0, gae)
        next_value = values[t]
    adv = np.asarray(advantages, dtype=np.float64)
    returns = adv + np.asarray(values, dtype=np.float64)
    return adv, returns


def _train_numpy_ppo(
    env: PublicVerifierEnv,
    *,
    config: OfflinePPOConfig,
    policy_id: str,
) -> TrainResult:
    rng = np.random.default_rng(config.seed)
    obs, _info = env.reset(seed=config.seed)
    policy = _SoftmaxPolicy(obs_dim=obs.shape[0], n_actions=env.action_space.n, rng=rng)
    episode_rewards: list[float] = []

    for ep in range(config.episodes):
        obs, _ = env.reset(seed=config.seed + ep)
        traj_obs: list[np.ndarray] = []
        traj_act: list[int] = []
        traj_logp: list[float] = []
        traj_rew: list[float] = []
        traj_val: list[float] = []
        traj_done: list[bool] = []
        ep_ret = 0.0
        done = False
        while not done:
            action, logp, value = policy.act(obs, rng)
            next_obs, reward, terminated, truncated, _info = env.step(action)
            done = bool(terminated or truncated)
            traj_obs.append(obs)
            traj_act.append(action)
            traj_logp.append(logp)
            traj_rew.append(float(reward))
            traj_val.append(float(value))
            traj_done.append(done)
            ep_ret += float(reward)
            obs = next_obs
        episode_rewards.append(ep_ret)

        adv, returns = _gae(
            traj_rew,
            traj_val,
            traj_done,
            gamma=config.gamma,
            lam=config.gae_lambda,
        )
        if len(adv) > 1:
            adv = (adv - adv.mean()) / (adv.std() + 1e-8)

        for _ in range(config.ppo_epochs):
            for i in range(len(traj_obs)):
                o = traj_obs[i]
                a = traj_act[i]
                old_logp = traj_logp[i]
                probs = policy.probs(o)
                new_logp = float(np.log(probs[a] + 1e-12))
                ratio = float(np.exp(new_logp - old_logp))
                clipped = float(np.clip(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps))
                # Policy gradient on clipped surrogate (ascent)
                pg = min(ratio * adv[i], clipped * adv[i])
                # Entropy bonus
                ent = float(-np.sum(probs * np.log(probs + 1e-12)))
                # Softmax score-function gradient for chosen action
                onehot = np.zeros_like(probs)
                onehot[a] = 1.0
                grad_logits = (onehot - probs) * (pg + config.entropy_coef * ent)
                policy.W += config.learning_rate * np.outer(grad_logits, o)
                policy.b += config.learning_rate * grad_logits
                # Value MSE gradient
                v = policy.value(o)
                v_err = returns[i] - v
                policy.v_w += config.learning_rate * config.value_coef * v_err * o.astype(np.float64)
                policy.v_b += config.learning_rate * config.value_coef * v_err

    # Preferred family under blank start observation
    blank, _ = env.reset(seed=config.seed)
    preferred_idx = policy.preferred_action(blank)
    preferred_family = env.families[preferred_idx]
    logits_digest = policy.digest()
    mean_r = float(np.mean(episode_rewards)) if episode_rewards else 0.0
    body = {
        "policy_id": policy_id,
        "backend": "numpy_ppo",
        "seed": config.seed,
        "episodes": config.episodes,
        "logits_digest": logits_digest,
        "preferred_family": preferred_family,
        "trained_against": env.public_verifier_id,
        "mean_public_reward": mean_r,
    }
    checkpoint_id = "ckpt-" + hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()[:24]
    path_str: str | None = None
    if config.checkpoint_dir is not None:
        config.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = config.checkpoint_dir / f"{checkpoint_id}.json"
        payload = {
            **body,
            "checkpoint_id": checkpoint_id,
            "W": policy.W.tolist(),
            "b": policy.b.tolist(),
            "v_w": policy.v_w.tolist(),
            "v_b": policy.v_b,
            "families": list(env.families),
            "claim_boundary": CLAIM_BOUNDARY,
        }
        path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        path_str = str(path)

    ckpt = PolicyCheckpoint(
        checkpoint_id=checkpoint_id,
        policy_id=policy_id,
        trained_against=env.public_verifier_id,
        backend="numpy_ppo",
        seed=config.seed,
        episodes=config.episodes,
        mean_public_reward=mean_r,
        logits_digest=logits_digest,
        path=path_str,
        preferred_family=preferred_family,
    )
    return TrainResult(checkpoint=ckpt, episode_rewards=episode_rewards, backend="numpy_ppo")


def _sb3_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("stable_baselines3") is not None
    except Exception:
        return False


def _train_sb3_ppo(
    env: PublicVerifierEnv,
    *,
    config: OfflinePPOConfig,
    policy_id: str,
) -> TrainResult:
    if not _sb3_available():
        raise ImportError(
            'stable-baselines3 is required for backend="sb3_ppo". '
            'Install with: pip install -e ".[marl]"'
        )
    from stable_baselines3 import PPO
    from stable_baselines3.common.monitor import Monitor

    # Wrap as gymnasium Env for SB3
    class _GymAdapter(env._gym.Env):  # type: ignore[name-defined]
        metadata = env.metadata
        observation_space = env.observation_space
        action_space = env.action_space

        def reset(self, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
            return env.reset(**kwargs)

        def step(self, action: Any) -> tuple[Any, float, bool, bool, dict[str, Any]]:
            return env.step(action)

        def close(self) -> None:
            env.close()

    gym_env = Monitor(_GymAdapter())
    total_timesteps = max(config.episodes * config.horizon, config.horizon)
    model = PPO(
        "MlpPolicy",
        gym_env,
        seed=config.seed,
        verbose=0,
        n_steps=max(config.horizon, 8),
        batch_size=max(config.horizon, 8),
        learning_rate=config.learning_rate,
        gamma=config.gamma,
        gae_lambda=config.gae_lambda,
        clip_range=config.clip_eps,
        ent_coef=config.entropy_coef,
        vf_coef=config.value_coef,
    )
    model.learn(total_timesteps=total_timesteps)

    # Evaluate deterministic greedy over families via short rollouts
    episode_rewards: list[float] = []
    family_votes: dict[str, int] = {f: 0 for f in env.families}
    for ep in range(min(8, config.episodes)):
        obs, _ = env.reset(seed=config.seed + 10_000 + ep)
        done = False
        ep_ret = 0.0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            family_votes[str(info["family"])] = family_votes.get(str(info["family"]), 0) + 1
            ep_ret += float(reward)
            done = bool(terminated or truncated)
        episode_rewards.append(ep_ret)

    preferred_family = max(family_votes.items(), key=lambda kv: kv[1])[0]
    mean_r = float(np.mean(episode_rewards)) if episode_rewards else 0.0
    path_str: str | None = None
    params_digest = hashlib.sha256(repr(model.policy.parameters_to_vector()).encode("utf-8")).hexdigest()
    if config.checkpoint_dir is not None:
        config.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = config.checkpoint_dir / f"{policy_id}.sb3.zip"
        model.save(str(path))
        path_str = str(path)
        params_digest = hashlib.sha256(path.read_bytes()).hexdigest()

    body = {
        "policy_id": policy_id,
        "backend": "sb3_ppo",
        "seed": config.seed,
        "episodes": config.episodes,
        "logits_digest": params_digest,
        "preferred_family": preferred_family,
        "trained_against": env.public_verifier_id,
        "mean_public_reward": mean_r,
    }
    checkpoint_id = "ckpt-" + hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()[:24]
    ckpt = PolicyCheckpoint(
        checkpoint_id=checkpoint_id,
        policy_id=policy_id,
        trained_against=env.public_verifier_id,
        backend="sb3_ppo",
        seed=config.seed,
        episodes=config.episodes,
        mean_public_reward=mean_r,
        logits_digest=params_digest,
        path=path_str,
        preferred_family=preferred_family,
    )
    return TrainResult(checkpoint=ckpt, episode_rewards=episode_rewards, backend="sb3_ppo")


class TrainedPublicPolicy:
    """Attack/evaluate helper bound to a frozen checkpoint preference."""

    def __init__(
        self,
        checkpoint: PolicyCheckpoint,
        *,
        target_family: str | None = None,
    ) -> None:
        self.checkpoint = checkpoint
        self.policy_id = checkpoint.policy_id
        self.trained_against = checkpoint.trained_against
        self.target_family = target_family or checkpoint.preferred_family
        if self.target_family not in ACTION_FAMILIES:
            raise ValueError(f"unknown target family: {self.target_family}")
        self.episodes_trained = checkpoint.episodes

    def attack(self, public: PublicVerifier) -> dict[str, Any]:
        from labtrust_gym.verifier_assurance.studies.outcome_process import seed_exploit_state

        state = seed_exploit_state(self.target_family)
        decision = public.evaluate(state)
        return {
            "policy_id": self.policy_id,
            "checkpoint_id": self.checkpoint.checkpoint_id,
            "family": self.target_family,
            "public_accepted": decision.accepted,
            "public_reward": 1.0 if decision.accepted else 0.0,
            "state": state,
            "trained_against": self.trained_against,
            "backend": self.checkpoint.backend,
        }


def train_policy_against_public(
    public: PublicVerifier,
    *,
    policy_id: str,
    config: OfflinePPOConfig | None = None,
    allowed_families: tuple[str, ...] | None = None,
) -> TrainResult:
    """
    Train a policy directly against V_public.

    Default backend is numpy_ppo (always available, deterministic). Pass
    backend=\"sb3_ppo\" only when stable-baselines3 is installed.
    """
    cfg = config or OfflinePPOConfig()
    env = PublicVerifierEnv(
        public,
        horizon=cfg.horizon,
        seed=cfg.seed,
        allowed_families=allowed_families,
    )
    if cfg.backend == "numpy_ppo":
        return _train_numpy_ppo(env, config=cfg, policy_id=policy_id)
    if cfg.backend == "sb3_ppo":
        return _train_sb3_ppo(env, config=cfg, policy_id=policy_id)
    raise ValueError(f"unsupported backend: {cfg.backend}")
