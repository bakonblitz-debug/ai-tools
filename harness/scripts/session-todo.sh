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
#   1. HANDOFF.md      QUEUED / BLOCKED item headings. RETIRED 2026-09-04 — the file is now a
#                      tombstone and matches nothing. Kept so a revived queue would still be read.
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

# ponytail: oldest-first means the cap truncates the NEWEST items, so keep it above the real
# count rather than at it. 20 is the plan.s own sanity ceiling — past that the filter is wrong,
# not the workspace, and the "+N more" tail is the signal to go look at why.
MAX=${TODO_MAX:-20}

# --- one line per file with an open section: "<age>\t<path>\t<section> (<n>)" ---
# ponytail: age comes from the <slug>-<epoch>-<date>.md filename, so files predating
# that convention print no age. Parse dates out of prose if that ever matters.
scan_leaves() {
  # career/ is job postings: applications, letters, per-company prep. Their status lives in
  # jobhunt.db, not here — his call 2026-09-04: postings are not todo items. The termination
  # dossier is a legal claim, not a posting, so it stays. JobHunt's own features and fixes
  # live under agentic-apps/ and are unaffected.
  find "$1" -name '*.md' -type f \
       ! \( -path '*/career/*' -a ! -path '*/career/simplyphp-termination/*' \) \
       2>/dev/null | LC_ALL=C sort | xargs awk -v now="$(date +%s)" '
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

  # career/ is job postings and must not reach the digest at all (his call 2026-09-04),
  # but the termination dossier lives under career/ and is a legal claim, not a posting.
  mkdir -p "$t/tree/career/simplyphp-termination"
  printf '# acme\n\n## Open\n\n- owes an answer\n' > "$t/tree/career/acme-dev-1785467066-20260730.md"
  printf '# d\n\n## 3. Open actions\n\n- file claim B\n' \
    > "$t/tree/career/simplyphp-termination/dossier-1785467066-20260730.md"
  c=$(scan_leaves "$t/tree")
  case $c in
    *acme*) echo "FAIL: a job posting reached the digest: $c"; exit 1 ;;
  esac
  case $c in
    *simplyphp-termination/dossier*) ;;
    *) echo "FAIL: the termination dossier must survive the career/ exclusion: $c"; exit 1 ;;
  esac

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

  # --close MOVES exactly one line into COMPLETED.md beside the index and refuses anything else.
  # The move is the whole point: nothing may be lost, and the index must shrink by exactly one line.
  printf -- '- [ ] one\n- [ ] two\n- [ ] three\n' > "$t/idx.md"
  close_line "$t/idx.md" 2 >/dev/null
  [ "$(grep -c . "$t/idx.md")" -eq 2 ] || { echo "FAIL: --close did not remove the line"; exit 1; }
  grep -q 'two' "$t/idx.md" && { echo "FAIL: the closed line is still in the index"; exit 1; }
  grep -q 'two' "$t/COMPLETED.md" || { echo "FAIL: the closed line did not reach COMPLETED.md"; exit 1; }
  grep -q '\[ \]' "$t/COMPLETED.md" && { echo "FAIL: the checkbox should be dropped on archive"; exit 1; }
  [ "$(sed -n 1p "$t/idx.md")" = "- [ ] one" ] || { echo "FAIL: --close touched a neighbour"; exit 1; }
  [ "$(sed -n 2p "$t/idx.md")" = "- [ ] three" ] || { echo "FAIL: --close touched a neighbour"; exit 1; }
  close_line "$t/idx.md" 9 >/dev/null 2>&1 && { echo "FAIL: --close accepted a nonexistent line"; exit 1; }

  # the mount guard: a workspace that is not there must fail LOUDLY. An empty digest
  # and "nothing is open" are indistinguishable to a reader, which is the one failure
  # that makes this tool actively misleading rather than merely unhelpful.
  bash "$0" "$t/no-such-root" >/dev/null 2>&1
  [ $? -eq 2 ] || { echo "FAIL: a missing workspace must exit 2, not look empty"; exit 1; }

  echo "selftest OK"
}

