#!/usr/bin/env bash
# health-check.sh — rerunnable health checks for THE HARNESS.
#
#   health-check.sh              run everything, one line per check
#   health-check.sh -v           show the detail line even when a check passes
#   health-check.sh <substring>  run only checks whose name contains <substring>
#
# Exit 0 if nothing FAILed. SKIP never fails the run — it means "could not test from
# here", and prints the command to run by hand.
#
# SCOPE. This file covers the harness itself: the shared workspace, the machines that
# reach it, and the tooling that runs on all of them. It is deliberately generic —
# nothing here knows about any one agent, model, or GPU. Deployment-specific checks
# live with that deployment: Hermes has its own at
# `projects/local-ai-setup/scripts/hermes-health-check.sh` (private repo — it carries gateway
# IPs and machine paths that do not belong in a public one).
#
# WHY THIS EXISTS. Every problem found on 2026-09-03 was silent rather than loud:
# `ollama ps` reported "100% GPU" for a model running on the CPU, WSL2-HANDOFF said
# "NOT YET FIXED" about something fixed eleven days earlier, and a digest printed an
# empty list because it looked in the wrong directory. None announced itself. These
# checks exist to make that class of drift announce itself in one command.
#
# HOW TO ADD A CHECK. Write a function `check_<name>` that echoes one detail line and
# returns 0 (pass), 1 (fail) or 77 (skip). It is picked up automatically — no registry.
#
# ASSERT INVARIANTS, NOT SNAPSHOTS. "23 open items" is true today and wrong next week;
# "all three machines report the same count" stays true forever. Derive the expected
# value at run time and compare, never hardcode it. A check that needs editing every
# time the workspace changes gets deleted instead of fixed.
set -u

# detect_root() (workspace root per OS, plus the .env override) lives
# in lib-root.sh so this file and session-todo.sh share one definition.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-root.sh"
detect_root
# Configuration. Two knobs, and for each one it matters whether the user ASKED for a
# value or just got the default: "you pointed me somewhere that is not there" is a
# failure, "you never mentioned a workspace" is simply an unconfigured optional piece.
# Conflating those is what made a fresh clone report three FAILs it could do nothing
# about. Workspace root: --root PATH or WORKSPACE_ROOT (.env). Remote: REMOTE_HOST
# (was hardcoded `mac`).
WWW_EXPLICIT=0
[ "$SYSTEM" = "explicit (WORKSPACE_ROOT)" ] && WWW_EXPLICIT=1
REMOTE_EXPLICIT=${REMOTE_HOST:+1}; REMOTE_EXPLICIT=${REMOTE_EXPLICIT:-0}
REMOTE_HOST=${REMOTE_HOST:-mac}

# Resolve siblings relative to THIS file, not to the detected workspace. These scripts
# ship together, so a clone can test itself; keying off $WWW made a fresh clone report
# "session-todo.sh missing" while it sat in the same directory.
SCRIPTS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Capture first and filter after: piping into `grep -v` would make the FUNCTION return
# grep's status, and grep exits 1 when it filters everything away — exactly what a
# silent `test -d` produces, turning every passing boolean check into a failure.
wsl_() {
  local out rc
  out=$(MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash -lc "$*" 2>&1); rc=$?
  printf '%s\n' "$out" | tr -d '\r' | grep -v 'Failed to translate'
  return $rc
}
have() { command -v "$1" >/dev/null 2>&1; }

# ==================================================================================
# Checks. Each echoes ONE detail line and returns 0 pass / 1 fail / 77 skip.
# ==================================================================================

check_workspace_mounted() {
  if [ ! -d "$WWW/context/context" ]; then
    # Explicitly pointed somewhere that is not there = broken. Auto-detected default
    # that does not exist = simply not configured, which is the normal state for a
    # new install and must not fail the run.
    [ "$WWW_EXPLICIT" = 1 ] && { echo "no tree at $WWW/context/context"; return 1; }
    echo "no context tree (optional) — point at one with --root PATH"; return 77
  fi
  echo "$SYSTEM → $WWW"
}

check_remote_reachable() {
  have ssh || { echo "no ssh client"; return 77; }
  [ "$SYSTEM" = Mac ] && { echo "running on the remote itself"; return 0; }
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" true 2>/dev/null     && { echo "ssh $REMOTE_HOST ok"; return 0; }
  # Unreachable is only a failure if a remote was actually requested. A single-machine
  # setup has none, and must not be told its git is broken.
  [ "$REMOTE_EXPLICIT" = 1 ]     && { echo "ssh $REMOTE_HOST failed — git for the share runs there, so commits are blocked"; return 1; }
  echo "no remote configured (optional) — set REMOTE_HOST to enable"; return 77
}

