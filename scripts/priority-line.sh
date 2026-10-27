#!/usr/bin/env bash
# priority-line.sh — one line naming the priority project's progress and its next item.
#
# His call, 2026-10-14: the improvement findings are THE priority project, and the
# reminder belongs in the TUI. The session digest cannot carry it: it lists oldest
# first and truncates, so a new project lands in "+N more". This line is used twice —
# as the statusLine (always on screen for him) and at the top of the SessionStart
# digest (in context for the model).
#
# Source: the `## Still open` checklist of the newest agentic-improvement-roadmap-*.md
# leaf. One file owns the list; this only reads it.
#
#   priority-line.sh [context-tree]     print the line (nothing if no roadmap exists)
#   priority-line.sh --selftest
set -u
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-root.sh"

line() {
  # No argument: the workspace root from lib-root (Mac ~/www, PC /m, WSL /mnt/www, or
  # WORKSPACE_ROOT). A hard-coded ~/www left the PC's status line empty until 2026-10-27.
  if [ -n "${1:-}" ]; then tree=$1; else detect_root; tree=$WWW/context/context; fi
  f=$(ls "$tree"/*/agentic-improvement-roadmap-*.md 2>/dev/null | sort | tail -1)
  [ -n "$f" ] || return 0
  awk '
    /^## Still open/ {s=1; next}
    /^## /           {s=0}
    s && /^- \[x\]/  {done++}
    s && /^- \[ \]/  {open++; if (!next_item) { next_item=substr($0, 7) } }
    END {
      if (open + done == 0) exit
      if (length(next_item) > 70) next_item = substr(next_item, 1, 67) "..."
      if (open == 0) printf "Priority fixes: all %d done\n", done
      else printf "Priority fixes %d/%d · next: %s\n", done, open + done, next_item
    }' "$f"
}

selftest() {
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  ok() { echo "  ok   $1"; }
  bad() { echo "  FAIL $1"; exit 1; }
  mkdir -p "$t/x"

  [ -z "$(line "$t")" ] || bad "no roadmap should print nothing"
  ok "no roadmap, no line"

  printf '# R\n\n## Notes\n- [ ] not a task\n\n## Still open\n\n- [x] first\n- [ ] second thing\n- [ ] third\n\n## After\n- [ ] ignored\n' \
    > "$t/x/agentic-improvement-roadmap-1-20260101.md"
  out=$(line "$t")
  [ "$out" = "Priority fixes 1/3 · next: second thing" ] || bad "counts or next item wrong: $out"
  ok "counts only the Still open checklist and names the first unchecked item"

  printf '## Still open\n- [x] a\n' > "$t/x/agentic-improvement-roadmap-2-20260102.md"
  out=$(line "$t")
  [ "$out" = "Priority fixes: all 1 done" ] || bad "the newest roadmap must win: $out"
  ok "the newest roadmap wins, and a finished one says so"

  mkdir -p "$t/ws/context/context/y"
  printf '## Still open
- [ ] from the detected root
' > "$t/ws/context/context/y/agentic-improvement-roadmap-3-20260103.md"
  out=$(WORKSPACE_ROOT="$t/ws" bash "$0")
  [ "$out" = "Priority fixes 0/1 · next: from the detected root" ] || bad "no argument must read the detected workspace root, got: $out"
  ok "no argument reads <workspace>/context/context via lib-root (the PC has no ~/www)"

  echo "selftest passed"
}

case ${1:-} in
  --selftest) selftest ;;
  *) line "${1:-}" ;;
esac
