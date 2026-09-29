#!/usr/bin/env bash
# context-check-monthly.sh — the scheduled regression test for the context tree.
#
# Generation (context-index.sh, wired into sync-memory.sh) is what actually
# prevents index drift; this is the monthly proof that it still works, plus the
# selftest for the generator itself.
#
# Failure has to be visible without anyone going looking. The jobhunt capture
# died silently for two days in September 2026 because its only signal was an
# email that a quiet day also suppresses. So a red run writes a handoff file,
# which `session-todo.sh` already prints at the top of every session, oldest
# first — reusing the channel he reads rather than adding a second one. No
# network, no mail, no dependency on the claude CLI: deterministic either way.
#
# Usage: context-check-monthly.sh [/path/to/context-repo]
set -u
CTX="${1:-$HOME/www/context}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
WWW="$(cd "$SELF_DIR/../../.." && pwd)"       # harness/scripts -> ai-tools -> ~/www
HANDOFF="$WWW/.plans/handoff-context-check.md"
STAMP=$(date '+%Y-%m-%d %H:%M')

out=$( { "$SELF_DIR/context-index.sh" --selftest; "$SELF_DIR/health-check.sh" context; } 2>&1 )
rc=$?

if [ "$rc" = 0 ] && ! printf '%s' "$out" | grep -q 'FAIL'; then
  # Green: retract the handoff rather than leaving a stale "open" in the digest.
  [ -f "$HANDOFF" ] && rm -f "$HANDOFF"
  echo "$STAMP context check green"
  exit 0
fi

mkdir -p "$WWW/.plans"
{
  echo "# Handoff — context tree checks are failing"
  echo
  echo "## Status"
  echo "open"
  echo
  echo "Written by \`context-check-monthly.sh\` on $STAMP. It runs the generator's selftest"
  echo "and the context checks in \`health-check.sh\`. A red run means either the generator"
  echo "broke or something edited the generated half by hand."
  echo
  echo "First thing to try: \`bash ai-tools/harness/scripts/context-index.sh ~/www/context\`,"
  echo "then re-run \`bash ai-tools/harness/scripts/health-check.sh context\`."
  echo
  echo '```'
  printf '%s\n' "$out" | tail -40
  echo '```'
} > "$HANDOFF"

echo "$STAMP context check FAILED — wrote $HANDOFF (the session digest will surface it)"
exit 1