# The repo is public and doubles as a portfolio, so a personal identifier reaching a
# tracked file is a leak, not untidiness. The 2026-09-29 tool/notebook split swept 27
# files by hand and MISSED one, because the sweep pattern matched paths and emails but
# not a bare first name. A hand sweep that has to be repeated is not a check; this is.
# Allowlist, settled 2026-09-29: LICENSE and the plugin manifests carry author metadata
# on purpose, .env.example documents the keys, and results.jsonl is recorded measurement
# data — rewriting it to look tidy would falsify a result.
check_no_personal_identifiers() {
  REPO=$(cd "$SCRIPTS/.." && pwd)
  command -v git >/dev/null 2>&1 || { echo "git not available"; return 77; }
  git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo"; return 77; }
  allow='^(LICENSE|\.claude-plugin/marketplace\.json|plugins/bacon/\.claude-plugin/plugin\.json|\.env\.example)$'
  hits=$(git -C "$REPO" ls-files \
    | grep -vE "$allow" \
    | while read -r f; do
        # Every alternative is bracketed ([I]saac, [b]acon@...) so the pattern does not
        # match the file it is written in. Without that this check flags itself, forever.
        grep -lE '[b]akonblitzgithub|[i]saacbacon1|[b]acon@proton|[I]saac' "$REPO/$f" 2>/dev/null
      done)
  [ -z "$hits" ] || { echo "personal identifier in: $(echo "$hits" | sed "s|$REPO/||" | tr '\n' ' ')"; return 1; }
  echo "no personal identifiers outside the allowlist"
}

# The two harness maps are hand-written, so they drift unless something fails when they do.
# Every tracked file must be named in BOTH: the .md (GitHub) and the .html (interactive).
# Matches on the path, so a file mentioned only by its base name does not count.
check_harness_map_covers_files() {
  REPO=$(cd "$SCRIPTS/.." && pwd)
  command -v git >/dev/null 2>&1 || { echo "git not available"; return 77; }
  git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo"; return 77; }
  missing="" n=0
  for map in docs/harness-map.md docs/harness-map.html; do
    [ -f "$REPO/$map" ] || { missing="$missing $map(absent)"; continue; }
    for f in $(git -C "$REPO" ls-files | grep -vE '^(LICENSE|\.gitignore|docs/harness-map\.(md|html))$'); do
      n=$((n+1))
      grep -qF "$f" "$REPO/$map" || missing="$missing ${map##*.}:$f"
    done
  done
  [ -z "$missing" ] || { echo "not on the map:$(echo "$missing" | cut -c1-200)"; return 1; }
  [ "$n" -gt 0 ] || { echo "scanned no files"; return 1; }
  echo "$((n / 2)) files on both maps"
}

# Every script that dispatches on --selftest gets run, found by grep, never a hand-kept
# list: on 2026-10-28 this file ran 2 of 11. A mention in a comment does not count
# (context-check-monthly.sh mentions it and is a real job that writes files).
check_script_selftests() {
  n=0; bad=""; skip=""
  for f in $(grep -l -E -- '--selftest\)|"--selftest"' "$SCRIPTS"/*.sh "$SCRIPTS"/*.py 2>/dev/null | LC_ALL=C sort); do
    n=$((n + 1))
    case $f in *.py) run=python3 ;; *) run=bash ;; esac
    command -v "$run" >/dev/null 2>&1 || { skip="$skip ${f##*/}"; continue; }
    # By bare name from its own folder, the way he runs one by hand: a script that
    # re-runs itself through a raw $0 fails here (3 did, 2026-10-28).
    # perl alarm because macOS has no timeout(1); SIGALRM exits 142.
    (cd "$SCRIPTS" && perl -e 'alarm shift; exec @ARGV or exit 127' "${SELFTEST_LIMIT:-60}" "$run" "${f##*/}" --selftest </dev/null >/dev/null 2>&1)
    case $? in 0) ;; 142) bad="$bad ${f##*/} (timed out)" ;; *) bad="$bad ${f##*/}" ;; esac
  done
  [ "$n" -gt 0 ] || { echo "found no script with a --selftest"; return 1; }
  [ -z "$bad" ] || { echo "selftest failed:$bad"; return 1; }
  echo "$n scripts${skip:+, no interpreter so skipped$skip}"
}

