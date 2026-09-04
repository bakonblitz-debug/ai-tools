#!/usr/bin/env bash
# session-todo.sh — one-glance digest of what is still open across the workspace.
# Runs on the Mac and in WSL. grep/sed/awk only; the tree is the only store.
#
#   session-todo.sh [WORKSPACE_ROOT]      digest (default: auto-detected per system, or $1)
#   session-todo.sh --reconcile [ROOT]    every candidate with file:line, uncapped
#   session-todo.sh --close FILE LINE     flip one "- [ ]" index line to "- [x]"
#   session-todo.sh --selftest            assert-based self-check, no workspace needed
#
# Sources, in reliability order (see <root>/.plans/handoff-session-start-todo.md):
#   1. HANDOFF.md      QUEUED / BLOCKED item headings — already structured
#   2. leaf "## Still open" / "## What is left to do" / "## [N.] Open …" sections.
#      "… before a/any call" is excluded: rehearsal notes, not work anyone owes today
#   3. TODO/*.md       aggregated to one line per file, never expanded per checkbox
#   4. <root>/.plans/ then ~/.claude/plans/ handoff-*.md, "## Status" = open (share first)
#   5. ponytail: comments — cited in --reconcile, harvested by /ponytail-debt, not here
#
# CONTEXT.md "- [ ]" index checkboxes are deliberately NOT a source. They carry a
# retired desktop-sync meaning until the reconciliation pass sets them honestly;
# reading them today yields 76 false items. See .plans/checkbox-reconciliation-proposal.md.
set -u

MAX=${TODO_MAX:-15}

# --- one line per file with an open section: "<age>\t<path>\t<section> (<n>)" ---
# ponytail: age comes from the <slug>-<epoch>-<date>.md filename, so files predating
# that convention print no age. Parse dates out of prose if that ever matters.
scan_leaves() {
  find "$1" -name '*.md' -type f 2>/dev/null | LC_ALL=C sort | xargs awk -v now="$(date +%s)" '
    function flush(   age) {
      if (file == "" || sec == "") return
      age = (epoch > 0) ? int((now - epoch) / 86400) "d" : "  ?"
      printf "%s\t%s\t%s (%d)\n", age, file, sec, cnt
    }
    FNR == 1 {
      flush(); file = FILENAME; sec = ""; cnt = 0; epoch = 0
      if (match(FILENAME, /-[0-9]{9,11}-[0-9]{8}\.md$/))
        epoch = substr(FILENAME, RSTART + 1, RLENGTH - 13) + 0
    }
    /^## / {
      if (sec != "") { flush(); sec = "" }
      # "… before a/any call" is rehearsal that fires only if someone calls — not
      # work anyone owes today, and 9 of them alone would double the digest.
      # the leading "N." allows "## 3. Open actions" (the termination dossier) through
      if ($0 ~ /^## ([0-9]+\. )?(Still open|Still blocked|What is left to do|Open($|[ ,.—:]))/ &&
          $0 !~ /before (a|any) call/) {
        sec = $0; sub(/^## /, "", sec); cnt = 0
      } else sec = ""
      next
    }
    sec != "" && /^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]/ { cnt++ }
    END { flush() }
  ' /dev/null   # keeps awk off stdin if find matched nothing (GNU/BSD xargs differ)
}

