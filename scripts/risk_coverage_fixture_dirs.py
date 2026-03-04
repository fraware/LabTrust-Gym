"""Print --runs args for risk register export used by coverage gate (single source of run dirs)."""

from __future__ import annotations

import argparse

# Canonical run dirs for validate-coverage --strict in CI (ui_fixtures + minimal coord pack fixture).
# coord_pack_fixture_minimal has only pack_summary.csv so evidence is marked synthetic: true.
RISK_COVERAGE_FIXTURE_DIRS = [
    "tests/fixtures/ui_fixtures",
    "tests/fixtures/coord_pack_fixture_minimal",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Print fixture run dirs for risk coverage CI.")
    parser.add_argument(
        "--dirs-only",
        action="store_true",
        help="Print one directory per line (for verify_run_evidence); default prints --runs d1 --runs d2 ...",
    )
    args = parser.parse_args()
    if args.dirs_only:
        for d in RISK_COVERAGE_FIXTURE_DIRS:
            print(d)
    else:
        out = " ".join(f"--runs {d}" for d in RISK_COVERAGE_FIXTURE_DIRS)
        print(out, end="")


if __name__ == "__main__":
    main()
