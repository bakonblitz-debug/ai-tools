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
#   1. <root>/.plans/ then ~/.claude/plans/ handoff-*.md, "## Status" = open (share first),
#      aged from mtime, newest first
#   2. leaf "## Still open" / "## What is left to do" / "## [N.] Open …" sections.
#      "… before a/any call" is excluded: rehearsal notes, not work anyone owes today
#   4. ponytail: comments — cited in --reconcile, harvested by /ponytail-debt, not here
#
# CONTEXT.md "- [ ]" index checkboxes are deliberately NOT a source. They carry a
# retired desktop-sync meaning until the reconciliation pass sets them honestly;
# reading them today yields 76 false items. See .plans/checkbox-reconciliation-proposal.md.
set -u

# ponytail: oldest-first means the cap truncates the NEWEST items, so keep it above the real
# count rather than at it. 20 is the plan.s own sanity ceiling — past that the filter is wrong,
# not the workspace, and the "+N more" tail is the signal to go look at why.
MAX=${TODO_MAX:-20}

# "<epoch>\t<age>". Sort on the epoch (exact); print the age, in minutes under an hour, hours
# under a day, days after.
age_fmt() {
  s=$(( $(date +%s) - $1 ))
  if   [ $s -lt 3600 ];  then printf '%d\t%dm' "$1" $(( s / 60 ))
  elif [ $s -lt 86400 ]; then printf '%d\t%dh' "$1" $(( s / 3600 ))
  else printf '%d\t%dd' "$1" $(( s / 86400 )); fi
}
# `date -r FILE` reads mtime on BSD (Mac) and GNU (WSL).
mtime_age() { age_fmt "$(date -r "$1" +%s)"; }

# Age of lines LO..HI of FILE = when the oldest of them was last written, from git blame
# (~0.05s a file). Outside git, or with no bullets to blame, it falls back to the file's mtime.
lines_age() {
  e=$([ -n "$2" ] && git -C "$(dirname "$1")" blame --line-porcelain -L "$2,$3" -- "$(basename "$1")" 2>/dev/null |
      awk '/^committer-time / { print $2 }' | sort -n | head -1)
  if [ -n "$e" ]; then age_fmt "$e"; else mtime_age "$1"; fi
}

# --- one line per file with an open section: "<age>\t<path>\t<section> (<n>)" ---
# Age is when the section's OLDEST bullet was last written (git blame), so one fresh line cannot
# hide stale ones. ponytail: a bulk rewrite of lines resets their blame; list that commit in a
# .git-blame-ignore-revs and pass --ignore-revs-file if it ever happens.
scan_leaves() {
  # career/ is job postings: applications, letters, per-company prep. Their status lives in
  # jobhunt.db, not here — his call 2026-09-04: postings are not todo items. A career/ folder
  # holding a .digest-keep file (a legal claim, not a posting) stays; the marker lives in the
  # private tree so this script names no folder. JobHunt's own features and fixes live under
  # agentic-apps/ and are unaffected.
  local keep=() k
  while IFS= read -r k; do keep+=(! -path "${k%/.digest-keep}/*"); done \
    < <(find "$1" -path '*/career/*' -name .digest-keep -type f 2>/dev/null)
  find "$1" -name '*.md' -type f \
       ! \( -path '*/career/*' ${keep[@]+"${keep[@]}"} \) \
       2>/dev/null | LC_ALL=C sort | xargs awk '
    function flush() {
      if (file == "" || sec == "") return
      printf "%s\t%s (%d)\t%s\t%s\n", file, sec, cnt, lo, hi
    }
    FNR == 1 { flush(); file = FILENAME; sec = ""; cnt = 0; lo = hi = "" }
    /^## / {
      if (sec != "") { flush(); sec = "" }
      # "… before a/any call" is rehearsal that fires only if someone calls — not
      # work anyone owes today, and 9 of them alone would double the digest.
      # the leading "N." allows "## 3. Open actions" (the termination dossier) through
      if ($0 ~ /^## ([0-9]+\. )?(Still open|Still blocked|What is left to do|Open($|[ ,.—:]))/ &&
          $0 !~ /before (a|any) call/) {
        sec = $0; sub(/^## /, "", sec); cnt = 0; lo = hi = ""
      } else sec = ""
      next
    }
    sec != "" && /^[[:space:]]*([-*]|[0-9]+\.)[[:space:]]/ { cnt++; if (lo == "") lo = FNR; hi = FNR }
    END { flush() }
  ' /dev/null |  # /dev/null keeps awk off stdin if find matched nothing (GNU/BSD xargs differ)
  while IFS="$(printf '\t')" read -r f sec lo hi; do
    printf '%s\t%s\t%s\n' "$(lines_age "$f" "$lo" "$hi")" "$f" "$sec"
  done | LC_ALL=C sort -n | cut -f2-   # oldest bullet first: the most neglected section leads
}

