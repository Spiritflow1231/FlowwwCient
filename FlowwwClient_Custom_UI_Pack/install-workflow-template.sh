#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(pwd)"
if [[ ! -d "$REPO_ROOT/.git" ]]; then
  echo "Run this script from the root of your Git repository (the folder containing .git)." >&2
  exit 1
fi
mkdir -p "$REPO_ROOT/.github/workflows"
cp "$ROOT_DIR/workflow-template/build-flowwwclient-mod.yml" "$REPO_ROOT/.github/workflows/build-flowwwclient-mod.yml"
echo "Copied workflow to .github/workflows/build-flowwwclient-mod.yml"
echo "Note: this builds the Fabric mod JAR, not the existing Python launcher EXE."
