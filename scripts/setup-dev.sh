#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --requirement requirements.txt
.venv/bin/pre-commit install
