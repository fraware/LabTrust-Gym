"""Reconstruction CLI helper for clean-checkout VA packs."""

from __future__ import annotations

import argparse
import json
import sys

from labtrust_gym.verifier_assurance.campaign.export import reconstruct_campaign


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct/validate a VA campaign pack")
    parser.add_argument("--pack", required=True, help="Path to campaign pack directory")
    args = parser.parse_args(argv)
    result = reconstruct_campaign(args.pack)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    sys.exit(main())
