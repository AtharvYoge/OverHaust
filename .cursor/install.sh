#!/usr/bin/env bash
# Idempotent dependency install for the Overhaust Cloud Agent environment.
# Refreshes Python backend dependencies and the web frontend's node modules.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

echo "[install] Installing Python backend dependencies..."
python3 -m pip install --user -r requirements.txt

echo "[install] Installing web frontend dependencies..."
npm install --prefix apps/web

echo "[install] Done."
