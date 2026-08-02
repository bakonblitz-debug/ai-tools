#!/usr/bin/env bash
# Verifies BOTH halves of TDD: the fixed suite is green, AND the new regression
# test actually catches the original bug (re-applied to a scratch copy).
set -u
WORK="$1"; TASK="$2"
cd "$WORK" || exit 1

echo "--- fixed suite must be green ---"
python3 -m unittest discover -s tests 2>&1 || { echo "FAIL: suite not green after fix"; exit 1; }

echo "--- regression test must catch the original bug ---"
SCRATCH=$(mktemp -d)
cp -r "$WORK/." "$SCRATCH/"
cp "$TASK/assets/core_buggy.py" "$SCRATCH/textkit/core.py"
if (cd "$SCRATCH" && python3 -m unittest discover -s tests >/dev/null 2>&1); then
  rm -rf "$SCRATCH"
  echo "FAIL: suite still green with the bug re-applied — regression test missing or toothless"
  exit 1
fi
rm -rf "$SCRATCH"
echo "PASS: regression test catches the bug and the fix is green"