# The derived-value check. The count changes as work is done, so asserting a number
# would rot within days. What must hold is that every machine sees the SAME tree.
# A disagreement means a stale mount, an unsynced clone, or a machine-local file
# leaking into a shared digest — all real, all otherwise silent.
check_digest_agreement() {
  local here there n
  # Nothing to cross-check without a tree, and "no count" would otherwise read as a
  # disagreement between machines rather than as an absent optional piece.
  [ -d "$WWW/context/context" ] || { echo "no workspace to compare"; return 77; }
  here=$(bash "$SCRIPTS/session-todo.sh" "$WWW" 2>/dev/null | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
  [ -n "$here" ] || { echo "digest produced no count on $SYSTEM"; return 1; }
  n="$SYSTEM=$here"

  if [ "$SYSTEM" = Windows ] && have wsl.exe; then
    there=$(wsl_ "bash /mnt/www/ai-tools/scripts/session-todo.sh" | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
    [ -n "$there" ] && n="$n WSL2=$there"
  fi
  if [ "$SYSTEM" != Mac ] && ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" true 2>/dev/null; then
    there=$(ssh "$REMOTE_HOST" 'bash ~/www/ai-tools/scripts/session-todo.sh' 2>/dev/null | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
    [ -n "$there" ] && n="$n Mac=$there"
  fi

  for v in $n; do
    case ${v#*=} in
      "$here") ;;
      *) echo "MISMATCH: $n — machines disagree about the same tree"; return 1 ;;
    esac
  done
  case $n in
    *" "*) echo "$n — agree" ;;
    *)     echo "$n (only this machine reachable)"; return 77 ;;
  esac
}

# The context tree and memory are the record everything else points at. Git for the
# share runs on the Mac; unpushed work is invisible to the other machine, which is
# how a fix gets applied and then re-investigated weeks later.
check_context_synced() {
  have ssh || { echo "no ssh client"; return 77; }
  local dirty ahead
  dirty=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" 'cd ~/www/context && git status --porcelain | wc -l' 2>/dev/null | tr -d ' ')
  [ -n "$dirty" ] || { echo "could not reach the context repo on the Mac"; return 77; }
  ahead=$(ssh "$REMOTE_HOST" 'cd ~/www/context && git rev-list --count @{u}..HEAD 2>/dev/null' 2>/dev/null | tr -d ' ')
  [ "$dirty" = 0 ] || { echo "$dirty uncommitted file(s) — the sync hook should have caught these"; return 1; }
  [ "${ahead:-0}" = 0 ] || { echo "$ahead commit(s) unpushed — the other machine cannot see them"; return 1; }
  echo "clean and pushed"
}

# ==================================================================================
# Context-tree checks. These assert the RULES the tree is kept to (2026-09-04), not
# its contents: an index is a map, every pointer resolves, nothing is unreachable,
# state is membership, and ACTIVE.md is derived. Each rule was broken at least once
# before it was a rule, which is why each has a check.
#
# Every one of these must FAIL LOUDLY when it scans nothing. A lint that walks an
# empty directory and reports success is worse than no lint — it manufactures
# confidence, which is the exact failure this file exists to prevent.
# ==================================================================================

# ponytail: 1500 B allows an H1 plus section headers; the pre-split indexes ran
# 5-11 KB each, so anything in that class trips this. Raise it only with a reason.
CONTEXT_MAX_PROSE=${CONTEXT_MAX_PROSE:-1500}

ctx_tree() { [ -d "$WWW/context/context" ] && echo "$WWW/context/context"; }

check_context_indexes_are_pointers() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  # ponytail: ONE awk over every index, not wc|tr per file. On Windows a fork costs
  # ~150ms, so the spawn count dominates, not the bytes read.
  read -r n worst worstf <<EOF