# Closing MOVES the line out of CONTEXT.md into COMPLETED.md beside it, rather than marking it.
# Membership is the state: a marker can drift from reality (this whole tool exists because 76 of
# them did), a file boundary cannot, because moving the line IS the update. It also keeps the index
# a list of live work, which is the thing agents read to orient.
close_line() {
  f=$1; n=$2
  line=$(sed -n "${n}p" "$f" 2>/dev/null)
  case $line in
    *'- ['*']'*) ;;
    *) echo "refused: $f:$n is not an index line" >&2; return 1 ;;
  esac
  done_file=${f%/*}/COMPLETED.md
  [ "$done_file" = "$f" ] && done_file=COMPLETED.md
  [ -e "$done_file" ] || cat > "$done_file" <<HDR
# Completed — archived out of \`${f##*/}\`

Finished records. They are here so the index next door stays a list of live work; nothing is
deleted, and a leaf that is linked from here is exactly as readable as one linked from there.
**Looking for something and not finding it in \`${f##*/}\`? It is in here.**

HDR
  printf '%s\n' "$line" | sed 's/^\([[:space:]]*-[[:space:]]*\)\[[ x]\] /\1/' >> "$done_file"
  sed -i.bak "${n}d" "$f" && rm -f "$f.bak"
  echo "archived $f:$n -> $done_file"
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
detect_root() {   # assigns SYSTEM and WWW; never call it in a subshell
  case "$(uname -s)" in
    Darwin)                 SYSTEM=Mac;      WWW=$HOME/www ;;
    MINGW*|MSYS*|CYGWIN*)   SYSTEM=Windows;  WWW=/m ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        SYSTEM=WSL2;        WWW=/mnt/www
      else
        SYSTEM=Linux;       WWW=$HOME/www
      fi ;;
    *)                      SYSTEM=$(uname -s); WWW=$HOME/www ;;
  esac
}

if [ $# -gt 0 ]; then
  WWW=$1; SYSTEM="explicit argument"
else
  # Called plainly, NOT as $(detect_root): a command substitution runs this in a
  # subshell, so SYSTEM would be set there and lost here. The message below then
  # reads it under `set -u` and the script dies with "SYSTEM: unbound variable" —
  # in the error path, which is the one path a new user always takes.
  detect_root
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
  # 1. HANDOFF.md — QUEUED / BLOCKED item headings only; DONE and the usage doc are noise.
  # Retired 2026-09-04, so this normally yields nothing; .plans/ below replaced it. Its failure
  # mode is worth remembering: three blocks headed DONE hid unfixed defects for 19 days, because
  # this grep reads the heading and the heading described the pass, not its findings.
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

render() {
  echo "## Still open — $total items (session-todo.sh)"
  echo
  printf '%s\n' "$items" | head -n "$1" | awk -F'\t' '{printf "  %-5s %-58s %s\n", $1, $2, $3}'
  [ "$total" -gt "$1" ] && echo "  +$((total - $1)) more — session-todo.sh --reconcile"
  return 0
}
render "$MAX"

# ACTIVE.md is GENERATED, never hand-edited — the tree stays the only store. It is written on every
# run (this hook fires at session start on both machines) so it cannot drift from the tree the way a
# maintained list would. Uncapped, unlike the terminal view: a file is scrolled, not glanced at.
# Its counterpart COMPLETED.md is the opposite and cannot be generated — "done" is not derivable
# from the tree, which is why the 2026-09-04 reconciliation needed a human to walk 78 lines. That
# one is written only by --close, one line at a time.
if [ "$MODE" = digest ] && [ -w "$WWW" ]; then
  { echo "# Active — every open item in the workspace"
    echo
    echo "**Generated by \`ai-tools/harness/scripts/session-todo.sh\` on $(date '+%Y-%m-%d %H:%M') from"
    echo "$SYSTEM. Do not hand-edit — it is overwritten on every session start.** Close something by"
    echo "resolving it in the file named below; finished index lines move to the \`COMPLETED.md\`"
    echo "beside their \`CONTEXT.md\`."
    echo
    echo "$total open items, oldest first."
    echo
    # Every row is a LINK, not a path. The whole point of this file is to drill down without
    # opening an index first, so a row you cannot click is a row that failed at its one job.
    # Link targets differ by source, hence the four rules: the tree is under context/context/,
    # .plans/ prints without its dot, HANDOFF.md carries a :line suffix, TODO/ is already root-relative.
    printf '%s\n' "$items" | awk -F'\t' '
      { age = $1; p = $2; sec = $3
        gsub(/^ +| +$/, "", age); gsub(/^ +| +$/, "", p)
        target = p
        sub(/:[0-9]+$/, "", target)
        if (target ~ /^plans\//)            target = "." target
        else if (target !~ /^(TODO|HANDOFF)/) target = "context/context/" target
        label = p
        printf "- **%s** — [%s](%s)  \n  %s\n", (age == "?" ? "undated" : age), label, target, sec
      }'
    echo
    echo "Age comes from the leaf filename (\`<slug>-<epoch>-<date>.md\`); **undated** means the file"
    echo "predates that convention. The trailing count is how many bullets that open section holds."
  } > "$WWW/ACTIVE.md" 2>/dev/null || true
fi

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
