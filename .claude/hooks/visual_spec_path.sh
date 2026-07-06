#!/usr/bin/env bash
# Print the path where Claude should write the lightweight visual spec JSON for
# a directory. The hook looks here (keyed by cwd) when it fires.
# Usage: visual_spec_path.sh [cwd]
set -euo pipefail
CWD="${1:-$PWD}"
KEY="$(printf '%s' "$CWD" | shasum | cut -c1-16)"
mkdir -p "$HOME/.plan-review/pending"
echo "$HOME/.plan-review/pending/$KEY.json"