$(find "$t" -name CONTEXT.md | xargs awk '
    FNR == 1 { file = FILENAME; bytes[file] = 0 }
    FNR > 1 && $0 !~ /^[[:space:]]*-[[:space:]]*\[/ && NF { bytes[file] += length($0) + 1 }
    END { n = 0; worst = 0; worstf = "-"
          for (f in bytes) { n++; if (bytes[f] > worst) { worst = bytes[f]; worstf = f } }
          print n, worst, worstf }')
EOF
  worstf=${worstf#"$t"/}
  [ "$n" -gt 0 ] || { echo "scanned 0 index files — the tree is not where it should be"; return 1; }
  [ "$worst" -le "$CONTEXT_MAX_PROSE" ] ||
    { echo "$worstf carries ${worst}B of prose (cap $CONTEXT_MAX_PROSE) — move it to a leaf"; return 1; }
  echo "$n indexes, worst ${worst}B prose (cap $CONTEXT_MAX_PROSE)"
}

check_context_pointers_resolve() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  links=0; broken=""
  for f in $(find "$t" \( -name CONTEXT.md -o -name COMPLETED.md \)); do
    d=${f%/*}
    for tgt in $(grep -o '](\([^)]*\.md\))' "$f" 2>/dev/null | sed 's/^](//; s/)$//'); do
      links=$((links+1))
      [ -e "$d/$tgt" ] || broken="$broken ${f#"$t"/}->$tgt"
    done
  done
  [ "$links" -gt 0 ] || { echo "found 0 pointers — an index tree with no links is broken, not clean"; return 1; }
  [ -z "$broken" ] || { echo "dead pointer(s):$(echo "$broken" | cut -c1-90)"; return 1; }
  echo "$links pointers, all resolve"
}

check_context_no_orphans() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  seen=0; orphans=""
  # ponytail: read each index ONCE and match in memory. Grepping per leaf was 232 round
  # trips over SMB — 47s from the PC against 1s on the Mac's local disk. Same result.
  for d in $(find "$t" -name CONTEXT.md | sed 's|/[^/]*$||'); do
    idx=$(cat "$d/CONTEXT.md" "$d/COMPLETED.md" 2>/dev/null)
    for f in "$d"/*.md; do
      [ -e "$f" ] || continue
      b=${f##*/}
      case $b in CONTEXT.md|COMPLETED.md) continue ;; esac
      seen=$((seen+1))
      case $idx in *"$b"*) ;; *) orphans="$orphans ${b}" ;; esac
    done
  done
  [ "$seen" -gt 0 ] || { echo "found 0 leaves — nothing was scanned"; return 1; }
  [ -z "$orphans" ] || { echo "unreachable leaf/leaves:$(echo "$orphans" | cut -c1-90)"; return 1; }
  echo "$seen leaves, all reachable from an index"
}

check_context_state_is_membership() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  hits=$(grep -rl '^[[:space:]]*-[[:space:]]*\[[ x]\]' --include=CONTEXT.md "$t" 2>/dev/null | wc -l | tr -d ' ')
  [ "$hits" = 0 ] ||
    { echo "$hits index file(s) reintroduced checkboxes — closing MOVES the line to COMPLETED.md"; return 1; }
  done_files=$(find "$t" -name COMPLETED.md | wc -l | tr -d ' ')
  echo "no checkboxes; $done_files COMPLETED.md archive(s)"
}

check_context_active_is_derived() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  [ -r "$WWW/ACTIVE.md" ] || { echo "ACTIVE.md missing — it is written on every digest run"; return 1; }
  # Read the STORED count before regenerating, or this compares the file to itself
  # and can never fail. session-todo.sh rewrites ACTIVE.md as a side effect.
  was=$(sed -n 's/^\([0-9][0-9]*\) open items.*/\1/p' "$WWW/ACTIVE.md" | head -1)
  now=$(bash "$SCRIPTS/session-todo.sh" 2>/dev/null | sed -n 's/^## Still open — \([0-9][0-9]*\) items.*/\1/p' | head -1)
  [ -n "$now" ] || { echo "the digest produced no count — cannot verify"; return 77; }
  [ "${was:-none}" = "$now" ] ||
    { echo "ACTIVE.md said ${was:-nothing}, tree says $now — it had drifted (now regenerated)"; return 1; }
  echo "ACTIVE.md agrees with the tree ($now items)"
}

