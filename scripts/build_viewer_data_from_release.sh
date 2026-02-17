#!/usr/bin/env bash
# Build viewer-data/latest/ from the release artifact chain (package-release minimal + export-risk-register).
# Used by CI viewer-data-from-release. Writes latest.json and copies the bundle so the viewer can load "latest release."
#
# Usage: ./scripts/build_viewer_data_from_release.sh [work_dir]
#   work_dir: optional; default is a temp dir (script runs package-release then export into it).
#
# Env: REPO_ROOT, SEED_BASE (default 100). No network.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
WORK_DIR="${1:-}"
if [ -z "$WORK_DIR" ]; then
  WORK_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t labtrust_viewer_release)
  trap 'rm -rf "$WORK_DIR"' EXIT
fi
mkdir -p "$WORK_DIR"
cd "$REPO_ROOT"

SEED_BASE="${SEED_BASE:-100}"
export LABTRUST_ALLOW_NETWORK="${LABTRUST_ALLOW_NETWORK:-0}"
LATEST_DIR="$REPO_ROOT/viewer-data/latest"
mkdir -p "$LATEST_DIR"

if command -v labtrust >/dev/null 2>&1; then
  LABTRUST=(labtrust)
else
  LABTRUST=(python3 -m labtrust_gym.cli.main)
fi

echo "=== package-release (minimal) ==="
"${LABTRUST[@]}" package-release --profile minimal --seed-base "$SEED_BASE" --out "$WORK_DIR"
echo "=== export-risk-register ==="
"${LABTRUST[@]}" export-risk-register --out "$WORK_DIR" --runs "$WORK_DIR"

BUNDLE="$WORK_DIR/RISK_REGISTER_BUNDLE.v0.1.json"
if [ ! -f "$BUNDLE" ]; then
  echo "Bundle not found: $BUNDLE"
  exit 1
fi

cp "$BUNDLE" "$LATEST_DIR/RISK_REGISTER_BUNDLE.v0.1.json"
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "")
VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('labtrust-gym'))" 2>/dev/null || echo "0.0.0")
GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
echo "{\"git_sha\": \"$GIT_SHA\", \"version\": \"$VERSION\", \"generated_at\": \"$GENERATED_AT\", \"bundle_file\": \"RISK_REGISTER_BUNDLE.v0.1.json\"}" > "$LATEST_DIR/latest.json"
echo "Viewer-data/latest built at $LATEST_DIR (latest.json + bundle)."
