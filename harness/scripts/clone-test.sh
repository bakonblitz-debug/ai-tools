#!/usr/bin/env bash
# clone-test.sh — what does a stranger get when they clone this repo?
#
# The gate for the "make the harness installable" work (.plans/handoff-harness-installable.md).
# The first draft of that plan GUESSED at the first failure and guessed wrong, so nothing gets
# designed until this list exists. Re-run it after every fix; the acceptance criterion is that
# health-check.sh exits 0 with everything unconfigured SKIPped and nothing FAILed.
#
#   bash clone-test.sh [clone-dir]
#
# Deliberately does NOT create a context repo, an ssh alias, a local AI, or sibling clones.
# That is the point: this simulates someone with none of his infrastructure.
set -u
REPO=${REPO:-https://github.com/bakonblitz-debug/ai-tools.git}
DIR=${1:-/tmp/harness-stranger}

# A doc that points at a file not in the clone is a dead end for the reader. This is
# the guard for exactly the defect fixed by hand on 2026-09-29 (four files citing a
# gitignored hermes note) — it did not catch it, because of the two bugs below.
#
# ${ref##*/}, not basename "$ref": a reference beginning with a dash made BSD basename
# parse it as a flag ("basename: illegal option -- d"), so the loop emitted errors and
# zero findings. An expansion has no flags to misparse, and no subprocess either.
#
# And it returns a status now. It printed its findings into a pipeline that ended in
# `sort -u`, so the script exited 0 whatever it found: a check that cannot fail.
scan_dangling() {
  local f ref base found=0
  for f in $(git ls-files); do
    for ref in $(grep -oE '[A-Za-z0-9_./-]+\.md' "$f" 2>/dev/null | sort -u); do
      base=${ref##*/}
      [ -n "$base" ] || continue
      if git check-ignore -q -- "$base" 2>/dev/null \
         && ! git ls-files --error-unmatch -- "$base" >/dev/null 2>&1; then
        echo "  $f -> $base (gitignored, not in the clone)"
        found=1
      fi
    done
  done
  return "$found"
}

selftest() {
  local tmp rc out st=0
  tmp=$(mktemp -d)
  # clean repo: a tracked doc citing a tracked doc. Must find nothing, exit 0.
  git -C "$tmp" init -q
  printf 'see other.md\n' > "$tmp/a.md"; printf 'hi\n' > "$tmp/other.md"
  git -C "$tmp" add -A >/dev/null; git -C "$tmp" -c user.email=t@t -c user.name=t commit -qm x
  out=$(cd "$tmp" && scan_dangling); rc=$?
  if [ "$rc" -ne 0 ] || [ -n "$out" ]; then
    echo "  FAIL clean repo reported a dangling reference: $out"; st=1
  else
    echo "  ok   a clean repo reports nothing and exits 0"
  fi
  # planted defect: a tracked doc citing a GITIGNORED doc. Must find it, exit non-zero.
  printf 'secret-note.md\n' > "$tmp/.gitignore"
  printf 'read secret-note.md for details\n' > "$tmp/a.md"
  printf 'private\n' > "$tmp/secret-note.md"
  git -C "$tmp" add -A >/dev/null; git -C "$tmp" -c user.email=t@t -c user.name=t commit -qm y
  out=$(cd "$tmp" && scan_dangling); rc=$?
  if [ "$rc" -eq 0 ] || [ -z "$out" ]; then
    echo "  FAIL planted dangling reference not caught (rc=$rc, out='$out')"; st=1
  else
    echo "  ok   a tracked file citing a gitignored file is caught, and fails the run"
  fi
  # the regression that started this: a reference beginning with a dash must not be
  # parsed as a flag. Before the fix this printed "basename: illegal option".
  printf 'see -dash-start.md and ./x/-y.md\n' > "$tmp/a.md"
  git -C "$tmp" add -A >/dev/null; git -C "$tmp" -c user.email=t@t -c user.name=t commit -qm z
  out=$(cd "$tmp" && scan_dangling 2>&1)
  if printf '%s' "$out" | grep -qi 'illegal option\|usage: basename'; then
    echo "  FAIL a dash-leading reference is still parsed as a flag: $out"; st=1
  else
    echo "  ok   a dash-leading reference is data, not a flag"
  fi
  rm -rf "$tmp"
  [ "$st" -eq 0 ] && echo "selftest passed" || echo "selftest FAILED"
  return "$st"
}

[ "${1:-}" = "--selftest" ] && { selftest; exit $?; }

rm -rf "$DIR"; mkdir -p "$DIR"
echo "=== cloning $REPO (public, as a stranger would) ==="
git clone --quiet "$REPO" "$DIR/ai-tools" || { echo "CLONE FAILED"; exit 1; }
cd "$DIR/ai-tools" || exit 1
echo "clone: $(git rev-parse --short HEAD), $(git ls-files | wc -l | tr -d ' ') tracked files"

# Run from the clone, with a HOME that has none of his layout, so auto-detection cannot
# silently find the real ~/www and mask the failure.
export HOME="$DIR/fakehome"; mkdir -p "$HOME"

GATE_FAIL=0

# Every entry point gets run and reported. Only health-check.sh's exit code is a
# verdict — it is the stated acceptance criterion at the top of this file. The others
# are informational: session-todo.sh exiting 2 on a missing workspace is correct
# behaviour for a stranger, not a defect. run() used to `return 0` unconditionally,
# which meant the acceptance criterion was printed and then discarded.
run() {
  local label=$1 gate=$2; shift 2
  echo
  echo "--- $label"
  local out rc
  out=$( "$@" 2>&1 ); rc=$?
  printf 'exit %d\n' "$rc"
  printf '%s\n' "$out" | head -12
  [ "$(printf '%s\n' "$out" | wc -l)" -gt 12 ] && echo "   … output truncated"
  if [ "$gate" = gate ] && [ "$rc" -ne 0 ]; then
    echo "  ^ GATE: this one must exit 0 for a stranger"
    GATE_FAIL=1
  fi
  return 0
}

echo
echo "================ entry points a stranger would actually run ================"
for s in harness/scripts/health-check.sh harness/scripts/session-todo.sh \
         harness/scripts/claude-bootstrap.sh harness/scripts/sync-memory.sh; do
  g=info; [ "$s" = harness/scripts/health-check.sh ] && g=gate
  if [ -f "$s" ]; then run "$s" "$g" bash "$s"; else echo; echo "--- $s: NOT IN THE CLONE"; GATE_FAIL=1; fi
done

echo
echo "================ tracked files citing paths a stranger does not have ================"
git ls-files -z | xargs -0 grep -lE '/mnt/www|~/www|ssh mac' 2>/dev/null | sed 's/^/  /'

echo
echo "================ tracked files citing a GITIGNORED file ================"
scan_dangling
rc=$?
[ "$rc" -eq 0 ] && echo "  none"
[ "$GATE_FAIL" -eq 0 ] || rc=1
exit "$rc"