# ponytail: fixed shortlist of root docs + the tree, not a workspace-wide grep. Widen it
# if a stale claim ever hides somewhere else; a recursive scan over SMB costs minutes.
stale_scan() {
  grep -rniE '(NOT YET FIXED|NOT FIXED|STILL BROKEN|STILL NOT WORKING)' \
    "$1"/*.md "$1"/local-ai-setup/*.md "$1"/context/context 2>/dev/null |
    grep -viE 'was stale|corrected [0-9]{4}|since fixed' | cut -c1-160
}

selftest() {
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  mkdir -p "$t/tree/sub"

  # a leaf with a real open section, aged from its filename epoch (1785467066 = 2026-07-30)
  printf '# x\n\n## 3. Open actions\n\n- one\n- two\n' > "$t/tree/sub/thing-1785467066-20260730.md"
  # the WSL2-HANDOFF drift shape: an assertion that reads open but is not a section
  printf '# y\n\n## Notes\n\nStatus: NOT YET FIXED\n' > "$t/tree/sub/drift-1785467067-20260730.md"
  # the trap this tool exists to avoid: 76 legacy checkboxes must contribute nothing
  printf '# i\n\n- [ ] [a](a.md) legacy\n- [ ] [b](b.md) legacy\n' > "$t/tree/CONTEXT.md"

  out=$(scan_leaves "$t/tree")
  n=$(printf '%s\n' "$out" | grep -c . )

  [ "$n" -eq 1 ] || { echo "FAIL: expected 1 open leaf, got $n:"; echo "$out"; exit 1; }
  case $out in
    *"3. Open actions (2)"*) ;;
    *) echo "FAIL: bullet count wrong: $out"; exit 1 ;;
  esac
  case $out in
    *CONTEXT.md*) echo "FAIL: a checkbox line reached the digest: $out"; exit 1 ;;
  esac
  case $out in
    *drift*) echo "FAIL: prose 'NOT YET FIXED' must not become an item: $out"; exit 1 ;;
  esac
  # age is derived, not stat'd: 2026-07-30 is well over 30 days before any plausible run
  age=${out%%$'\t'*}
  [ "${age%d}" -gt 30 ] 2>/dev/null || { echo "FAIL: age not derived from filename: $age"; exit 1; }

  # the real WSL2-HANDOFF §11b shape: an assertion left standing 11 days after the fix.
  # It must NOT reach the digest (it is not a "## Still open" section) but MUST reach
  # --reconcile, and the already-corrected form must not come back as a false positive.
  printf '### 11b\n\n**NOT YET FIXED** — hermes can still delete anything on C:.\n' > "$t/WSL2-HANDOFF.md"
  printf '### 11c\n\n**FIXED — this section was stale, corrected 2026-09-03.**\n' >> "$t/WSL2-HANDOFF.md"
  s=$(stale_scan "$t")
  case $s in
    *"NOT YET FIXED"*) ;;
    *) echo "FAIL: --reconcile missed the seeded stale assertion"; exit 1 ;;
  esac
  [ "$(printf '%s\n' "$s" | grep -c .)" -eq 1 ] ||
    { echo "FAIL: the corrected line came back as a false positive:"; echo "$s"; exit 1; }

  # --close flips exactly one line and refuses anything else
  printf -- '- [ ] one\n- [ ] two\n' > "$t/idx.md"
  close_line "$t/idx.md" 2 >/dev/null
  [ "$(sed -n 2p "$t/idx.md")" = "- [x] two" ] || { echo "FAIL: --close did not check line 2"; exit 1; }
  [ "$(sed -n 1p "$t/idx.md")" = "- [ ] one" ] || { echo "FAIL: --close touched line 1"; exit 1; }
  close_line "$t/idx.md" 2 >/dev/null 2>&1 && { echo "FAIL: --close re-closed a closed line"; exit 1; }

  # the mount guard: a workspace that is not there must fail LOUDLY. An empty digest
  # and "nothing is open" are indistinguishable to a reader, which is the one failure
  # that makes this tool actively misleading rather than merely unhelpful.
  bash "$0" "$t/no-such-root" >/dev/null 2>&1
  [ $? -eq 2 ] || { echo "FAIL: a missing workspace must exit 2, not look empty"; exit 1; }

  echo "selftest OK"
}

close_line() {
  f=$1; n=$2
  case $(sed -n "${n}p" "$f" 2>/dev/null) in
    *'- [ ]'*) ;;
    *) echo "refused: $f:$n is not an unchecked checkbox" >&2; return 1 ;;
  esac
  sed -i.bak "${n}s/- \[ \]/- [x]/" "$f" && rm -f "$f.bak"
  echo "closed $f:$n"
}

case ${1:-} in
  --selftest) selftest; exit $? ;;
  --close) close_line "${2:?file}" "${3:?line}"; exit $? ;;
  --reconcile) MODE=reconcile; shift ;;
  *) MODE=digest ;;
esac

# One tree, three mount points: ~/www on the Mac, /mnt/www in WSL2, M:\ (= /m under
# Git Bash) on the PC. Pick by system, then VERIFY — a digest that prints an empty
# list because it looked in the wrong place is indistinguishable from "nothing is
# open", which is the one failure that makes this tool actively misleading.
#
# WSL reports "Linux" from uname, so it must be tested before plain Linux. The
# /proc/version marker is the reliable tell; $WSL_DISTRO_NAME is unset under some
# service managers and sudo's env_reset.
detect_root() {
  case "$(uname -s)" in
    Darwin)                 SYSTEM=Mac;      echo "$HOME/www" ;;
    MINGW*|MSYS*|CYGWIN*)   SYSTEM=Windows;  echo "/m" ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        SYSTEM=WSL2;        echo "/mnt/www"
      else
        SYSTEM=Linux;       echo "$HOME/www"
      fi ;;
    *)                      SYSTEM=$(uname -s); echo "$HOME/www" ;;
  esac
}

if [ $# -gt 0 ]; then
  WWW=$1; SYSTEM="explicit argument"
else
  WWW=$(detect_root)
fi

if [ ! -d "$WWW/context/context" ]; then
  echo "session-todo: detected $SYSTEM, expected the workspace at '$WWW'" >&2
  echo "session-todo: but '$WWW/context/context' is not there — is the share mounted?" >&2
  echo "session-todo: override with an explicit root, e.g. session-todo.sh /mnt/www" >&2
  exit 2
fi
TREE=$WWW/context/context
PLANS=$HOME/.claude/plans

# Structured signals first — these are already dated and triaged by a machine, so they
# outrank prose regardless of age. They carry no filename epoch, which is why they cannot
# just be sorted in with the rest.
structured=$(
  # 1. HANDOFF.md — QUEUED / BLOCKED item headings only; DONE and the usage doc are noise
  [ -r "$WWW/HANDOFF.md" ] && grep -nE '^\*\*[0-9]+[a-z]*\..*(QUEUED|BLOCKED)' "$WWW/HANDOFF.md" |
    sed 's/[*_`]//g; s/^\([0-9]*\):/  ?\tHANDOFF.md:\1\t/'

  # 2. TODO/*.md — one aggregate line each, never one per checkbox
  for f in "$WWW"/TODO/*.md; do
    [ -r "$f" ] || continue
    o=$(grep -c '^\s*-\s\[ \]' "$f") ; [ "$o" -gt 0 ] || continue
    printf '  ?\tTODO/%s\t%s unchecked, unreconciled\n' "${f##*/}" "$o"
  done

  # 3. this skill's own handoffs. ponytail: $HOME-local, so a hook running over ssh sees
  # the remote machine's plans, not the calling machine's. Sync them if that ever bites.
  # Two locations on purpose. $HOME/.claude/plans is machine-LOCAL, and this hook runs
  # on the Mac over ssh — so a handoff written on the PC is invisible from there, which
  # defeats the point of parking it. <root>/.plans is on the share and both machines see
  # it; prefer that for anything meant to resurface. Dedup by basename, share wins.
  seen=""
  for f in "$WWW"/.plans/handoff-*.md "$PLANS"/handoff-*.md; do
    [ -r "$f" ] || continue
    b=${f##*/}
    printf '%s\n' "$seen" | grep -qx -- "$b" && continue
    seen="$seen
$b"
    grep -A1 '^## Status' "$f" | grep -qi '^open' &&
      printf '  ?\tplans/%s\tStatus: open\n' "$b"
  done
)

