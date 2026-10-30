#!/usr/bin/env bash
# coding-rules.sh — bacon-dev SessionStart hook. Prints <workspace>/context/memory/index/coding.md
# so the coding rules load only in sessions where this plugin is enabled. Silent, exit 0, if absent.
# Workspace: lib-root.sh when it sits beside the plugin (ai-tools checkout), else walk up from the
# project dir (the plugin may run from the plugin cache, where ../../../scripts does not exist).
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REL=context/memory/index/coding.md

find_rules() {
  local lib="$HERE/../../../scripts/lib-root.sh" w d
  if [ -f "$lib" ]; then
    w=$(. "$lib" && detect_root && printf %s "$WWW") 2>/dev/null
    [ -n "$w" ] && [ -f "$w/$REL" ] && { printf %s "$w/$REL"; return; }
  fi
  d=${CLAUDE_PROJECT_DIR:-$PWD}
  while [ -n "$d" ] && [ "$d" != / ] && [ "$d" != . ]; do
    [ -f "$d/$REL" ] && { printf %s "$d/$REL"; return; }
    d=$(dirname "$d")
  done
}

selftest() {
  local fail=0 out; t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  expect() {  # expect <label> <want-stdout> ; env comes from the caller
    out=$(bash "$HERE/coding-rules.sh" </dev/null 2>&1); rc=$?
    [ "$rc" = 0 ] && [ "$out" = "$2" ] || { echo "FAIL: $1 (rc=$rc, got: $out)"; fail=1; }
  }
  mkdir -p "$t/context/memory/index" "$t/projects/x"
  export WORKSPACE_ROOT=$t CLAUDE_PROJECT_DIR=$t/projects/x
  expect "absent file prints nothing" ""
  printf 'rule one\nrule two\n' > "$t/context/memory/index/coding.md"
  expect "present file is printed" "$(printf 'rule one\nrule two')"
  export WORKSPACE_ROOT=/nonexistent-workspace
  expect "walk-up from the project dir finds it when the workspace is unknown" "$(printf 'rule one\nrule two')"
  export CLAUDE_PROJECT_DIR=/nonexistent-project
  expect "no workspace and no file anywhere: silent, exit 0" ""
  [ "$fail" = 0 ] && echo "coding-rules selftest OK"
  return $fail
}

case "${1:-}" in
  --selftest) selftest; exit $? ;;
esac
f=$(find_rules); [ -n "$f" ] && cat "$f"
exit 0
