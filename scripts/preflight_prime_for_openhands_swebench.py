#!/usr/bin/env python3
"""
Preflight Prime Intellect model availability for OpenHands
SWE-bench runs.

Purpose:
- Resolve requested Prime models (default:
  scripts/hospital_lab_full_pipeline_config.yaml).
- Query Prime /models once and verify requested models are currently available.
- Emit a concise report and optional OpenHands LLM config JSON files for
  available models.

Examples:
  python scripts/preflight_prime_for_openhands_swebench.py
  python scripts/preflight_prime_for_openhands_swebench.py --strict
  python scripts/preflight_prime_for_openhands_swebench.py --models \
    "anthropic/claude-3.5-haiku,deepseek/deepseek-chat"
  python scripts/preflight_prime_for_openhands_swebench.py \
    --write-config-dir ".llm_config/prime"
  python scripts/preflight_prime_for_openhands_swebench.py \
    --auto-canonical-config
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_repo_on_syspath() -> None:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _load_dotenv_if_present() -> None:
    env_file = _repo_root() / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except ImportError:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _discover_prime_models_live(
    limit: int = 500,
) -> tuple[set[str], str | None]:
    try:
        from openai import OpenAI
    except Exception as e:  # noqa: BLE001
        return set(), f"openai SDK unavailable: {e}"

    key = (
        os.environ.get("PRIME_INTELLECT_API_KEY")
        or os.environ.get("PRIME_API_KEY")
        or ""
    ).strip()
    if not key:
        return set(), "PRIME_INTELLECT_API_KEY/PRIME_API_KEY missing"

    base = (
        os.environ.get("LABTRUST_PRIME_INTELLECT_BASE_URL")
        or "https://api.pinference.ai/api/v1"
    ).strip()
    team = (os.environ.get("LABTRUST_PRIME_TEAM_ID") or "").strip()
    headers: dict[str, str] = {"X-Prime-Team-ID": team} if team else {}

    try:
        kwargs: dict[str, Any] = {"api_key": key, "base_url": base}
        if headers:
            kwargs["default_headers"] = headers
        client = OpenAI(**kwargs)
        data = client.models.list()
        out: set[str] = set()
        for row in getattr(data, "data", [])[:limit]:
            model_id = str(getattr(row, "id", "") or "").strip()
            if model_id:
                out.add(model_id)
        return out, None
    except Exception as e:  # noqa: BLE001
        return set(), str(e)[:240]


def _models_from_hospital_config(config_path: Path) -> list[str]:
    _ensure_repo_on_syspath()
    from labtrust_gym.policy.loader import load_yaml

    data = load_yaml(config_path)
    rows = (
        data.get("prime_intellect_benchmark_models")
        if isinstance(data, dict)
        else None
    )
    out: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                backend = str(row.get("backend", "")).strip()
                model_id = str(row.get("model_id", "")).strip()
                if backend == "prime_intellect_live" and model_id:
                    out.append(model_id)
    return out


def _slugify_model_id(model_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", model_id.strip())
    safe = safe.strip("-")
    return safe or "model"


def _write_openhands_llm_configs(
    out_dir: Path,
    base_url: str,
    model_ids: list[str],
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model_id in model_ids:
        payload = {
            "model": f"openai/{model_id}",
            "base_url": base_url,
            "api_key": "${PRIME_INTELLECT_API_KEY}",
        }
        filename = f"prime-{_slugify_model_id(model_id)}.json"
        path = out_dir / filename
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def _write_canonical_openhands_llm_config(
    path: Path,
    base_url: str,
    model_id: str,
) -> None:
    payload = {
        "model": f"openai/{model_id}",
        "base_url": base_url,
        "api_key": "${PRIME_INTELLECT_API_KEY}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _parse_models_arg(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight Prime model availability for OpenHands "
            "SWE-bench benchmark runs."
        )
    )
    parser.add_argument(
        "--config",
        default="scripts/hospital_lab_full_pipeline_config.yaml",
        help=(
            "Path to hospital pipeline config with "
            "prime_intellect_benchmark_models."
        ),
    )
    parser.add_argument(
        "--models",
        default="",
        help=(
            "Optional comma-separated Prime model IDs; overrides "
            "config model list when set."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any requested model is unavailable.",
    )
    parser.add_argument(
        "--write-config-dir",
        default="",
        help=(
            "Optional output directory for OpenHands LLM config JSON "
            "files (available models only)."
        ),
    )
    parser.add_argument(
        "--json-report",
        default="",
        help=(
            "Optional path to write a machine-readable preflight "
            "report JSON."
        ),
    )
    parser.add_argument(
        "--auto-canonical-config",
        action="store_true",
        help=(
            "Write a canonical OpenHands config at .llm_config/prime.json "
            "using the first available requested model."
        ),
    )
    args = parser.parse_args()

    _load_dotenv_if_present()
    repo_root = _repo_root()

    requested_models: list[str]
    if args.models.strip():
        requested_models = _parse_models_arg(args.models)
        source = "--models"
    else:
        cfg = Path(args.config)
        if not cfg.is_absolute():
            cfg = repo_root / cfg
        requested_models = _models_from_hospital_config(cfg)
        source = str(cfg)

    if not requested_models:
        print(
            "No requested Prime models were resolved. Nothing to validate.",
            file=sys.stderr,
        )
        return 1

    available, err = _discover_prime_models_live(limit=500)
    if err:
        print(f"Prime model discovery failed: {err}", file=sys.stderr)
        return 1

    available_requested = [m for m in requested_models if m in available]
    missing_requested = [m for m in requested_models if m not in available]
    base_url = (
        os.environ.get("LABTRUST_PRIME_INTELLECT_BASE_URL")
        or "https://api.pinference.ai/api/v1"
    ).strip()

    print(f"Prime preflight source: {source}")
    print(f"Prime base URL: {base_url}")
    print(f"Requested models: {len(requested_models)}")
    print(f"Available now: {len(available_requested)}")
    print(f"Missing now: {len(missing_requested)}")
    if available_requested:
        print("Available requested models:")
        for mid in available_requested:
            print(f"  - {mid}")
    if missing_requested:
        print("Missing requested models:")
        for mid in missing_requested:
            print(f"  - {mid}")

    written_files: list[Path] = []
    if args.write_config_dir.strip():
        out_dir = Path(args.write_config_dir)
        if not out_dir.is_absolute():
            out_dir = repo_root / out_dir
        written_files = _write_openhands_llm_configs(
            out_dir,
            base_url,
            available_requested,
        )
        print(
            f"Wrote {len(written_files)} OpenHands config file(s) "
            f"to: {out_dir}"
        )

    canonical_config_path: Path | None = None
    canonical_model: str | None = None
    if args.auto_canonical_config:
        if not available_requested:
            print(
                "Cannot write canonical .llm_config/prime.json: "
                "no requested models are currently available.",
                file=sys.stderr,
            )
            return 3
        canonical_model = available_requested[0]
        canonical_config_path = repo_root / ".llm_config" / "prime.json"
        _write_canonical_openhands_llm_config(
            canonical_config_path,
            base_url,
            canonical_model,
        )
        print(
            "Wrote canonical OpenHands config: "
            f"{canonical_config_path} (model={canonical_model})"
        )

    if args.json_report.strip():
        report_path = Path(args.json_report)
        if not report_path.is_absolute():
            report_path = repo_root / report_path
        payload = {
            "source": source,
            "prime_base_url": base_url,
            "requested_models": requested_models,
            "available_requested_models": available_requested,
            "missing_requested_models": missing_requested,
            "available_model_count_total": len(available),
            "strict_mode": bool(args.strict),
            "wrote_config_files": [str(p) for p in written_files],
            "wrote_canonical_config": str(canonical_config_path)
            if canonical_config_path is not None
            else None,
            "canonical_model": canonical_model,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote JSON report: {report_path}")

    if missing_requested and args.strict:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
