#!/usr/bin/env bash
# Name the current Claude Code session, the same way /rename does: append a
# custom-title line to the session transcript. The /resume picker shows it.
# Usage: set-title.sh "Short topic title"
set -euo pipefail

title="${1:-}"
id="${CLAUDE_CODE_SESSION_ID:-}"
[ -n "$title" ] || { echo "usage: set-title.sh \"title\"" >&2; exit 2; }
[ -n "$id" ] || { echo "CLAUDE_CODE_SESSION_ID not set; not inside a Claude Code session" >&2; exit 1; }

# Keep the title JSON-safe: drop quotes, backslashes and control characters, cap the length.
title=$(printf '%s' "$title" | tr -d '"\\' | tr -d '\000-\037' | cut -c1-80)

transcript=$(ls "$HOME"/.claude/projects/*/"$id".jsonl 2>/dev/null | head -1 || true)
[ -n "$transcript" ] || { echo "no transcript found for session $id" >&2; exit 1; }

printf '{"type":"custom-title","customTitle":"%s","sessionId":"%s"}\n' "$title" "$id" >> "$transcript"
echo "session titled: $title"
