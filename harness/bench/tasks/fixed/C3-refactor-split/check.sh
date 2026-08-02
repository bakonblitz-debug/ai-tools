#!/usr/bin/env bash
cd "$1" || exit 1
[ -f textkit/text.py ]  || { echo "FAIL: textkit/text.py missing"; exit 1; }
[ -f textkit/stats.py ] || { echo "FAIL: textkit/stats.py missing"; exit 1; }
[ ! -f textkit/core.py ] || { echo "FAIL: textkit/core.py still exists"; exit 1; }
grep -q "def word_frequencies" textkit/stats.py || { echo "FAIL: word_frequencies not in stats.py"; exit 1; }
grep -q "def truncate" textkit/text.py || { echo "FAIL: truncate not in text.py"; exit 1; }
# tests must be untouched
diff -q tests/test_core.py "$2/../../../fixtures/pyfix/tests/test_core.py" >/dev/null \
  || { echo "FAIL: test file was modified"; exit 1; }
python3 -m unittest discover -s tests 2>&1