# one line per open handoff: "<age>d\tplans/<name>\t<status line>", newest first.
# Age is the file's mtime: handoffs carry no filename epoch, and greet needs them ordered.
# `date -r FILE` reads mtime on both BSD (Mac) and GNU (WSL) date.
scan_handoffs() {
  seen=" "
  for d in "$@"; do
    for f in "$d"/handoff-*.md; do
      [ -r "$f" ] || continue
      b=${f##*/}
      case $seen in *" $b "*) continue ;; esac
      seen="$seen$b "
      st=$(awk '/^## Status/ { s = 1; next } s && NF { print; exit }' "$f")
      case $st in [Oo]pen*) ;; *) continue ;; esac
      printf '%s\tplans/%s\t%s\n' "$(mtime_age "$f")" "$b" "$st"
    done
  done | LC_ALL=C sort -rn | cut -f2-   # newest first
}

# ponytail: fixed shortlist of root docs + the tree, not a workspace-wide grep. Widen it
# if a stale claim ever hides somewhere else; a recursive scan over SMB costs minutes.
stale_scan() {
  grep -rniE '(NOT YET FIXED|NOT FIXED|STILL BROKEN|STILL NOT WORKING)' \
    "$1"/*.md "$1"/projects/local-ai-setup/*.md "$1"/context/context 2>/dev/null |
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
  # age is the last edit, not the filename epoch: leaves only grow, so an append is progress
  # and a 2026-07-30 note touched 2 days ago is 2 days idle, not 90
  touch -t "$(date -v-2d +%Y%m%d%H%M 2>/dev/null || date -d '2 days ago' +%Y%m%d%H%M)" "$t/tree/sub/thing-1785467066-20260730.md"
  out=$(scan_leaves "$t/tree")
  age=${out%%$'\t'*}
  [ "$age" = 2d ] || { echo "FAIL: leaf age must be time since last edit, got: $age"; exit 1; }

  # in git, a section is as old as its OLDEST bullet: one fresh line must not hide four stale ones
  g="$t/repo"; mkdir -p "$g"; git -C "$g" init -q
  printf '# z\n\n## Still open\n\n- stale one\n- stale two\n\n## Notes\n\n- not open\n' > "$g/z.md"
  git -C "$g" add z.md
  GIT_COMMITTER_DATE='2026-01-01T00:00:00' git -C "$g" -c user.name=t -c user.email=t@t \
    commit -qm old --date=2026-01-01T00:00:00
  printf '# z\n\n## Still open\n\n- stale one\n- stale two\n- fresh\n\n## Notes\n\n- not open\n' > "$g/z.md"
  git -C "$g" -c user.name=t -c user.email=t@t commit -qam new
  b=$(scan_leaves "$g")
  case $b in
    [0-9]*"d	$g/z.md	Still open (3)") [ "${b%%d*}" -gt 100 ] ||
      { echo "FAIL: section age must come from its oldest bullet: $b"; exit 1; } ;;
    *) echo "FAIL: section age must come from its oldest bullet, in days: $b"; exit 1 ;;
  esac

  # career/ is job postings and must not reach the digest at all (his call 2026-09-04),
  # except a folder he marks with .digest-keep (a legal claim, say). The marker lives in the
  # private tree, so this public script names no folder.
  mkdir -p "$t/tree/career/a-claim" "$t/tree/career/b-prep"
  touch "$t/tree/career/a-claim/.digest-keep"
  printf '# acme\n\n## Open\n\n- owes an answer\n' > "$t/tree/career/acme-dev-1785467066-20260730.md"
  printf '# b\n\n## Open\n\n- prep\n' > "$t/tree/career/b-prep/notes-1785467066-20260730.md"
  printf '# d\n\n## 3. Open actions\n\n- file claim B\n' \
    > "$t/tree/career/a-claim/dossier-1785467066-20260730.md"
  c=$(scan_leaves "$t/tree")
  case $c in
    *acme*|*b-prep*) echo "FAIL: a job posting reached the digest: $c"; exit 1 ;;
  esac
  case $c in
    *a-claim/dossier*) ;;
    *) echo "FAIL: a career/ folder marked .digest-keep must reach the digest: $c"; exit 1 ;;
  esac

  # handoffs: aged from mtime (they carry no filename epoch), newest first, status text kept,
  # closed ones dropped, and the share copy wins over a same-named local one.
  mkdir -p "$t/share" "$t/local"
  printf '# a\n\n## Status\n\nopen — waiting on the PC\n' > "$t/share/handoff-old.md"
  printf '# b\n\n## Status\n\nopen\n' > "$t/share/handoff-new.md"
  printf '# c\n\n## Status\n\ndone\n' > "$t/share/handoff-closed.md"
  printf '# d\n\n## Status\n\nopen — LOCAL DUPLICATE\n' > "$t/local/handoff-new.md"
  touch -t 202601010000 "$t/share/handoff-old.md"
  # same day, newer by minutes, but sorts first by name: order must follow the clock, not the name
  printf '# e\n\n## Status\n\nopen\n' > "$t/share/handoff-aaa.md"
  touch -t "$(date -v-10M +%Y%m%d%H%M 2>/dev/null || date -d '10 minutes ago' +%Y%m%d%H%M)" "$t/share/handoff-aaa.md"
  h=$(scan_handoffs "$t/share" "$t/local")
  [ "$(printf '%s\n' "$h" | grep -c .)" -eq 3 ] || { echo "FAIL: expected 3 open handoffs:"; echo "$h"; exit 1; }
  case $(printf '%s\n' "$h" | sed -n 2p) in
    1[01]"m	plans/handoff-aaa.md	open") ;;   # 10 minutes old reads as minutes, not 0d
    *) echo "FAIL: same-day handoffs must sort by mtime and show minutes:"; echo "$h"; exit 1 ;;
  esac
  case $(printf '%s\n' "$h" | head -1) in
    "0m	plans/handoff-new.md	open") ;;
    *) echo "FAIL: newest handoff must come first, aged 0m, share copy winning:"; echo "$h"; exit 1 ;;
  esac
  case $(printf '%s\n' "$h" | tail -1) in
    [0-9]*"d	plans/handoff-old.md	open — waiting on the PC") ;;
    *) echo "FAIL: old handoff must be aged and keep its status text:"; echo "$h"; exit 1 ;;
  esac

  # the real WSL2-HANDOFF §11b shape: an assertion left standing 11 days after the fix.
  # It must NOT reach the digest (it is not a "## Still open" section) but MUST reach
  # --reconcile, and the already-corrected form must not come back as a false positive.
  mkdir -p "$t/projects/local-ai-setup"
  printf '### 11b\n\n**NOT YET FIXED** — hermes can still delete anything on C:.\n' > "$t/projects/local-ai-setup/WSL2-HANDOFF.md"
  printf '### 11c\n\n**FIXED — this section was stale, corrected 2026-09-03.**\n' >> "$t/projects/local-ai-setup/WSL2-HANDOFF.md"
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

# detect_root() (workspace root per OS, plus the .env override) now
# lives in lib-root.sh so health-check.sh and friends share one definition.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-root.sh"

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

# Handoffs first, newest first: they are parked work someone meant to resume, so they outrank
# prose regardless of age. Share first, then $HOME (machine-local, invisible over ssh); dedup
# by basename, share wins.
structured=$(scan_handoffs "$WWW/.plans" "$PLANS")

# 4. leaf open sections, oldest first, aged from the filename
aged=$([ -d "$TREE" ] && scan_leaves "$TREE" | sed "s|\t$TREE/|\t|")   # already oldest edit first

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
    echo "**Generated by \`ai-tools/scripts/session-todo.sh\` on $(date '+%Y-%m-%d %H:%M') from"
    echo "$SYSTEM. Do not hand-edit — it is overwritten on every session start.** Close something by"
    echo "resolving it in the file named below; finished index lines move to the \`COMPLETED.md\`"
    echo "beside their \`CONTEXT.md\`."
    echo
    echo "$total open items: handoffs newest first, then context notes stalest first (age of the oldest open bullet)."
    echo
    # Every row is a LINK, not a path. The whole point of this file is to drill down without
    # opening an index first, so a row you cannot click is a row that failed at its one job.
    # Link targets differ by source: the tree is under context/context/, .plans/ prints without its dot.
    printf '%s\n' "$items" | awk -F'\t' '
      { age = $1; p = $2; sec = $3
        gsub(/^ +| +$/, "", age); gsub(/^ +| +$/, "", p)
        target = (p ~ /^plans\//) ? "." p : "context/context/" p
        label = p
        printf "- **%s** — [%s](%s)  \n  %s\n", age, label, target, sec
      }'
    echo
    echo "Age is time since the file was last changed. The trailing count is how many bullets that open section holds."
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
