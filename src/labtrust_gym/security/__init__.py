"""Security: adversarial detection, agent capabilities, secrets, fs safety (B002, B006, B008)."""

from labtrust_gym.security.adversarial_detection import (
    DetectionResult,
    detect_adversarial,
    load_adversarial_detection_policy,
)
from labtrust_gym.security.agent_capabilities import (
    AGENT_CAPABILITY_DENY,
    AGENT_OVERRIDE_BUDGET_EXCEEDED,
    AGENT_RATE_LIMIT,
    check_capability,
    get_profile_for_agent,
    load_agent_capabilities,
)
from labtrust_gym.security.fs_safety import (
    assert_under_runs_dir,
    get_runs_dir,
    is_safe_filename_component,
    resolve_within_base,
)
from labtrust_gym.security.output_shaping import (
    build_run_summary,
    obfuscate_identifier,
    shape_llm_decision,
    shape_signature_verification,
    summary_contains_no_forbidden_fields,
)
from labtrust_gym.security.risk_injections import (
    InjectionConfig,
    RiskInjector,
    make_injector,
)
from labtrust_gym.security.secret_scrubber import (
    get_secret_env_names,
    scrub_dict_for_log,
    scrub_secrets,
)

__all__ = [
    "AGENT_CAPABILITY_DENY",
    "AGENT_OVERRIDE_BUDGET_EXCEEDED",
    "AGENT_RATE_LIMIT",
    "DetectionResult",
    "assert_under_runs_dir",
    "check_capability",
    "detect_adversarial",
    "get_profile_for_agent",
    "get_runs_dir",
    "get_secret_env_names",
    "is_safe_filename_component",
    "load_adversarial_detection_policy",
    "load_agent_capabilities",
    "obfuscate_identifier",
    "resolve_within_base",
    "shape_llm_decision",
    "shape_signature_verification",
    "summary_contains_no_forbidden_fields",
    "scrub_dict_for_log",
    "scrub_secrets",
    "InjectionConfig",
    "RiskInjector",
    "make_injector",
]