# 4. leaf open sections, oldest first, aged from the filename
aged=$([ -d "$TREE" ] && scan_leaves "$TREE" | sed "s|\t$TREE/|\t|" | LC_ALL=C sort -rn)

items=$(printf '%s\n%s\n' "$structured" "$aged" | grep .)
total=$(printf '%s\n' "$items" | grep -c .)
[ "$total" -eq 0 ] && exit 0
[ "$MODE" = reconcile ] && MAX=$total

echo "## Still open — $total items (session-todo.sh)"
echo
printf '%s\n' "$items" | head -n "$MAX" | awk -F'\t' '{printf "  %-5s %-58s %s\n", $1, $2, $3}'
[ "$total" -gt "$MAX" ] && echo "  +$((total - MAX)) more — session-todo.sh --reconcile"

if [ "$MODE" = reconcile ]; then
  # Drift the other way: a hard assertion that something is broken, which nobody
  # revisited. WSL2-HANDOFF §11b claimed "NOT YET FIXED" for 11 days after the fix
  # landed. Reconcile-only — these need a human to rewrite prose, and --close will
  # not touch them; it flips checkboxes and nothing else.
  echo
  echo "Stale-assertion candidates (a claim that something is broken — verify before believing it):"
  stale_scan "$WWW" | sed 's/^/  /' | head -20
  echo
  echo "Deferred code shortcuts live in ponytail: comments — run /ponytail-debt for that ledger."
  echo "(Not scanned here: a recursive grep of the workspace over SMB costs minutes, and this"
  echo " script runs on every session start.)"
  echo "Close one index line: session-todo.sh --close <CONTEXT.md> <line>"
  echo "Proposed reconciliation for all 78 index checkboxes: $WWW/.plans/checkbox-reconciliation-proposal.md"
fi
exit 0
