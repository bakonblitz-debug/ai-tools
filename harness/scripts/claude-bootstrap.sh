#!/usr/bin/env bash
# SessionStart hook: pull the ai-tools repo, then print the shared workspace
# orientation (SessionStart stdout is injected into the session's context).
# Usage: claude-bootstrap.sh /path/to/ai-tools
set -u
REPO="${1:?usage: claude-bootstrap.sh /path/to/ai-tools}"

T=""
command -v timeout >/dev/null 2>&1 && T="timeout 10"
# credential.interactive=false: never pop an auth prompt from a hook — fail fast instead
if ! $T git -C "$REPO" -c credential.interactive=false pull --rebase --autostash --quiet >/dev/null 2>&1; then
  # a conflicted pull must not leave the repo mid-rebase
  if [ -d "$(git -C "$REPO" rev-parse --git-path rebase-merge)" ] || [ -d "$(git -C "$REPO" rev-parse --git-path rebase-apply)" ]; then
    git -C "$REPO" rebase --abort >/dev/null 2>&1 || true
  fi
fi

# surface divergence loudly: both sides having commits the other lacks means
# concurrent context/memory writes from two machines — needs the interactive flow
if COUNTS=$(git -C "$REPO" rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null); then
  BEHIND=$(printf '%s' "$COUNTS" | awk '{print $1}')
  AHEAD=$(printf '%s' "$COUNTS" | awk '{print $2}')
  if [ "${BEHIND:-0}" -gt 0 ] && [ "${AHEAD:-0}" -gt 0 ] 2>/dev/null; then
    cat <<'EOF'
> **CONTEXT SYNC CONFLICT** — this clone and origin have diverged (both have
> commits the other lacks), almost certainly concurrent context/memory writes
> from two machines. Before relying on the context tree or memory, resolve it
> WITH Isaac using `skills/git-conflict/SKILL.md`, section "Context & memory
> conflicts": run `git pull --rebase` manually to surface the conflicts, then
> follow the idea-reconciliation protocol (merge-with-caveats / challenge /
> philosophy talk). Never resolve context conflicts silently.

EOF
  fi
fi

CTX="$REPO/harness/scripts/bootstrap-context.md"
[ -r "$CTX" ] && cat "$CTX"
exit 0
