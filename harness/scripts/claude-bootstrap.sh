#!/usr/bin/env bash
# SessionStart hook: pull the private context repo (if it is a git repo), then
# print its orientation (SessionStart stdout is injected into the session).
# Usage: claude-bootstrap.sh /path/to/context-repo
#
# Git is OPTIONAL. If the context path is not a git repo, memory/context still
# work locally — this just skips the pull. Point it at a private git repo to get
# cross-machine sync (recommended; context/memory accumulate PII, keep it private).
set -u
CTX="${1:?usage: claude-bootstrap.sh /path/to/context-repo}"

if [ -d "$CTX/.git" ]; then
  # Offline (e.g. GitHub account suspended): skip the network pull so SessionStart
  # doesn't stall on an unreachable remote. Local orientation + the divergence
  # check below still run. Remove the marker to re-enable: rm "$CTX/.git/sync-offline"
  if [ ! -f "$CTX/.git/sync-offline" ]; then
    T=""
    command -v timeout >/dev/null 2>&1 && T="timeout 10"
    # credential.interactive=false: never pop an auth prompt from a hook — fail fast instead
    if ! $T git -C "$CTX" -c credential.interactive=false pull --rebase --autostash --quiet >/dev/null 2>&1; then
      # a conflicted pull must not leave the repo mid-rebase
      if [ -d "$(git -C "$CTX" rev-parse --git-path rebase-merge)" ] || [ -d "$(git -C "$CTX" rev-parse --git-path rebase-apply)" ]; then
        git -C "$CTX" rebase --abort >/dev/null 2>&1 || true
      fi
    fi
  fi

  # surface divergence loudly: both sides having commits the other lacks means
  # concurrent context/memory writes from two machines — needs the interactive flow
  if COUNTS=$(git -C "$CTX" rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null); then
    BEHIND=$(printf '%s' "$COUNTS" | awk '{print $1}')
    AHEAD=$(printf '%s' "$COUNTS" | awk '{print $2}')
    if [ "${BEHIND:-0}" -gt 0 ] && [ "${AHEAD:-0}" -gt 0 ] 2>/dev/null; then
      cat <<'EOF'
> **CONTEXT SYNC CONFLICT** — this clone and origin have diverged (both have
> commits the other lacks), almost certainly concurrent context/memory writes
> from two machines. Before relying on the context tree or memory, resolve it
> using `ai-tools/skills/git-conflict/SKILL.md`, section "Context & memory
> conflicts": run `git pull --rebase` manually to surface the conflicts, then
> follow the idea-reconciliation protocol. Never resolve context conflicts silently.

EOF
    fi
  fi
fi

ORIENT="$CTX/ORIENT.md"
[ -r "$ORIENT" ] && cat "$ORIENT"
exit 0
