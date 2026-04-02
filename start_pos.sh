#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ".env" ]]; then
  echo "[ERROR] .env file not found in: $SCRIPT_DIR"
  echo "Create .env first (you can copy from .env.example)."
  exit 1
fi

# Export all variables from .env
set -a
# shellcheck disable=SC1091
source ".env"
set +a

if [[ -z "${PAYSTACK_SECRET_KEY:-}" ]]; then
  echo "[ERROR] PAYSTACK_SECRET_KEY is empty in .env"
  exit 1
fi

PYTHON_CMD="python"
if [[ -x ".venv/Scripts/python.exe" ]]; then
  PYTHON_CMD=".venv/Scripts/python.exe"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_CMD=".venv/bin/python"
fi

echo "[INFO] Running POS with: $PYTHON_CMD"
exec "$PYTHON_CMD" main.py
