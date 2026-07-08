#!/usr/bin/env bash
# UserPromptSubmit hook: while in plan mode, inject the planning mindset into
# context once per session. On exit 0, UserPromptSubmit stdout is added as
# context Claude can see (verified against code.claude.com/docs/en/hooks).
# Usage: plan-mindset.sh /path/to/context-repo   (reads $CTX/PLANNING-MINDSET.md)
#
# Gated on permission_mode == "plan": there is no plan-mode lifecycle hook, so
# UserPromptSubmit + the permission_mode field is the only signal for it.
# ponytail: greps the two fields out of the stdin JSON instead of requiring jq —
#   fine for flat string fields; switch to jq if the schema ever nests them.
set -u
CTX="${1:?usage: plan-mindset.sh /path/to/context-repo}"
MINDSET="$CTX/PLANNING-MINDSET.md"
[ -f "$MINDSET" ] || exit 0

input="$(cat)"

# Only in plan mode.
printf '%s' "$input" | grep -Eq '"permission_mode"[[:space:]]*:[[:space:]]*"plan"' || exit 0

# Once per session — sentinel keyed on session_id so a multi-turn plan session
# doesn't re-inject ~1.5k words every prompt.
# ponytail: injected content can fall out after a compaction; re-enter plan mode
#   in a fresh session to reload it if a long session drops it.
sid="$(printf '%s' "$input" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
sentinel="${TMPDIR:-/tmp}/claude-plan-mindset-${sid:-unknown}"
[ -f "$sentinel" ] && exit 0
touch "$sentinel" 2>/dev/null || true

cat "$MINDSET"
exit 0
