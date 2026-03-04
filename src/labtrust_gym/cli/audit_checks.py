"""
Audit/doctor checks: Python env, extras, filesystem, policy resolution.
Each check returns {id, status, detail, remediation}; status is "pass" | "warn" | "fail".
Required checks (fail => exit 1): python_path, policy_validation, pytest_available, env_extras.
Optional (warn only): plots, marl, llm backends.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def check_python_path() -> dict[str, Any]:
    id_ = "python_path"
    exe = sys.executable
    detail = f"executable={exe}"
    return {"id": id_, "status": "pass", "detail": detail, "remediation": ""}


def check_venv() -> dict[str, Any]:
    id_ = "venv"
    venv = os.environ.get("VIRTUAL_ENV")
    conda = os.environ.get("CONDA_PREFIX")
    if venv:
        return {"id": id_, "status": "pass", "detail": f"VIRTUAL_ENV={venv}", "remediation": ""}
    if conda:
        return {"id": id_, "status": "pass", "detail": f"CONDA_PREFIX={conda}", "remediation": ""}
    return {
        "id": id_,
        "status": "warn",
        "detail": "No VIRTUAL_ENV or CONDA_PREFIX set",
        "remediation": "Use a venv or conda env for isolation.",
    }


def _try_import(name: str, attr: str | None = None) -> tuple[bool, str]:
    try:
        m = __import__(name)
        if attr:
            v = getattr(m, attr, None)
            return True, str(v) if v is not None else "ok"
        return True, getattr(m, "__version__", "ok")
    except ImportError:
        return False, "not installed"


def check_extras_env() -> dict[str, Any]:
    """Required for default smoke: pettingzoo, gymnasium."""
    id_ = "extras_env"
    pettingzoo_ok, pz_ver = _try_import("pettingzoo")
    gym_ok, gym_ver = _try_import("gymnasium")
    if pettingzoo_ok and gym_ok:
        return {
            "id": id_,
            "status": "pass",
            "detail": f"pettingzoo={pz_ver}, gymnasium={gym_ver}",
            "remediation": "",
        }
    missing = []
    if not pettingzoo_ok:
        missing.append("pettingzoo")
    if not gym_ok:
        missing.append("gymnasium")
    return {
        "id": id_,
        "status": "fail",
        "detail": f"missing: {', '.join(missing)}",
        "remediation": 'pip install -e ".[env]"',
    }


def check_extras_dev() -> dict[str, Any]:
    """pytest required for tests."""
    id_ = "extras_dev"
    ok, ver = _try_import("pytest")
    if ok:
        return {"id": id_, "status": "pass", "detail": f"pytest={ver}", "remediation": ""}
    return {
        "id": id_,
        "status": "fail",
        "detail": "pytest not installed",
        "remediation": 'pip install -e ".[dev]"',
    }


def check_extras_plots() -> dict[str, Any]:
    id_ = "extras_plots"
    ok, ver = _try_import("matplotlib")
    if ok:
        return {"id": id_, "status": "pass", "detail": f"matplotlib={ver}", "remediation": ""}
    return {
        "id": id_,
        "status": "warn",
        "detail": "matplotlib not installed",
        "remediation": 'pip install -e ".[plots]" for make-plots.',
    }


def check_extras_marl() -> dict[str, Any]:
    id_ = "extras_marl"
    ok, _ = _try_import("stable_baselines3")
    if ok:
        return {"id": id_, "status": "pass", "detail": "stable_baselines3 ok", "remediation": ""}
    return {
        "id": id_,
        "status": "warn",
        "detail": "stable_baselines3 not installed",
        "remediation": 'pip install -e ".[marl]" for PPO.',
    }


def check_llm_backends() -> dict[str, Any]:
    id_ = "llm_backends"
    openai_ok, _ = _try_import("openai")
    anthropic_ok, _ = _try_import("anthropic")
    detail_parts = []
    if openai_ok:
        detail_parts.append("openai")
    if anthropic_ok:
        detail_parts.append("anthropic")
    if not detail_parts:
        return {
            "id": id_,
            "status": "warn",
            "detail": "No openai or anthropic; llm_live backends unavailable",
            "remediation": 'pip install -e ".[llm_openai]" or ".[llm_anthropic]" for live LLM.',
        }
    return {"id": id_, "status": "pass", "detail": ",".join(detail_parts), "remediation": ""}


def check_filesystem_temp() -> dict[str, Any]:
    id_ = "filesystem_temp"
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(delete=True) as f:
            f.write(b"x")
        return {"id": id_, "status": "pass", "detail": "temp write ok", "remediation": ""}
    except Exception as e:
        return {
            "id": id_,
            "status": "fail",
            "detail": str(e),
            "remediation": "Fix filesystem permissions or TMPDIR.",
        }


def check_policy_resolution(root: Path) -> dict[str, Any]:
    id_ = "policy_resolution"
    try:
        from labtrust_gym.config import get_policy_dir, get_policy_source
        from labtrust_gym.policy.validate import validate_policy

        policy_dir = get_policy_dir(root)
        source_info = get_policy_source()
        detail = f"policy_dir={policy_dir}"
        if source_info:
            detail += f"; policy_source={source_info[0]}"
        errs = validate_policy(root, partner_id=None)
        if errs:
            return {
                "id": id_,
                "status": "fail",
                "detail": f"{detail}; validate_policy errors={len(errs)}",
                "remediation": "Run labtrust validate-policy and fix reported errors.",
            }
        return {"id": id_, "status": "pass", "detail": detail, "remediation": ""}
    except Exception as e:
        return {
            "id": id_,
            "status": "fail",
            "detail": str(e),
            "remediation": "Run from repo root or set LABTRUST_POLICY_DIR to the policy directory.",
        }


REQUIRED_CHECK_IDS = frozenset(
    {"python_path", "venv", "extras_env", "extras_dev", "filesystem_temp", "policy_resolution"}
)


def run_doctor_checks(root: Path) -> tuple[list[dict[str, Any]], bool]:
    """Run all doctor checks. Returns (checks, overall_pass). overall_pass is False if any required check fails."""
    checks = []
    checks.append(check_python_path())
    checks.append(check_venv())
    checks.append(check_extras_env())
    checks.append(check_extras_dev())
    checks.append(check_extras_plots())
    checks.append(check_extras_marl())
    checks.append(check_llm_backends())
    checks.append(check_filesystem_temp())
    checks.append(check_policy_resolution(root))
    required_failed = any(c["status"] == "fail" and c["id"] in REQUIRED_CHECK_IDS for c in checks)
    overall_pass = not required_failed
    return checks, overall_pass
