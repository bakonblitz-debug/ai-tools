#!/usr/bin/env bash
# health-check.sh — rerunnable health checks for THE HARNESS.
#
#   health-check.sh              run everything, one line per check
#   health-check.sh -v           show the detail line even when a check passes
#   health-check.sh <substring>  run only checks whose name contains <substring>
#
# Exit 0 if nothing FAILed. SKIP never fails the run — it means "could not test from
# here", and prints the command to run by hand.
#
# SCOPE. This file covers the harness itself: the shared workspace, the machines that
# reach it, and the tooling that runs on all of them. It is deliberately generic —
# nothing here knows about any one agent, model, or GPU. Deployment-specific checks
# live with that deployment: Hermes has its own at
# `local-ai-setup/scripts/hermes-health-check.sh` (private repo — it carries gateway
# IPs and machine paths that do not belong in a public one).
#
# WHY THIS EXISTS. Every problem found on 2026-09-03 was silent rather than loud:
# `ollama ps` reported "100% GPU" for a model running on the CPU, WSL2-HANDOFF said
# "NOT YET FIXED" about something fixed eleven days earlier, and a digest printed an
# empty list because it looked in the wrong directory. None announced itself. These
# checks exist to make that class of drift announce itself in one command.
#
# HOW TO ADD A CHECK. Write a function `check_<name>` that echoes one detail line and
# returns 0 (pass), 1 (fail) or 77 (skip). It is picked up automatically — no registry.
#
# ASSERT INVARIANTS, NOT SNAPSHOTS. "23 open items" is true today and wrong next week;
# "all three machines report the same count" stays true forever. Derive the expected
# value at run time and compare, never hardcode it. A check that needs editing every
# time the workspace changes gets deleted instead of fixed.
set -u

case "$(uname -s)" in
  Darwin)               SYSTEM=Mac;     WWW=$HOME/www ;;
  MINGW*|MSYS*|CYGWIN*) SYSTEM=Windows; WWW=/m ;;
  Linux) if grep -qi microsoft /proc/version 2>/dev/null
         then SYSTEM=WSL2; WWW=/mnt/www
         else SYSTEM=Linux; WWW=$HOME/www; fi ;;
  *)                    SYSTEM=$(uname -s); WWW=$HOME/www ;;
esac
# Configuration. Two knobs, and for each one it matters whether the user ASKED for a
# value or just got the default: "you pointed me somewhere that is not there" is a
# failure, "you never mentioned a workspace" is simply an unconfigured optional piece.
# Conflating those is what made a fresh clone report three FAILs it could do nothing
# about. Workspace root: --root PATH. Remote: REMOTE_HOST (was hardcoded `mac`).
WWW_EXPLICIT=0
REMOTE_EXPLICIT=${REMOTE_HOST:+1}; REMOTE_EXPLICIT=${REMOTE_EXPLICIT:-0}
REMOTE_HOST=${REMOTE_HOST:-mac}

# Resolve siblings relative to THIS file, not to the detected workspace. These scripts
# ship together, so a clone can test itself; keying off $WWW made a fresh clone report
# "session-todo.sh missing" while it sat in the same directory.
SCRIPTS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Capture first and filter after: piping into `grep -v` would make the FUNCTION return
# grep's status, and grep exits 1 when it filters everything away — exactly what a
# silent `test -d` produces, turning every passing boolean check into a failure.
wsl_() {
  local out rc
  out=$(MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash -lc "$*" 2>&1); rc=$?
  printf '%s\n' "$out" | tr -d '\r' | grep -v 'Failed to translate'
  return $rc
}
have() { command -v "$1" >/dev/null 2>&1; }

# ==================================================================================
# Checks. Each echoes ONE detail line and returns 0 pass / 1 fail / 77 skip.
# ==================================================================================

check_workspace_mounted() {
  if [ ! -d "$WWW/context/context" ]; then
    # Explicitly pointed somewhere that is not there = broken. Auto-detected default
    # that does not exist = simply not configured, which is the normal state for a
    # new install and must not fail the run.
    [ "$WWW_EXPLICIT" = 1 ] && { echo "no tree at $WWW/context/context"; return 1; }
    echo "no context tree (optional) — point at one with --root PATH"; return 77
  fi
  echo "$SYSTEM → $WWW"
}

check_remote_reachable() {
  have ssh || { echo "no ssh client"; return 77; }
  [ "$SYSTEM" = Mac ] && { echo "running on the remote itself"; return 0; }
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" true 2>/dev/null     && { echo "ssh $REMOTE_HOST ok"; return 0; }
  # Unreachable is only a failure if a remote was actually requested. A single-machine
  # setup has none, and must not be told its git is broken.
  [ "$REMOTE_EXPLICIT" = 1 ]     && { echo "ssh $REMOTE_HOST failed — git for the share runs there, so commits are blocked"; return 1; }
  echo "no remote configured (optional) — set REMOTE_HOST to enable"; return 77
}

