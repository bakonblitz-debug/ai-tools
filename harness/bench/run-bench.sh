#!/usr/bin/env bash
# run-bench.sh — run the fixed bench set against the local agent.
#
#   bash run-bench.sh all
#   bash run-bench.sh C1-slugify
#   BENCH_MODEL=devstral:24k bash run-bench.sh C1-slugify
#
# Work happens in /tmp, not on the share. The agent uid can write the share (see
# the filesystem-confinement notes), but an exam that edits files should not run
# over SMB while it is being timed, and a sandbox the agent owns outright removes
# permissions as an explanation for a failure. Artifacts are copied back to
# results/<run-id>/ afterwards, by this script, as the user.
set -u
BENCH=$(cd "$(dirname "$0")" && pwd)
# Overridable so this is not welded to one machine. Defaults are the WSL2 box:
# the agent runs as its own uid, so the binary is invoked through sudo -u.
HERMES=${HERMES_BIN:-/home/isaac/.hermes/.hermes/hermes-agent/venv/bin/hermes}
HERMES_USER=${HERMES_USER:-hermes}
WWW=${WWW_ROOT:-/mnt/www}
h() { sudo -n -u "$HERMES_USER" "$HERMES" "$@"; }

RUN=$(date +%Y%m%d-%H%M%S)
OUT=$BENCH/results/$RUN
LEDGER=$BENCH/scoreboard/results.jsonl
mkdir -p "$OUT" "$BENCH/scoreboard"

# Principle 2: a score means nothing without the configuration that produced it.
MODEL=${BENCH_MODEL:-$(h config get model.default | tr -d '\r ')}
[ -n "${BENCH_MODEL:-}" ] && { ORIG=$(h config get model.default | tr -d '\r ')
  trap 'h config set model.default "$ORIG" >/dev/null' EXIT
  h config set model.default "$MODEL" >/dev/null; }

fingerprint() {
  # sha1("") is da39a3ee5e6b: if either hash reads that, the path moved and the
  # fingerprint is lying about what produced the score. Principle 2 or nothing.
  printf '{"type":"run","run_id":"%s","at":"%s","model":"%s","ctx":"%s","hermes":"%s","skills_sha":"%s","soul_sha":"%s"}\n' \
    "$RUN" "$(date -Is)" "$MODEL" "$(h config get model.context_length | tr -dc 0-9)" \
    "$(h --version 2>/dev/null | tr -d '\r' | head -1)" \
    "$(find "$WWW/ai-tools/harness/skills" -type f -name '*.md' -exec sha1sum {} + 2>/dev/null | sort | sha1sum | cut -c1-12)" \
    "$(sha1sum "$WWW/local-ai-setup/SOUL.md" 2>/dev/null | cut -c1-12)"
}
fingerprint | tee "$OUT/metadata.json" >> "$LEDGER"

TASKS=$( [ "${1:-all}" = all ] && ls "$BENCH/tasks/fixed" || echo "$@" )
for T in $TASKS; do
  TD=$BENCH/tasks/fixed/$T
  [ -f "$TD/meta.env" ] || { echo "no such task: $T"; continue; }
  CATEGORY=; TIER=; FIXTURE=none; GRADE=machine; TIMEOUT=1800
  . "$TD/meta.env"

  W=/tmp/bench-$RUN/$T/work
  mkdir -p "$W"
  [ "$FIXTURE" = none ] || cp -r "$BENCH/fixtures/$FIXTURE/." "$W/"
  [ -f "$TD/setup.sh" ] && bash "$TD/setup.sh" "$W" "$TD"
  # The agent runs as hermes and must own what it is asked to edit.
  chmod -R a+rwX "/tmp/bench-$RUN/$T"

  # --query-file, not -q: prompts are markdown with backticks and $ signs, and
  # argv is one shell-quoting mistake away from mangling them. `chat` rather than
  # -z because -z prints only the final answer, and principle 3 needs the tool
  # calls in the transcript to scan for fabricated output.
  sed "s|__WORKDIR__|$W|g" "$TD/prompt.md" > "/tmp/bench-$RUN/$T/prompt.txt"
  chmod a+r "/tmp/bench-$RUN/$T/prompt.txt"
  echo "=== $T ($CATEGORY tier $TIER, timeout ${TIMEOUT}s) ..."
  START=$(date +%s)
  # --no-restore-cwd is load-bearing: without it a fresh session restores the
  # recorded workspace cwd (the share root), and it writes its answer there
  # share root instead of the sandbox. Measured 2026-09-04, on C2 and C3.
  timeout "$TIMEOUT" sudo -n -u "$HERMES_USER" "$HERMES" chat \
    --query-file "/tmp/bench-$RUN/$T/prompt.txt" --oneshot --in "$W" --no-restore-cwd \
    --yolo --run-budget "$TIMEOUT" \
    > "/tmp/bench-$RUN/$T/transcript.log" 2>&1
  RC=$?
  SECS=$(( $(date +%s) - START ))

  RESULT=NEEDS_GRADING
  CHECK=
  if [ -f "$TD/check.sh" ]; then
    CHECK=$(bash "$TD/check.sh" "$W" "$TD" 2>&1); CRC=$?
    printf '%s\n' "$CHECK" > "/tmp/bench-$RUN/$T/check.log"
    if [ $CRC -eq 0 ]; then
      RESULT=PASS
      [ "$GRADE" = both ] && RESULT=MACHINE_PASS_NEEDS_GRADING
    else
      RESULT=FAIL
    fi
  fi
  [ $RC -eq 124 ] && RESULT=TIMEOUT

  cp -r "/tmp/bench-$RUN/$T" "$OUT/$T"
  printf '{"type":"check","run_id":"%s","task":"%s","category":"%s","tier":%s,"result":"%s","secs":%s,"rc":%s}\n' \
    "$RUN" "$T" "$CATEGORY" "$TIER" "$RESULT" "$SECS" "$RC" >> "$LEDGER"
  echo "    $RESULT in ${SECS}s"
done

echo
echo "run $RUN — results in $OUT, records appended to $LEDGER"
echo "Grade the NEEDS_GRADING records per grading/RUBRIC.md, and read every transcript"
echo "for fabricated tool output: that is an auto-zero even where check.sh passed."
