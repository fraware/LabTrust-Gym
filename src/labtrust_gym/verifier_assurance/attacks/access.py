"""Attack access classes with query logging and cross-class denial (LT-VA-09)."""

from __future__ import annotations

import copy
from enum import Enum
from typing import Any, Callable, Mapping, Protocol

from labtrust_gym.verifier_assurance.oracle.dual_oracle import PublicVerifier, VerifierDecision

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"


class AccessClass(str, Enum):
    SCRIPTED = "scripted"
    PRETRAINED = "pretrained"
    RL_TRAINED = "rl_trained"
    BLACK_BOX = "black_box"
    GRAY_BOX = "gray_box"
    WHITE_BOX = "white_box"
    MULTI_AGENT = "multi_agent"
    FROZEN_CHECKPOINT = "frozen_checkpoint"


class AttackAccessError(PermissionError):
    """Cross-class leakage or unauthorized capability access."""


class AttackHandle(Protocol):
    access_class: AccessClass

    def query_verifier(self, state: Mapping[str, Any]) -> VerifierDecision: ...


class BaseAttackHandle:
    def __init__(
        self,
        access_class: AccessClass,
        public_verifier: PublicVerifier,
        *,
        checkpoint_id: str | None = None,
    ) -> None:
        self.access_class = access_class
        self._public = public_verifier
        self._checkpoint_id = checkpoint_id
        self._query_log: list[dict[str, Any]] = []
        self.claim_boundary = CLAIM_BOUNDARY

    @property
    def query_log(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._query_log)

    def query_verifier(self, state: Mapping[str, Any]) -> VerifierDecision:
        decision = self._public.evaluate(state)
        self._query_log.append(
            {
                "access_class": self.access_class.value,
                "decision": decision.to_dict(),
            }
        )
        return decision

    def as_white_box(self) -> "WhiteBoxAttackHandle":
        raise AttackAccessError(
            f"cannot escalate {self.access_class.value} handle to white_box"
        )

    def verifier_internals(self) -> dict[str, Any]:
        raise AttackAccessError(
            f"{self.access_class.value} cannot access verifier internals"
        )


class BlackBoxAttackHandle(BaseAttackHandle):
    def __init__(self, public_verifier: PublicVerifier) -> None:
        super().__init__(AccessClass.BLACK_BOX, public_verifier)


class GrayBoxAttackHandle(BaseAttackHandle):
    def __init__(self, public_verifier: PublicVerifier, explanations: Mapping[str, Any]) -> None:
        super().__init__(AccessClass.GRAY_BOX, public_verifier)
        self._explanations = copy.deepcopy(dict(explanations))

    def explanation(self) -> dict[str, Any]:
        return copy.deepcopy(self._explanations)


class WhiteBoxAttackHandle(BaseAttackHandle):
    def __init__(self, public_verifier: PublicVerifier, verifier_profile: Mapping[str, Any]) -> None:
        super().__init__(AccessClass.WHITE_BOX, public_verifier)
        self._verifier_profile = copy.deepcopy(dict(verifier_profile))

    def verifier_internals(self) -> dict[str, Any]:
        return copy.deepcopy(self._verifier_profile)

    def as_white_box(self) -> "WhiteBoxAttackHandle":
        return self


class ScriptedAttackHandle(BaseAttackHandle):
    def __init__(
        self,
        public_verifier: PublicVerifier,
        script: Callable[[Mapping[str, Any]], dict[str, Any]],
    ) -> None:
        super().__init__(AccessClass.SCRIPTED, public_verifier)
        self._script = script

    def act(self, obs: Mapping[str, Any]) -> dict[str, Any]:
        return self._script(obs)


class RLTrainedAttackHandle(BaseAttackHandle):
    def __init__(self, public_verifier: PublicVerifier, policy_id: str) -> None:
        super().__init__(AccessClass.RL_TRAINED, public_verifier)
        self.policy_id = policy_id


class FrozenCheckpointHandle(BaseAttackHandle):
    def __init__(self, public_verifier: PublicVerifier, checkpoint_id: str) -> None:
        super().__init__(AccessClass.FROZEN_CHECKPOINT, public_verifier, checkpoint_id=checkpoint_id)


def open_attack_handle(
    access_class: AccessClass | str,
    public_verifier: PublicVerifier,
    **kwargs: Any,
) -> BaseAttackHandle:
    ac = AccessClass(access_class)
    if ac == AccessClass.BLACK_BOX:
        return BlackBoxAttackHandle(public_verifier)
    if ac == AccessClass.GRAY_BOX:
        return GrayBoxAttackHandle(public_verifier, kwargs.get("explanations") or {})
    if ac == AccessClass.WHITE_BOX:
        profile = kwargs.get("verifier_profile")
        if not profile:
            raise AttackAccessError("white_box requires verifier_profile")
        return WhiteBoxAttackHandle(public_verifier, profile)
    if ac == AccessClass.SCRIPTED:
        script = kwargs.get("script")
        if script is None:
            raise AttackAccessError("scripted requires script callable")
        return ScriptedAttackHandle(public_verifier, script)
    if ac == AccessClass.RL_TRAINED:
        return RLTrainedAttackHandle(public_verifier, str(kwargs.get("policy_id") or "rl-policy"))
    if ac == AccessClass.PRETRAINED:
        return BaseAttackHandle(AccessClass.PRETRAINED, public_verifier)
    if ac == AccessClass.MULTI_AGENT:
        return BaseAttackHandle(AccessClass.MULTI_AGENT, public_verifier)
    if ac == AccessClass.FROZEN_CHECKPOINT:
        cid = kwargs.get("checkpoint_id")
        if not cid:
            raise AttackAccessError("frozen_checkpoint requires checkpoint_id")
        return FrozenCheckpointHandle(public_verifier, str(cid))
    raise AttackAccessError(f"unsupported access class: {ac}")
