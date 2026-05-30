#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"

command_text="$(
  python3 -c 'import json, sys
data = json.load(sys.stdin)
print(data.get("command") or data.get("tool_input", {}).get("command") or "")' <<<"$input"
)"

if [[ ! "$command_text" =~ (^|[[:space:];|&])git[[:space:]]+commit($|[[:space:]]) ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

emit_deny() {
  local user_message="$1"
  local agent_message="$2"
  python3 - "$user_message" "$agent_message" <<'PY'
import json
import sys

print(json.dumps({
    "permission": "deny",
    "user_message": sys.argv[1],
    "agent_message": sys.argv[2],
}))
PY
}

if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  python_bin="$VIRTUAL_ENV/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
else
  python_bin="python3"
fi

if ! "$python_bin" -m ruff --version >/dev/null 2>&1; then
  emit_deny \
    "Commit blocked: Ruff is not installed. Install project requirements, then commit again." \
    "The before-commit quality hook could not run Ruff. Install dependencies with: $python_bin -m pip install -r requirements.txt"
  exit 0
fi

if ! "$python_bin" -m pytest --version >/dev/null 2>&1; then
  emit_deny \
    "Commit blocked: pytest is not installed. Install project requirements, then commit again." \
    "The before-commit quality hook could not run pytest. Install dependencies with: $python_bin -m pip install -r requirements.txt"
  exit 0
fi

format_log="$(mktemp)"
lint_log="$(mktemp)"
test_log="$(mktemp)"
trap 'rm -f "$format_log" "$lint_log" "$test_log"' EXIT

if ! "$python_bin" -m ruff format . >"$format_log" 2>&1; then
  emit_deny \
    "Commit blocked: Ruff formatting failed. Fix the formatter error and commit again." \
    "The before-commit quality hook blocked git commit because ruff format failed. Output:\n$(tail -n 40 "$format_log")"
  exit 0
fi

if ! git diff --quiet; then
  emit_deny \
    "Commit blocked: Ruff formatted files. Review and stage the formatting changes, then commit again." \
    "The before-commit quality hook ran ruff format and it changed files. The user needs to stage those changes before retrying git commit."
  exit 0
fi

if ! "$python_bin" -m ruff check . >"$lint_log" 2>&1; then
  emit_deny \
    "Commit blocked: Ruff lint checks failed. Fix the lint issues and commit again." \
    "The before-commit quality hook blocked git commit because ruff check failed. Output:\n$(tail -n 80 "$lint_log")"
  exit 0
fi

if ! "$python_bin" -m pytest >"$test_log" 2>&1; then
  emit_deny \
    "Commit blocked: tests failed. Fix the test failures and commit again." \
    "The before-commit quality hook blocked git commit because python3 -m pytest failed. Output:\n$(tail -n 80 "$test_log")"
  exit 0
fi

echo '{"permission":"allow"}'