# CLAUDE.md said `superpowers` was disabled while settings had it enabled for weeks
# (fixed by hand 2026-10-14). The prose could not be checked; this marker line can:
#   `plugins: id@market=on|off ...`
# Effective state = enabledPlugins merged per key over the user file, then the workspace
# project and local files (later wins). A plugin that is `off` may be absent; `on` may not.
# A CLAUDE.md with no marker FAILs, never SKIPs: rewording the line must break loudly.
# The interpreter is probed by running it, because the PC's python3 is a Store stub that
# exists and fails. Paths go in as argv, not into the -c source: Git Bash converts POSIX
# paths only for argv handed to a native Windows exe.
check_plugins_match_claude_md() {
  local py=""
  for c in python3 python py; do
    have "$c" && "$c" -c 'import json' >/dev/null 2>&1 && { py=$c; break; }
  done
  [ -n "$py" ] || { echo "no working python3/python/py to read settings.json"; return 77; }
  "$py" -c '
import json, os, re, sys
md, *layers = sys.argv[1:]
if not os.path.isfile(md): print("no CLAUDE.md at " + md); sys.exit(77)
pairs = []
for line in open(md, encoding="utf-8"):
    if "`plugins:" in line:
        body = line.split("`plugins:", 1)[1].split("`", 1)[0]
        pairs = [m.groups() for t in body.split() if (m := re.fullmatch(r"([^=\s]+)=(on|off)", t))]
        break
if not pairs: print("no valid `plugins: id=on|off` marker in " + md); sys.exit(1)
eff, src, seen = {}, {}, False
for p in layers:
    if not os.path.isfile(p): continue
    seen = True
    try: d = json.load(open(p, encoding="utf-8")).get("enabledPlugins", {})
    except Exception as e: print("unreadable " + p + ": " + str(e)); sys.exit(1)
    for k, v in d.items(): eff[k] = v; src[k] = p
if not seen: print("no settings.json in any layer"); sys.exit(77)
bad = ["%s declared %s, settings say %s%s" % (i, w, eff.get(i, "absent"), " (" + src[i] + ")" if i in src else "")
       for i, w in pairs if (eff.get(i) is True) != (w == "on")]
if bad: print("; ".join(bad)); sys.exit(1)
print("%d declaration(s) in %s agree with settings" % (len(pairs), md))
' "$WWW/CLAUDE.md" "$HOME/.claude/settings.json" "$WWW/.claude/settings.json" "$WWW/.claude/settings.local.json"
}

# ==================================================================================
# Selftest — proves the context checks FAIL on a broken tree.
#
# A lint is only worth its runtime if it can fail. These build deliberately broken
# fixture trees and assert each check rejects them, then a clean one and assert each
# accepts it. The empty-tree case is the important one: the original digest printed an
# empty list because it looked in the wrong directory, and "nothing is wrong" is
# indistinguishable from "nothing was examined" unless something asserts otherwise.
# ==================================================================================
ctx_expect() {  # ctx_expect <want-rc> <fn>
  want=$1; fn=$2; out=$("$fn" 2>&1); rc=$?
  [ "$rc" = "$want" ] && return 0
  printf '  FAIL: %s returned %s, wanted %s — %s\n' "$fn" "$rc" "$want" "$out"; ST_FAIL=1
}

