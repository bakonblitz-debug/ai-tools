#!/usr/bin/env bash
# Commit + push harness context/memory changes so every machine can just pull.
# Usage: sync-memory.sh /path/to/ai-tools
# As a PostToolUse hook it reads the tool-call JSON on stdin and no-ops unless
# the touched file is inside harness/context/ or harness/memory/. With no
# tool_input on stdin (Stop hook, manual run) it always syncs.
set -u
REPO="${1:?usage: sync-memory.sh /path/to/ai-tools}"

if [ ! -t 0 ]; then
  INPUT="$(cat 2>/dev/null || true)"
  if printf '%s' "$INPUT" | grep -q '"tool_input"'; then
    # match harness/context|memory with / or JSON-escaped \\ separators
    printf '%s' "$INPUT" | grep -Eq 'harness[^"]{0,4}(context|memory)' || exit 0
  fi
fi

cd "$REPO" || exit 0
if [ -n "$(git status --porcelain -- harness/context harness/memory)" ]; then
  git add -- harness/context harness/memory
  git commit --quiet -m "context/memory sync from $(hostname)" || true
fi

T=""
command -v timeout >/dev/null 2>&1 && T="timeout 30"
# credential.interactive=false: never pop an auth prompt from a hook — fail fast instead
$T git -c credential.interactive=false pull --rebase --autostash --quiet >/dev/null 2>&1 || true
$T git -c credential.interactive=false push --quiet >/dev/null 2>&1 || true
exit 0
