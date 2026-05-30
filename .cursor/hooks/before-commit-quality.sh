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

if [[ ! -x ".venv/bin/pre-commit" ]]; then
  emit_deny \
    "Commit blocked: development environment is not set up. Run scripts/setup-dev.sh, then commit again." \
    "The before-commit quality hook requires .venv and pre-commit. Run: scripts/setup-dev.sh"
  exit 0
fi

hook_log="$(mktemp)"
trap 'rm -f "$hook_log"' EXIT

if ! .venv/bin/pre-commit run >"$hook_log" 2>&1; then
  emit_deny \
    "Commit blocked: pre-commit checks failed. Fix the issues and commit again." \
    "The before-commit quality hook blocked git commit because pre-commit run failed. Output:\n$(tail -n 80 "$hook_log")"
  exit 0
fi

if ! git diff --quiet; then
  emit_deny \
    "Commit blocked: pre-commit modified files. Review and stage the changes, then commit again." \
    "The before-commit quality hook ran pre-commit and it changed files. The user needs to stage those changes before retrying git commit."
  exit 0
fi

echo '{"permission":"allow"}'
