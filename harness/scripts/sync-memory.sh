#!/usr/bin/env bash
# Commit + push context/memory changes so every machine can just pull.
# Usage: sync-memory.sh /path/to/context-repo
#
# As a PostToolUse hook it reads the tool-call JSON on stdin and no-ops unless
# the touched file is inside context/ or memory/. With no tool_input on stdin
# (Stop hook, manual run) it always syncs.
#
# Git is OPTIONAL. If the context path is not a git repo, this no-ops silently —
# memory still works locally. Point it at a private git repo to get sync.
set -u
CTX="${1:?usage: sync-memory.sh /path/to/context-repo}"

# git-optional: nothing to sync if this isn't a git repo
[ -d "$CTX/.git" ] || exit 0

# read stdin only when it's a real pipe/file (hook JSON) — a terminal or an
# open-but-idle stdin (manual/scripted runs) would make cat block forever
if [ ! -t 0 ] && { [ -p /dev/stdin ] || [ -f /dev/stdin ]; }; then
  INPUT="$(cat 2>/dev/null || true)"
  if printf '%s' "$INPUT" | grep -q '"tool_input"'; then
    # match a context/ or memory/ path segment. Both separators must be accepted
    # on BOTH sides: Windows sends backslash paths (M:\context\memory\x.md, which
    # arrives JSON-escaped as \\), and requiring a forward slash after the segment
    # made this filter never match on Windows — so the PostToolUse hook silently
    # no-op'd there while the Stop hook (no tool_input) masked it. Found 2026-07-30.
    printf '%s' "$INPUT" | grep -Eq '(^|/|\\)(context|memory)(/|\\)' || exit 0
  fi
fi

cd "$CTX" || exit 0
# SYNC_HOST_LABEL overrides the commit label. Needed when a machine drives this
# script on another machine over ssh — the Windows PC does, because git cannot
# write objects into a repo on the Mac's SMB share (macOS refuses to rename
# git's read-only 0444 temp objects), so its hooks run this here via `ssh mac`.
# Without the override every such commit would be labelled with the Mac's
# hostname and the tree would lose track of which machine authored what.
HOST_LABEL="${SYNC_HOST_LABEL:-$(hostname)}"
if [ -n "$(git status --porcelain -- memory context)" ]; then
  git add -- memory context
  git commit --quiet -m "context/memory sync from $HOST_LABEL" || true
fi

# Offline (e.g. GitHub account suspended): commit locally, skip network so the
# hook doesn't stall on — or leak an index.lock against — an unreachable remote.
# Commits queue up and go out on the next run after `rm "$CTX/.git/sync-offline"`.
# ponytail: manual marker; auto-detect from a push 403 if toggling it gets old.
[ -f "$CTX/.git/sync-offline" ] && exit 0

T=""
command -v timeout >/dev/null 2>&1 && T="timeout 30"
# credential.interactive=false: never pop an auth prompt from a hook — fail fast instead
if ! $T git -c credential.interactive=false pull --rebase --autostash --quiet >/dev/null 2>&1; then
  # never leave the repo mid-rebase: abort so both sides stay intact — the
  # session-start bootstrap detects the divergence and routes it to the
  # interactive git-conflict flow (harness/skills/git-conflict, context section)
  if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
    git rebase --abort >/dev/null 2>&1 || true
  fi
fi
$T git -c credential.interactive=false push --quiet >/dev/null 2>&1 || true
exit 0