check_digest_selftest() {
  [ -f "$SCRIPTS/session-todo.sh" ] || { echo "session-todo.sh missing"; return 1; }
  out=$(bash "$SCRIPTS/session-todo.sh" --selftest 2>&1) \
    || { echo "${out:-selftest failed}"; return 1; }
  echo "$out"
}

# The derived-value check. The count changes as work is done, so asserting a number
# would rot within days. What must hold is that every machine sees the SAME tree.
# A disagreement means a stale mount, an unsynced clone, or a machine-local file
# leaking into a shared digest — all real, all otherwise silent.
check_digest_agreement() {
  local here there n
  # Nothing to cross-check without a tree, and "no count" would otherwise read as a
  # disagreement between machines rather than as an absent optional piece.
  [ -d "$WWW/context/context" ] || { echo "no workspace to compare"; return 77; }
  here=$(bash "$SCRIPTS/session-todo.sh" "$WWW" 2>/dev/null | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
  [ -n "$here" ] || { echo "digest produced no count on $SYSTEM"; return 1; }
  n="$SYSTEM=$here"

  if [ "$SYSTEM" = Windows ] && have wsl.exe; then
    there=$(wsl_ "bash /mnt/www/ai-tools/harness/scripts/session-todo.sh" | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
    [ -n "$there" ] && n="$n WSL2=$there"
  fi
  if [ "$SYSTEM" != Mac ] && ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" true 2>/dev/null; then
    there=$(ssh "$REMOTE_HOST" 'bash ~/www/ai-tools/harness/scripts/session-todo.sh' 2>/dev/null | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
    [ -n "$there" ] && n="$n Mac=$there"
  fi

  for v in $n; do
    case ${v#*=} in
      "$here") ;;
      *) echo "MISMATCH: $n — machines disagree about the same tree"; return 1 ;;
    esac
  done
  case $n in
    *" "*) echo "$n — agree" ;;
    *)     echo "$n (only this machine reachable)"; return 77 ;;
  esac
}

# The context tree and memory are the record everything else points at. Git for the
# share runs on the Mac; unpushed work is invisible to the other machine, which is
# how a fix gets applied and then re-investigated weeks later.
check_context_synced() {
  have ssh || { echo "no ssh client"; return 77; }
  local dirty ahead
  dirty=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" 'cd ~/www/context && git status --porcelain | wc -l' 2>/dev/null | tr -d ' ')
  [ -n "$dirty" ] || { echo "could not reach the context repo on the Mac"; return 77; }
  ahead=$(ssh "$REMOTE_HOST" 'cd ~/www/context && git rev-list --count @{u}..HEAD 2>/dev/null' 2>/dev/null | tr -d ' ')
  [ "$dirty" = 0 ] || { echo "$dirty uncommitted file(s) — the sync hook should have caught these"; return 1; }
  [ "${ahead:-0}" = 0 ] || { echo "$ahead commit(s) unpushed — the other machine cannot see them"; return 1; }
  echo "clean and pushed"
}

# ==================================================================================
# Runner
# ==================================================================================
VERBOSE=0; FILTER=""
for a in "$@"; do
  case ${TAKE_ROOT:-} in 1) WWW=$a; WWW_EXPLICIT=1; TAKE_ROOT=0; continue ;; esac
  case $a in
    -v|--verbose) VERBOSE=1 ;;
    --root)       TAKE_ROOT=1 ;;
    *)            FILTER=$a ;;
  esac
done

P=0; F=0; S=0
for fn in $(declare -F | awk '{print $3}' | grep '^check_' | sort); do
  name=${fn#check_}
  case $name in *"$FILTER"*) ;; *) continue ;; esac
  detail=$("$fn"); rc=$?
  case $rc in
    0)  P=$((P+1)); [ "$VERBOSE" = 1 ] && printf '  \033[32mPASS\033[0m  %-22s %s\n' "$name" "$detail" \
                                       || printf '  \033[32mPASS\033[0m  %s\n' "$name" ;;
    77) S=$((S+1)); printf '  \033[33mSKIP\033[0m  %-22s %s\n' "$name" "$detail" ;;
    *)  F=$((F+1)); printf '  \033[31mFAIL\033[0m  %-22s %s\n' "$name" "$detail" ;;
  esac
done

printf '\n  harness: %d passed, %d failed, %d skipped\n' "$P" "$F" "$S"
[ "$F" -eq 0 ]
