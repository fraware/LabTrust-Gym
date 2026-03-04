#!/usr/bin/env python3
"""
Build episode_bundle.json from a run directory for the simulation viewer.

Reads episode log (required), optional METHOD_TRACE and coord_decisions JSONL,
groups by step, attaches lab_design, writes episode_bundle.v0.1 JSON.

Usage:
  python scripts/build_episode_bundle.py --run-dir <path> [--out <path>]
  python scripts/build_episode_bundle.py --episode-log <path> [--out <path>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from labtrust_gym.export.episode_bundle import (  # noqa: E402
    build_bundle_from_run_dir,
    write_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build episode_bundle.json for the simulation viewer.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Run dir (episode_log.jsonl or logs/*.jsonl, METHOD_TRACE, coord_decisions)",
    )
    parser.add_argument(
        "--episode-log",
        type=Path,
        default=None,
        help="Explicit episode log JSONL path (overrides --run-dir lookup)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: run_dir/episode_bundle.json or stdout)",
    )
    args = parser.parse_args()

    if args.run_dir is None and args.episode_log is None:
        parser.error("One of --run-dir or --episode-log is required")

    run_dir = Path(args.run_dir) if args.run_dir else args.episode_log.parent
    episode_log = Path(args.episode_log) if args.episode_log else None

    try:
        bundle = build_bundle_from_run_dir(
            run_dir,
            episode_log_path=episode_log,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    out_path = args.out
    if out_path is not None:
        out_path = Path(out_path)
        if out_path.is_dir():
            out_path = out_path / "episode_bundle.json"
        write_bundle(bundle, out_path)
        print(f"Wrote {out_path}")
    else:
        import json

        print(json.dumps(bundle, sort_keys=True, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
