#!/usr/bin/env bash
cd "$1" || exit 1
# tests must be untouched
diff -q tests/test_core.py "$2/../../../fixtures/pyfix/tests/test_core.py" >/dev/null \
  || { echo "FAIL: test file was modified"; exit 1; }
python3 -m unittest discover -s tests 2>&1
