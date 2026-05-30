#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "This script must be sourced to activate the virtual environment." >&2
  echo "Usage: source scripts/activate.sh [venv_path]" >&2
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${1:-"$PROJECT_ROOT/.venv"}"
ACTIVATE_FILE="$VENV_DIR/bin/activate"

if [[ ! -f "$ACTIVATE_FILE" ]]; then
  echo "Virtual environment not found: $VENV_DIR" >&2
  echo "Create it with: python3 -m venv \"$VENV_DIR\"" >&2
  return 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE_FILE"

echo "Activated virtual environment: $VIRTUAL_ENV"
