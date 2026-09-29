#!/usr/bin/env bash
# wrong.sh — he records a failure of mine, in his own words, with no model in the path.
#
# Why this exists: every other failure metric depends on me noticing and choosing
# to write it down, which makes me the author of my own numerator. This one does
# not. It appends verbatim, before I see the prompt, and I never mediate it.
#
# Two entry points, one behaviour:
#   wrong.sh <context-repo> "text"     append directly (usable as `! wrong ...`)
#   wrong.sh <context-repo> --hook     read a UserPromptSubmit JSON on stdin and
#                                      append when the prompt starts with `wrong:`
#   wrong.sh --selftest                synthetic fixtures
#
# The row lands in context/metrics/failures.md with class `unclassified` and
# caught_by `him`. Classification is a later, optional step: an unclassified row
# is still a recorded failure, and leaving it unclassified must never lose it.
set -u

LOG_REL="context/metrics/failures.md"

append_row() {
  ctx=$1; text=$2
  log="$ctx/$LOG_REL"
  [ -f "$log" ] || { echo "wrong: no failure log at $log" >&2; return 1; }
  # Pipes are the field separator, so they cannot survive inside a field.
  clean=$(printf '%s' "$text" | tr '\n\t|' '   ' | sed 's/  */ /g; s/^ //; s/ $//')
  [ -n "$clean" ] || { echo "wrong: nothing to record" >&2; return 1; }
  printf '%s | %s | unclassified | him | %s | reported by him, verbatim\n' \
    "$(date +%Y-%m-%d)" "${CLAUDE_SESSION_ID:-session-unknown}" "$clean" >> "$log"
  echo "wrong: recorded — $clean"
}

from_hook() {
  ctx=$1
  input=$(cat 2>/dev/null || true)
  # Extract .prompt without a JSON parser: python3 is present on both machines, but
  # this hook must not fail the prompt if it is missing.
  if command -v python3 >/dev/null 2>&1; then
    prompt=$(printf '%s' "$input" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("prompt",""))
except Exception: print("")' 2>/dev/null)
  else
    prompt=$(printf '%s' "$input" | sed -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p')
  fi
  case $prompt in
    wrong:*|WRONG:*|wrong\ -*) ;;
    *) exit 0 ;;
  esac
  text=$(printf '%s' "$prompt" | sed 's/^[Ww][Rr][Oo][Nn][Gg]:[[:space:]]*//; s/^wrong -[[:space:]]*//')
  append_row "$ctx" "$text"
}

selftest() {
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  mkdir -p "$t/context/metrics"
  printf '# Failures\n\n' > "$t/$LOG_REL"
  ok() { echo "  ok   $1"; }
  bad() { echo "  FAIL $1"; exit 1; }

  "$0" "$t" "you sent an email during a test" >/dev/null
  grep -q '| unclassified | him | you sent an email during a test |' "$t/$LOG_REL" ||
    bad "direct append did not land verbatim: $(tail -1 "$t/$LOG_REL")"
  ok "direct append lands verbatim with caught_by=him"

  printf '{"prompt":"wrong: the letter had AI padding again"}' | "$0" "$t" --hook >/dev/null
  grep -q 'the letter had AI padding again' "$t/$LOG_REL" || bad "hook did not record a wrong: prompt"
  ok "hook records a wrong: prompt"

  before=$(grep -c '^2' "$t/$LOG_REL")
  printf '{"prompt":"what is the status of the ledger"}' | "$0" "$t" --hook >/dev/null
  [ "$(grep -c '^2' "$t/$LOG_REL")" = "$before" ] || bad "an ordinary prompt was recorded as a failure"
  ok "an ordinary prompt is a no-op"

  # \\t, not a literal tab: a raw tab inside a JSON string is invalid JSON, which
  # made this case silently no-op and the assertion below read a stale row.
  printf '{"prompt":"wrong: pipes | and\\ttabs must not break the row"}' | "$0" "$t" --hook >/dev/null
  # The pipe and the tab both become a space, then runs collapse: one space each.
  tail -1 "$t/$LOG_REL" | grep -q 'pipes and tabs must not break the row' ||
    bad "pipes/tabs case did not record: $(tail -1 "$t/$LOG_REL")"
  [ "$(tail -1 "$t/$LOG_REL" | awk -F' \\| ' '{print NF}')" = 6 ] ||
    bad "field count broke: $(tail -1 "$t/$LOG_REL")"
  ok "pipes and tabs in his text cannot break the field count"

  before=$(grep -c '^2' "$t/$LOG_REL")
  printf '{"prompt":"wrong:   "}' | "$0" "$t" --hook >/dev/null 2>&1
  [ "$(grep -c '^2' "$t/$LOG_REL")" = "$before" ] || bad "an empty report was recorded"
  ok "an empty report is refused"

  echo "selftest passed"
}

case ${1:-} in
  --selftest) selftest ;;
  "") echo "usage: wrong.sh <context-repo> \"text\" | wrong.sh <context-repo> --hook | wrong.sh --selftest" >&2; exit 2 ;;
  *)
    ctx=$1; shift
    case ${1:-} in
      --hook) from_hook "$ctx" ;;
      "") echo "wrong: nothing to record" >&2; exit 1 ;;
      *) append_row "$ctx" "$*" ;;
    esac
    ;;
esac
