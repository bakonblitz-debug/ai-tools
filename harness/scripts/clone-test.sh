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

rm -rf "$DIR"; mkdir -p "$DIR"
echo "=== cloning $REPO (public, as a stranger would) ==="
git clone --quiet "$REPO" "$DIR/ai-tools" || { echo "CLONE FAILED"; exit 1; }
cd "$DIR/ai-tools" || exit 1
echo "clone: $(git rev-parse --short HEAD), $(git ls-files | wc -l | tr -d ' ') tracked files"

# Run from the clone, with a HOME that has none of his layout, so auto-detection cannot
# silently find the real ~/www and mask the failure.
export HOME="$DIR/fakehome"; mkdir -p "$HOME"

run() {
  local label=$1; shift
  echo
  echo "--- $label"
  local out rc
  out=$( "$@" 2>&1 ); rc=$?
  printf 'exit %d\n' "$rc"
  printf '%s\n' "$out" | head -12
  [ "$(printf '%s\n' "$out" | wc -l)" -gt 12 ] && echo "   … output truncated"
  return 0
}

echo
echo "================ entry points a stranger would actually run ================"
for s in harness/scripts/health-check.sh harness/scripts/session-todo.sh \
         harness/scripts/claude-bootstrap.sh harness/scripts/sync-memory.sh; do
  if [ -f "$s" ]; then run "$s" bash "$s"; else echo; echo "--- $s: NOT IN THE CLONE"; fi
done

echo
echo "================ tracked files citing paths a stranger does not have ================"
git ls-files -z | xargs -0 grep -lE '/mnt/www|~/www|ssh mac' 2>/dev/null | sed 's/^/  /'

echo
echo "================ tracked files citing a GITIGNORED file ================"
# A doc that points at a file not in the clone is a dead end for the reader.
for f in $(git ls-files); do
  for ref in $(grep -oE '[A-Za-z0-9_./-]+\.md' "$f" 2>/dev/null | sort -u); do
    base=$(basename "$ref")
    if git check-ignore -q "$base" 2>/dev/null && ! git ls-files --error-unmatch "$base" >/dev/null 2>&1; then
      echo "  $f -> $base (gitignored, not in the clone)"
    fi
  done
done | sort -u