ctx_selftest() {
  ST_FAIL=0
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  tree=$t/context/context; mkdir -p "$tree/sub"

  # --- 1. an empty tree must FAIL, never pass quietly -----------------------------
  WWW=$t
  ctx_expect 1 check_context_indexes_are_pointers
  ctx_expect 1 check_context_pointers_resolve
  ctx_expect 1 check_context_no_orphans

  # --- 2. each rule broken exactly once -------------------------------------------
  # prose where pointers belong
  { echo '# Index'; awk 'BEGIN{while(i++<40) print "prose line that belongs in a leaf, not an index."}'; } > "$tree/CONTEXT.md"
  printf -- '- [real.md](real.md) — fine\n' >> "$tree/CONTEXT.md"
  printf '# real\n' > "$tree/real.md"
  ctx_expect 1 check_context_indexes_are_pointers

  # dead pointer
  { echo '# Index'; echo '- [gone.md](gone.md) — points at nothing'; echo '- [real.md](real.md) — fine'; } > "$tree/CONTEXT.md"
  ctx_expect 1 check_context_pointers_resolve

  # unreachable leaf
  printf '# stray\n' > "$tree/stray.md"
  { echo '# Index'; echo '- [real.md](real.md) — fine'; } > "$tree/CONTEXT.md"
  ctx_expect 1 check_context_no_orphans
  rm -f "$tree/stray.md"

  # a checkbox creeping back in
  { echo '# Index'; echo '- [ ] [real.md](real.md) — state must be membership, not a marker'; } > "$tree/CONTEXT.md"
  ctx_expect 1 check_context_state_is_membership

  # ACTIVE.md that disagrees with the tree
  { echo '# Index'; echo '- [real.md](real.md) — fine'; } > "$tree/CONTEXT.md"
  printf '# Active\n\n999 open items, oldest first.\n' > "$t/ACTIVE.md"
  ctx_expect 1 check_context_active_is_derived

  # --- 3. the same checks must PASS on a clean tree --------------------------------
  # (guards the opposite failure: a check so strict it can never be satisfied)
  ctx_expect 0 check_context_indexes_are_pointers
  ctx_expect 0 check_context_pointers_resolve
  ctx_expect 0 check_context_no_orphans
  ctx_expect 0 check_context_state_is_membership

  # --- 4. a leaf may only grow; the CLAUDE.md mirror (workspace/CLAUDE-entrypoint.md)
  # must track CLAUDE.md byte for byte, so it is not a leaf and may shrink ------------
  if ctx_mac_only && command -v git >/dev/null 2>&1; then
    g=${tree%/context}; mkdir -p "$tree/workspace"
    printf 'a
b
' > "$tree/sub/leaf-1-20260101.md"; printf 'a
b
' > "$tree/workspace/CLAUDE-entrypoint.md"
    git -C "$g" init -q && git -C "$g" add -A && git -C "$g" -c user.email=t@t -c user.name=t commit -qm base
    printf 'a
' > "$tree/workspace/CLAUDE-entrypoint.md"
    ctx_expect 0 check_context_leaves_only_grow
    printf 'a
' > "$tree/sub/leaf-1-20260101.md"
    ctx_expect 1 check_context_leaves_only_grow
  fi

  # --- 5. script selftests: a mention is not a selftest, and none found must FAIL ---
  SCRIPTS=$t/scripts; mkdir -p "$SCRIPTS"
  printf '# runs context-index.sh --selftest; echo real job\n' > "$SCRIPTS/mentions.sh"
  ctx_expect 1 check_script_selftests
  printf 'case $1 in --selftest) exit 1 ;; esac\n' > "$SCRIPTS/red.sh"
  ctx_expect 1 check_script_selftests
  rm "$SCRIPTS/red.sh"
  printf 'case $1 in --selftest) exit 0 ;; esac\n' > "$SCRIPTS/green.sh"
  printf 'import sys\nsys.exit(0 if "--selftest" in sys.argv else 2)\n' > "$SCRIPTS/green.py"
  ctx_expect 0 check_script_selftests
  printf 'case $1 in --selftest) sleep 30 ;; esac\n' > "$SCRIPTS/hang.sh"
  out=$(SELFTEST_LIMIT=1 check_script_selftests)
  case $out in *"hang.sh (timed out)"*) ;; *) echo "  FAIL: a hung selftest gave: $out"; ST_FAIL=1 ;; esac
  rm "$SCRIPTS/hang.sh"
  # a machine with no python3: .py selftests are skipped, not failed
  mkdir "$t/bin"; for c in bash perl grep sort; do ln -s "$(command -v $c)" "$t/bin/$c"; done
  out=$(PATH=$t/bin check_script_selftests); rc=$?
  case "$rc $out" in "0 "*"skipped green.py"*) ;; *) echo "  FAIL: no python3 gave $rc: $out"; ST_FAIL=1 ;; esac

  # --- 6. plugin declarations vs settings (HOME/WWW set per subshell, so the PATH case
  # above and the real machine never leak in) ------------------------------------------
  p6mk() { rm -rf "$t/h" "$t/w"; mkdir -p "$t/h/.claude" "$t/w/.claude"
    printf -- '- Plugin state, checked by `health-check.sh`: `plugins: %s`\n' "$1" > "$t/w/CLAUDE.md"; }
  p6() { ( HOME=$t/h; WWW=$t/w; ctx_expect "$1" check_plugins_match_claude_md; [ "$ST_FAIL" = 0 ] ) || ST_FAIL=1; }
  p6mk 'a@m=off'; echo '{"enabledPlugins":{"a@m":true}}' > "$t/h/.claude/settings.json"
  p6 1                                   # declared off, user says true
  echo '{"enabledPlugins":{"a@m":false}}' > "$t/h/.claude/settings.json"
  echo '{"enabledPlugins":{"a@m":true}}' > "$t/w/.claude/settings.local.json"
  p6 1                                   # a later layer overrides the user's false
  p6mk 'a@m=on'; echo '{"enabledPlugins":{}}' > "$t/h/.claude/settings.json"
  p6 1                                   # declared on, absent
  p6mk 'a@m=off'; echo '{"enabledPlugins":{}}' > "$t/h/.claude/settings.json"
  p6 0                                   # declared off, absent = not enabled
  echo '{not json' > "$t/h/.claude/settings.json"
  p6 1                                   # invalid JSON in a present layer
  echo '{"enabledPlugins":{}}' > "$t/h/.claude/settings.json"; echo '- no marker here' > "$t/w/CLAUDE.md"
  p6 1                                   # CLAUDE.md without the marker
  p6mk 'a@m=off b@m=on'; echo '{"enabledPlugins":{"a@m":false,"b@m":true}}' > "$t/h/.claude/settings.json"
  p6 0                                   # all agree
  rm -f "$t/h/.claude/settings.json"
  p6 77                                  # no settings file in any layer

  [ "$ST_FAIL" = 0 ] && { echo "context selftest OK — every check fails on a broken tree and passes on a clean one"; return 0; }
  echo "context selftest FAILED"; return 1
}

