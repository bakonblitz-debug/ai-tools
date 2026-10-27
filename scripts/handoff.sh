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
# Automatic handoff (2026-10-14, his call: "as soon as you feel we should, just do it"):
# context-budget.py tells the model to write handoff-auto-<folder>.md once a session
# gets long, and settings.json's autoCompactWindow compacts it without asking. As a
# SessionStart hook, --session-start then puts that folder's open plan into the new or
# compacted session, so nothing has to be typed. A resumed session is skipped: it
# already holds its own context.
#
# A plan is open when its `## Status` section says `open`. Closing one is editing
# that line, which is also what stops it being injected.
set -u

PLANS="${PLANS_DIR:-$HOME/www/.plans}"
MAX_LINES=${HANDOFF_MAX_LINES:-400}

# `open` on its own line inside the Status section. A plan with no Status is not
# open: silence must never mean "inject me".
is_open() {
  awk '/^##[[:space:]]*Status/{s=1;next} /^##[[:space:]]/{s=0} s&&/^[[:space:]]*open[[:space:]]*$/{found=1} END{exit !found}' "$1"
}

open_plans() {
  [ -d "$PLANS" ] || return 0
  for f in "$PLANS"/handoff-*.md; do
    [ -e "$f" ] && is_open "$f" && echo "$f"
  done
}

# One plan per working folder: /Users/me/www/proj -> handoff-auto-Users-me-www-proj.md
# ponytail: Mac and PC spell the same folder differently, so a plan does not cross machines
auto_path() {
  slug=$(printf '%s' "$1" | tr -c 'A-Za-z0-9' '-' | sed 's/^-*//; s/-*$//')
  echo "$PLANS/handoff-auto-$slug.md"
}

hook_field() {
  printf '%s' "$1" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get(sys.argv[1],""))
except Exception: print("")' "$2" 2>/dev/null
}

session_start() {
  input=$(cat 2>/dev/null || true)
  [ "$(hook_field "$input" source)" = resume ] && exit 0
  # The launch folder, not the live cwd: a session cd's around, and the budget hook
  # names the plan from the same variable.
  cwd=${CLAUDE_PROJECT_DIR:-$(hook_field "$input" cwd)}
  [ -n "$cwd" ] || exit 0
  f=$(auto_path "$cwd")
  [ -e "$f" ] && is_open "$f" || exit 0
  echo "Resuming automatically: the previous session in this folder handed off to this plan."
  emit "$f"
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
  unset CLAUDE_PROJECT_DIR
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

  auto=$("$0" --auto-path /Users/me/www/proj)
  [ "$auto" = "$t/handoff-auto-Users-me-www-proj.md" ] || bad "auto path is not derived from the cwd: $auto"
  ok "the automatic plan's path is derived from the session's folder"

  printf '# Auto\n\n## Status\nopen\n\nbody-auto\n' > "$auto"
  out=$(printf '{"source":"clear","cwd":"/Users/me/www/proj"}' | "$0" --session-start)
  case $out in *body-auto*) ;; *) bad "a cleared session did not get its plan: $out" ;; esac
  out=$(printf '{"source":"compact","cwd":"/Users/me/www/proj"}' | "$0" --session-start)
  case $out in *body-auto*) ;; *) bad "a compacted session did not get its plan: $out" ;; esac
  ok "a cleared or compacted session gets its folder's plan with no prompt"

  out=$(printf '{"source":"resume","cwd":"/Users/me/www/proj"}' | "$0" --session-start)
  [ -z "$out" ] || bad "a resumed session already has its context: $out"
  out=$(printf '{"source":"startup","cwd":"/Users/me/www/other"}' | "$0" --session-start)
  [ -z "$out" ] || bad "another folder's plan leaked in: $out"
  ok "a resumed session or another folder gets nothing"

  out=$(printf '{"source":"clear","cwd":"/Users/me/www/proj/sub"}' | CLAUDE_PROJECT_DIR=/Users/me/www/proj "$0" --session-start)
  case $out in *body-auto*) ;; *) bad "the launch folder must win over a cwd the session moved to: $out" ;; esac
  ok "the launch folder wins over wherever the session cd'd to"

  printf '# Auto\n\n## Status\ndone\n\nbody-auto\n' > "$auto"
  out=$(printf '{"source":"startup","cwd":"/Users/me/www/proj"}' | "$0" --session-start)
  [ -z "$out" ] || bad "a closed automatic plan was injected: $out"
  ok "a closed automatic plan stays out"

  echo "selftest passed"
}

case ${1:-} in
  --selftest) selftest ;;
  --hook)     from_hook ;;
  --session-start) session_start ;;
  --auto-path) auto_path "${2:?--auto-path needs a folder}" ;;
  list)       open_plans | sed 's|.*/handoff-|  |; s|\.md$||' ;;
  *)          serve "${1:-}" ;;
esac
