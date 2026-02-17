#!/usr/bin/env bash
# Build the canonical release fixture used as the regression anchor for verify-release.
# Run from a known-good commit; then commit tests/fixtures/release_fixture_minimal/ (minimal set).
#
# Usage: ./scripts/build_release_fixture.sh [repo_root]
#   repo_root: optional; default is parent of script dir.
#
# Env:
#   SEED_BASE  seed for package-release (default: 100)
#
# Exit: 0 if full chain passes; fixture is written to tests/fixtures/release_fixture_minimal.
set -eu

REPO_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
SEED_BASE="${SEED_BASE:-100}"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/release_fixture_minimal"

cd "$REPO_ROOT"
mkdir -p "$FIXTURE_DIR"
export LABTRUST_ALLOW_NETWORK="${LABTRUST_ALLOW_NETWORK:-0}"

if command -v labtrust >/dev/null 2>&1; then
  LABTRUST=(labtrust)
elif command -v python >/dev/null 2>&1; then
  LABTRUST=(python -m labtrust_gym.cli.main)
else
  LABTRUST=(python3 -m labtrust_gym.cli.main)
fi

echo "=== 1/4 package-release (minimal) ==="
"${LABTRUST[@]}" package-release --profile minimal --seed-base "$SEED_BASE" --out "$FIXTURE_DIR"
echo "=== 2/4 export-risk-register ==="
"${LABTRUST[@]}" export-risk-register --out "$FIXTURE_DIR" --runs "$FIXTURE_DIR"
echo "=== 3/4 build-release-manifest ==="
"${LABTRUST[@]}" build-release-manifest --release-dir "$FIXTURE_DIR"
echo "=== 4/4 verify-release --strict-fingerprints ==="
"${LABTRUST[@]}" verify-release --release-dir "$FIXTURE_DIR" --strict-fingerprints

echo "Release fixture built at $FIXTURE_DIR. Commit only the minimal set needed for verify-release."
