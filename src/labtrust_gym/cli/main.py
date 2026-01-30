"""labtrust CLI: validate-policy and future commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from labtrust_gym.policy.validate import validate_policy


def _find_repo_root() -> Path:
    """Assume we run from repo root or from src; walk up to find policy/."""
    cwd = Path.cwd()
    for p in [cwd, cwd.parent]:
        if (p / "policy").is_dir():
            return p
    return cwd


def main() -> int:
    parser = argparse.ArgumentParser(prog="labtrust", description="LabTrust-Gym CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate-policy", help="Validate policy files against schemas")
    p_validate.set_defaults(func=lambda _: _run_validate_policy(_find_repo_root()))
    args = parser.parse_args()
    return args.func(args)


def _run_validate_policy(root: Path) -> int:
    """Run policy validation; print errors to stderr; return 0 on success, 1 on failure."""
    errors = validate_policy(root)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("Policy validation OK.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
