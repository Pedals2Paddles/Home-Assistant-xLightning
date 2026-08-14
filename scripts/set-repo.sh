#!/usr/bin/env bash
# Point the manifest and docs at your GitHub repository.
#
#   ./scripts/set-repo.sh youruser/ha-xlightning
#
# Run this once after cloning. HACS reads the manifest's documentation and
# issue_tracker URLs, so they must resolve.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <owner/repo>" >&2
  exit 1
fi

SLUG="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLACEHOLDER="YOUR_GITHUB_USER/ha-xlightning"

cd "$ROOT"
COUNT=$(grep -rl "$PLACEHOLDER" --include='*.json' --include='*.md' . | wc -l)
grep -rl "$PLACEHOLDER" --include='*.json' --include='*.md' . \
  | xargs sed -i.bak "s|$PLACEHOLDER|$SLUG|g"
find . -name '*.bak' -delete

echo "Updated $COUNT file(s) to $SLUG"
grep -rn "github.com/$SLUG" --include='*.json' . || true
