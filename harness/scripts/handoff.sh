#!/usr/bin/env bash
# handoff.sh — type `handoff` in a fresh session and the open plan lands in context.
#
# The session digest already LISTS open handoffs, which still leaves a manual step:
# noticing the line, then asking for the file to be read. This removes it. As a
# UserPromptSubmit hook, a prompt of `handoff` (optionally with a topic) prints the
# plan to stdout, which the harness injects as context before the model answers.
#
# Why a hook and not a skill: a skill routes through the model, which can summarise,
# skip or "improve" the plan. A hook cannot. The text arrives verbatim.
#
#   handoff                 the one open plan, or a list if there are several
#   handoff <topic>         the plan whose filename matches <topic>
#   handoff list            names only
#
# A plan is open when its `## Status` section says `open`. Closing one is editing
# that line, which is also what stops it being injected.
set -u

PLANS="${PLANS_DIR:-$HOME/www/.plans}"
MAX_LINES=${HANDOFF_MAX_LINES:-400}

open_plans() {
  [ -d "$PLANS" ] || return 0
  for f in "$PLANS"/handoff-*.md; do
    [ -e "$f" ] || continue
    # `open` on its own line inside the Status section. A plan with no Status is not
    # open: silence must never mean "inject me".
    awk '/^##[[:space:]]*Status/{s=1;next} /^##[[:space:]]/{s=0} s&&/^[[:space:]]*open[[:space:]]*$/{found=1} END{exit !found}' "$f" &&
      echo "$f"
  done
}

emit() {
  f=$1
  echo "=== handoff: ${f##*/} ==="
  n=$(grep -c '' "$f")
  if [ "$n" -gt "$MAX_LINES" ]; then
    head -n "$MAX_LINES" "$f"
    echo "…[truncated at $MAX_LINES of $n lines — read $f for the rest]"
  else
    cat "$f"
  fi
}

serve() {
  topic=${1:-}
  plans=$(open_plans)
  [ -n "$plans" ] || { echo "handoff: no open plan in $PLANS"; return 0; }
  if [ -n "$topic" ]; then
    match=$(printf '%s\n' "$plans" | grep -i -- "$topic" | head -1)
    [ -n "$match" ] || { echo "handoff: no open plan matching '$topic'. Open:"; printf '%s\n' "$plans" | sed 's|.*/|  |'; return 0; }
    emit "$match"; return 0
  fi
  count=$(printf '%s\n' "$plans" | grep -c .)
  if [ "$count" = 1 ]; then emit "$plans"; return 0; fi
  echo "handoff: $count open plans — say 'handoff <topic>' to pick one:"
  printf '%s\n' "$plans" | sed 's|.*/handoff-|  |; s|\.md$||'
}

from_hook() {
  input=$(cat 2>/dev/null || true)
  if command -v python3 >/dev/null 2>&1; then
    prompt=$(printf '%s' "$input" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("prompt",""))
except Exception: print("")' 2>/dev/null)
  else
    prompt=$(printf '%s' "$input" | sed -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  fi
  # Only a bare `handoff` (plus an optional topic) triggers. A sentence merely
  # containing the word does not, or every discussion of handoffs would inject one.
  case $(printf '%s' "$prompt" | tr 'A-Z' 'a-z') in
    handoff|handoff\ *|"resume handoff"|"resume handoff "*) ;;
    *) exit 0 ;;
  esac
  topic=$(printf '%s' "$prompt" | tr 'A-Z' 'a-z' | sed 's/^resume handoff//; s/^handoff//; s/^[[:space:]]*//; s/[[:space:]]*$//')
  case $topic in list) open_plans | sed 's|.*/handoff-|  |; s|\.md$||'; exit 0 ;; esac
  serve "$topic"
}

selftest() {
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  export PLANS_DIR="$t"
  ok() { echo "  ok   $1"; }
  bad() { echo "  FAIL $1"; exit 1; }

  printf '# One\n\n## Status\nopen\n\nbody-one\n' > "$t/handoff-alpha.md"
  printf '# Two\n\n## Status\ndone\n\nbody-two\n' > "$t/handoff-beta.md"

  out=$(printf '{"prompt":"handoff"}' | "$0" --hook)
  case $out in *body-one*) ;; *) bad "the single open plan was not emitted" ;; esac
  case $out in *body-two*) bad "a closed plan was emitted" ;; esac
  ok "emits the open plan and never a closed one"

  printf '# Three\n\n## Status\nopen\n\nbody-three\n' > "$t/handoff-gamma.md"
  out=$(printf '{"prompt":"handoff"}' | "$0" --hook)
  case $out in *"2 open plans"*) ;; *) bad "two open plans should produce a chooser: $out" ;; esac
  ok "several open plans produce a list, not a guess"

  out=$(printf '{"prompt":"handoff gamma"}' | "$0" --hook)
  case $out in *body-three*) ;; *) bad "topic match failed" ;; esac
  ok "a topic picks the plan"

  out=$(printf '{"prompt":"what did we say about the handoff protocol"}' | "$0" --hook)
  [ -z "$out" ] || bad "a sentence containing the word must not inject: $out"
  ok "only a bare handoff prompt triggers"

  printf '# Four\n\nno status section at all\n' > "$t/handoff-delta.md"
  out=$(printf '{"prompt":"handoff delta"}' | "$0" --hook)
  case $out in *"no open plan matching"*) ;; *) bad "a plan with no Status must not count as open: $out" ;; esac
  ok "a plan with no Status is not open"

  rm -f "$t"/handoff-*.md
  out=$(printf '{"prompt":"handoff"}' | "$0" --hook)
  case $out in *"no open plan"*) ;; *) bad "empty case should say so: $out" ;; esac
  ok "says so when there is nothing open"

  echo "selftest passed"
}

case ${1:-} in
  --selftest) selftest ;;
  --hook)     from_hook ;;
  list)       open_plans | sed 's|.*/handoff-|  |; s|\.md$||' ;;
  *)          serve "${1:-}" ;;
esac
