#!/bin/zsh
set -euo pipefail

REPO_DIR="$HOME/code/personal/apandeya"
LOG_FILE="$HOME/Library/Logs/apandeya-coding-velocity.log"

exec >> "$LOG_FILE" 2>&1
echo "=== $(date) ==="

cd "$REPO_DIR"
git pull --ff-only origin main

python3 scripts/gen_coding_velocity.py

if [ -z "$(git status --porcelain -- stats/ README.md)" ]; then
  echo "No changes, skipping commit."
  exit 0
fi

git add stats/ README.md
git commit -m "chore: refresh coding velocity stats"
git push origin main
echo "Pushed update."
