#!/usr/bin/env bash
# py.sh <script.py> [args] — run a Python script with whichever Python 3.9+ works on this machine.
# The only shell a skill may use: it picks the interpreter (the PC's python3 is a Store stub that
# exists and fails; the Mac has no py). Everything else goes in the Python script.
for c in python3 python "py -3"; do
  if $c -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    exec $c "$@"
  fi
done
echo "py.sh: no Python 3.9+ found (tried python3, python, py -3)" >&2
exit 127
