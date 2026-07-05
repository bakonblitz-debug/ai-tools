#!/usr/bin/env bash
# SessionStart hook: pull the ai-tools repo, then print the shared workspace
# orientation (SessionStart stdout is injected into the session's context).
# Usage: claude-bootstrap.sh /path/to/ai-tools
set -u
REPO="${1:?usage: claude-bootstrap.sh /path/to/ai-tools}"

T=""
command -v timeout >/dev/null 2>&1 && T="timeout 10"
# credential.interactive=false: never pop an auth prompt from a hook — fail fast instead
$T git -C "$REPO" -c credential.interactive=false pull --rebase --autostash --quiet >/dev/null 2>&1 || true

CTX="$REPO/harness/scripts/bootstrap-context.md"
[ -r "$CTX" ] && cat "$CTX"
exit 0
