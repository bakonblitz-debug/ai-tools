#!/usr/bin/env bash
# coding-mode.sh — turn coding mode on for a project folder.
#
#   coding-mode.sh <dir>            write/merge <dir>/.claude/settings.json: the coding plugin set = true
#   coding-mode.sh <dir> --check    exit 1 listing the plugins not enabled there; touches nothing
#   coding-mode.sh --selftest
#
# Merges into an existing settings.json and keeps every other key. The set is the coding mode of
# docs/coding-standards.md: bacon-dev (architect/ouroboros/handoff + the coding-rules hook),
# ponytail, superpowers. User settings keep them off, so only folders that opt in load them.
set -u
CODING_SET="bacon-dev@ai-tools ponytail@ponytail superpowers@claude-plugins-official"

# The interpreter is probed by running it (the PC's python3 is a Store stub that exists and fails).
PY=""
for c in python3 python py; do
  command -v "$c" >/dev/null 2>&1 && "$c" -c 'import json' >/dev/null 2>&1 && { PY=$c; break; }
done

# apply <settings-path> <write|check>   -> prints missing ids; exit 0 ok, 1 missing (check), 2 unreadable
apply() {
  "$PY" -c '
import json, os, sys
path, mode, *ids = sys.argv[1:]
d = {}
if os.path.isfile(path):
    try: d = json.load(open(path, encoding="utf-8"))
    except Exception as e: print("unreadable " + path + ": " + str(e)); sys.exit(2)
    if not isinstance(d, dict): print("not a JSON object: " + path); sys.exit(2)
ep = d.get("enabledPlugins")
ep = ep if isinstance(ep, dict) else {}
missing = [i for i in ids if ep.get(i) is not True]
if mode == "check":
    if missing: print(" ".join(missing)); sys.exit(1)
    sys.exit(0)
for i in ids: ep[i] = True
d["enabledPlugins"] = ep
os.makedirs(os.path.dirname(path), exist_ok=True)
open(path, "w", encoding="utf-8").write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
' "$1" "$2" $CODING_SET
}

selftest() {
  local fail=0 out rc s; t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  [ -n "$PY" ] || { echo "no working python3/python/py"; return 1; }
  ck() { [ "$2" = "$3" ] || { echo "FAIL: $1 (want '$3', got '$2')"; fail=1; }; }
  me() { bash "$0" "$@" 2>&1; }
  s=$t/p/.claude/settings.json; mkdir -p "$t/p/.claude"
  out=$(me "$t/p" --check); rc=$?
  ck "check on a folder with no settings.json fails" "$rc" 1
  case $out in *bacon-dev@ai-tools*ponytail@ponytail*superpowers@claude-plugins-official*) ;; *) ck "check lists all three missing ids" "$out" "all three" ;; esac
  [ -e "$s" ] && ck "check must not create the file" "created" "absent"
  me "$t/p" >/dev/null; rc=$?
  ck "write on a fresh folder succeeds" "$rc" 0
  me "$t/p" --check >/dev/null; ck "check passes after a write" "$?" 0
  printf '{"model":"x","enabledPlugins":{"other@m":true,"ponytail@ponytail":false},"hooks":{"a":1}}\n' > "$s"
  me "$t/p" --check >/dev/null; ck "a false value counts as missing" "$?" 1
  me "$t/p" >/dev/null
  out=$("$PY" -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["model"],d["hooks"]["a"],d["enabledPlugins"]["other@m"],d["enabledPlugins"]["ponytail@ponytail"],len(d["enabledPlugins"]))' "$s")
  ck "merge keeps other keys and flips the false one" "$out" "x 1 True True 4"
  cp "$s" "$t/before"; me "$t/p" >/dev/null; cmp -s "$s" "$t/before"; ck "second run is a no-op (idempotent)" "$?" 0
  echo '{bad' > "$s"; me "$t/p" >/dev/null; ck "unreadable settings.json: exit 2, file untouched" "$?:$(cat "$s")" "2:{bad"
  [ "$fail" = 0 ] && echo "coding-mode selftest OK"
  return $fail
}

case "${1:-}" in
  --selftest) selftest; exit $? ;;
  ""|-h|--help) sed -n 2,9p "$0"; exit 2 ;;
esac
[ -n "$PY" ] || { echo "no working python3/python/py"; exit 2; }
dir=$1; mode=write
[ "${2:-}" = "--check" ] && mode=check
[ -d "$dir" ] || { echo "not a directory: $dir"; exit 2; }
out=$(apply "$dir/.claude/settings.json" "$mode"); rc=$?
case $mode:$rc in
  check:1) echo "coding mode off in $dir — missing: $out"; exit 1 ;;
  check:0) echo "coding mode on in $dir"; exit 0 ;;
  write:0) echo "coding mode written to $dir/.claude/settings.json"; exit 0 ;;
  *) echo "$out"; exit 2 ;;
esac
