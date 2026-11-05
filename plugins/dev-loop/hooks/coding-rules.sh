#!/usr/bin/env bash
# coding-rules.sh — dev-loop SessionStart hook. Prints your coding rules into the session, so they
# load only where this plugin is enabled. Which file:
#   1. $CODING_RULES_FILE, if set and readable (one rules file for every project: set it in the
#      "env" block of ~/.claude/settings.json)
#   2. else <project>/.claude/coding-rules.md
# Neither → prints nothing. Always exit 0: a missing rules file must never break a session.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

find_rules() {
  if [ -n "${CODING_RULES_FILE:-}" ] && [ -r "$CODING_RULES_FILE" ]; then
    printf %s "$CODING_RULES_FILE"; return
  fi
  local p="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/coding-rules.md"
  [ -r "$p" ] && printf %s "$p"
}

selftest() {
  local fail=0 out rc; t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  expect() {  # expect <label> <want-stdout> ; env comes from the caller
    out=$(bash "$HERE/coding-rules.sh" </dev/null 2>&1); rc=$?
    [ "$rc" = 0 ] && [ "$out" = "$2" ] || { echo "FAIL: $1 (rc=$rc, got: $out)"; fail=1; }
  }
  mkdir -p "$t/proj/.claude" "$t/home"
  unset CODING_RULES_FILE
  export CLAUDE_PROJECT_DIR=$t/proj
  expect "no rules anywhere prints nothing" ""
  printf 'project rule\n' > "$t/proj/.claude/coding-rules.md"
  expect "the project's .claude/coding-rules.md is printed" "project rule"
  printf 'global rule\n' > "$t/home/rules.md"
  export CODING_RULES_FILE=$t/home/rules.md
  expect "CODING_RULES_FILE wins over the project file" "global rule"
  export CODING_RULES_FILE=$t/missing.md
  expect "an unreadable CODING_RULES_FILE falls back to the project file" "project rule"
  export CLAUDE_PROJECT_DIR=$t/nowhere
  expect "nothing readable: silent, exit 0" ""
  [ "$fail" = 0 ] && echo "coding-rules selftest OK"
  return $fail
}

case "${1:-}" in
  --selftest) selftest; exit $? ;;
esac
f=$(find_rules); [ -n "$f" ] && cat "$f"
exit 0
