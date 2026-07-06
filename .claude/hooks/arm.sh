#!/usr/bin/env bash
# Arm a ONE-SHOT plan review for a directory. The hook stays dormant (normal
# plan mode) until this runs; the next ExitPlanMode in that dir opens the browser.
# Usage: arm.sh [cwd]   (defaults to $PWD)
set -euo pipefail
CWD="${1:-$PWD}"
KEY="$(printf '%s' "$CWD" | shasum | cut -c1-16)"   # sha1 hex, first 16 (matches the hook)
mkdir -p "$HOME/.plan-review/triggers"
mkdir -p "$HOME/.plan-review/pending"
rm -f "$HOME/.plan-review/pending/$KEY.json" "$HOME/.plan-review/pending/$KEY.html"
touch "$HOME/.plan-review/triggers/$KEY"
echo "✓ Plan review armed for: $CWD"
echo "  Your next plan submission will open in the browser (one-shot)."