# ==================================================================================
# Generated-half checks (2026-09-29). context-index.sh owns the generated index
# blocks and the per-folder LEDGER.md; these assert its output is current and
# well-formed. The point is not to nag: a generated block cannot rot, so these are
# regression tests on the generator, which is why none of them gate a session.
# ==================================================================================

ctx_index_script() { echo "$WWW/ai-tools/scripts/context-index.sh"; }
ctx_mac_only() { case $(uname -s) in Darwin) return 0 ;; *) return 1 ;; esac; }

check_context_generated_blocks_current() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  ctx_mac_only || { echo "generation is Mac-only (git and local disk live there)"; return 77; }
  sc=$(ctx_index_script); [ -x "$sc" ] || { echo "context-index.sh missing or not executable"; return 1; }
  # A sync is mid-flight: the tree is being rewritten right now, so any answer here
  # is about a half-written state. SKIP is the honest verdict; a FAIL would flap.
  [ -d "${t%/context}/.git/context-index.lock" ] &&
    { echo "generation in progress (sync holds the lock)"; return 77; }
  out=$("$sc" "${t%/context}" --check 2>&1) || { echo "$(echo "$out" | tr '\n' ' ' | cut -c1-90)"; return 1; }
  echo "$out"
}

check_context_ledger_grammar() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  # ponytail: one awk over every ledger, not a grep per line.
  read -r files lines bad badline <<EOF
$(find "$t" -name LEDGER.md | LC_ALL=C sort | xargs awk '
    FNR == 1 { f++ }
    NF == 0 || /^# generated-at: [0-9a-f]+$/ { next }
    { n++
      if ($0 !~ /^[0-9]{4}-[0-9]{2}-[0-9]{2} \| [0-9a-f]{7,40} \| [AMDR][0-9]* \| [^|]+ \| \+([0-9]+|\?) -([0-9]+|\?)$/) {
        b++; if (b == 1) bl = FILENAME ":" FNR
      } }
    END { print f+0, n+0, b+0, (bl == "" ? "-" : bl) }' /dev/null)
EOF
  [ "${files:-0}" -gt 0 ] || { echo "found 0 LEDGER.md — the generated half was never written"; return 1; }
  [ "${lines:-0}" -gt 0 ] || { echo "$files ledger(s) but 0 event lines — nothing was scanned"; return 1; }
  [ "${bad:-0}" = 0 ] || { echo "$bad malformed ledger line(s), first at ${badline#"$t"/}"; return 1; }
  echo "$files ledgers, $lines events, all well-formed"
}

check_context_ledger_hashes() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  ctx_mac_only || { echo "git runs on the Mac only"; return 77; }
  [ -d "${t%/context}/.git" ] || { echo "context tree is not a git repo here"; return 77; }
  # ponytail: ONE batch-check for every distinct sha. Per-sha git calls were the
  # 232-round-trip mistake the orphan check already paid for.
  shas=$(find "$t" -name LEDGER.md -exec awk -F' \\| ' 'NF>=2 {print $2}' {} + | LC_ALL=C sort -u)
  [ -n "$shas" ] || { echo "no ledger hashes to verify — nothing was scanned"; return 1; }
  missing=$(printf '%s\n' $shas | ( cd "${t%/context}" && git cat-file --batch-check 2>/dev/null ) |
    grep -c 'missing$' || true)
  total=$(printf '%s\n' $shas | grep -c .)
  [ "${missing:-0}" = 0 ] || { echo "$missing of $total ledger hash(es) resolve to no object"; return 1; }
  echo "$total distinct commits, all present"
}

check_context_anchors_resolve() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  leaves=0; broken=""
  for f in $(find "$t" -name '*.md' ! -name CONTEXT.md ! -name COMPLETED.md ! -name LEDGER.md); do
    leaves=$((leaves+1))
    for a in $(grep -o 'SUPERSEDED-BY:[[:space:]]*#[A-Za-z0-9._-]*' "$f" 2>/dev/null | sed 's/.*#//'); do
      grep -qF "{#$a}" "$f" || broken="$broken ${f##*/}#$a"
    done
  done
  [ "$leaves" -gt 0 ] || { echo "found 0 leaves — nothing was scanned"; return 1; }
  [ -z "$broken" ] || { echo "dangling supersede(s):$(echo "$broken" | cut -c1-90)"; return 1; }
  echo "$leaves leaves, every SUPERSEDED-BY resolves"
}

check_context_leaves_only_grow() {
  t=$(ctx_tree) || { echo "no context tree (optional)"; return 77; }
  [ -n "$t" ] || { echo "no context tree (optional)"; return 77; }
  ctx_mac_only || { echo "git runs on the Mac only"; return 77; }
  r=${t%/context}; [ -d "$r/.git" ] || { echo "context tree is not a git repo here"; return 77; }
  # A leaf may only grow. A removed line is a rewrite of recorded history, which is
  # allowed only when the same change adds a RETRACTION naming what went.
  # ponytail: uncommitted changes only — that is what a pre-sync gate can see. A
  # history-wide audit is `git log --numstat` on demand, not a per-run check.
  # -M is load-bearing: without it a rename (yearly log rotation, for one) reads as
  # a whole-file deletion and fails a check that is meant to catch rewrites.
  offenders=""
  while IFS=$'\t' read -r add del path; do
    [ -n "${path:-}" ] || continue
    case $path in *.md) ;; *) continue ;; esac
    # CLAUDE-entrypoint.md mirrors CLAUDE.md byte for byte; it changes when CLAUDE.md does.
    case ${path##*/} in CONTEXT.md|COMPLETED.md|LEDGER.md|CLAUDE-entrypoint.md) continue ;; esac
    [ "${del:-0}" = 0 ] && continue
    ( cd "$r" && git diff HEAD -- "$path" | grep -q '^+.*RETRACTION:' ) || offenders="$offenders ${path##*/}(-$del)"
  done <<EOF
$( cd "$r" && git diff HEAD -M --numstat -- context 2>/dev/null )
EOF
  [ -z "$offenders" ] || { echo "leaf line(s) removed with no RETRACTION:$(echo "$offenders" | cut -c1-80)"; return 1; }
  echo "no leaf shrank without a retraction"
}

# ==================================================================================
# Runner
# ==================================================================================
VERBOSE=0; FILTER=""
for a in "$@"; do
  case ${TAKE_ROOT:-} in 1) WWW=$a; WWW_EXPLICIT=1; TAKE_ROOT=0; continue ;; esac
  case $a in
    --selftest)   SELFTEST=1 ;;
    -v|--verbose) VERBOSE=1 ;;
    --root)       TAKE_ROOT=1 ;;
    *)            FILTER=$a ;;
  esac
done

[ "${SELFTEST:-0}" = 1 ] && { ctx_selftest; exit $?; }

P=0; F=0; S=0
for fn in $(declare -F | awk '{print $3}' | grep '^check_' | sort); do
  name=${fn#check_}
  case $name in *"$FILTER"*) ;; *) continue ;; esac
  detail=$("$fn"); rc=$?
  case $rc in
    0)  P=$((P+1)); [ "$VERBOSE" = 1 ] && printf '  \033[32mPASS\033[0m  %-22s %s\n' "$name" "$detail" \
                                       || printf '  \033[32mPASS\033[0m  %s\n' "$name" ;;
    77) S=$((S+1)); printf '  \033[33mSKIP\033[0m  %-22s %s\n' "$name" "$detail" ;;
    *)  F=$((F+1)); printf '  \033[31mFAIL\033[0m  %-22s %s\n' "$name" "$detail" ;;
  esac
done

printf '\n  harness: %d passed, %d failed, %d skipped\n' "$P" "$F" "$S"
[ "$F" -eq 0 ]
