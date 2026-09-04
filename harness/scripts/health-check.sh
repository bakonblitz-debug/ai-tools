#!/usr/bin/env bash
# health-check.sh — rerunnable health checks for the harness and the local-AI stack.
#
#   health-check.sh              run everything, one line per check
#   health-check.sh -v           show the detail line even when a check passes
#   health-check.sh <substring>  run only checks whose name contains <substring>
#
# Exit 0 if nothing FAILed. SKIP never fails the run — it means "could not test from
# here" (usually needs root), and prints the command to run by hand.
#
# WHY THIS EXISTS. Every problem found on 2026-09-03 was invisible rather than loud:
# `ollama ps` reported "100% GPU" for a model running on the CPU, WSL2-HANDOFF said
# "NOT YET FIXED" about something fixed eleven days earlier, and a digest printed an
# empty list because it looked in the wrong directory. None of them announced itself.
# These checks exist to make that class of drift announce itself in one command.
#
# HOW TO ADD A CHECK. Write a function `check_<name>` that echoes one detail line and
# returns 0 (pass), 1 (fail) or 77 (skip). It is picked up automatically — no registry.
#
# ASSERT INVARIANTS, NOT SNAPSHOTS. "23 open items" is true today and wrong next week;
# "all three machines report the same count" stays true forever. Derive the expected
# value at run time and compare, never hardcode it. A check that needs editing every
# time the workspace changes gets deleted instead of fixed.
set -u

# --- workspace root, same detection as session-todo.sh -----------------------------
case "$(uname -s)" in
  Darwin)               SYSTEM=Mac;     WWW=$HOME/www ;;
  MINGW*|MSYS*|CYGWIN*) SYSTEM=Windows; WWW=/m ;;
  Linux) if grep -qi microsoft /proc/version 2>/dev/null
         then SYSTEM=WSL2; WWW=/mnt/www
         else SYSTEM=Linux; WWW=$HOME/www; fi ;;
  *)                    SYSTEM=$(uname -s); WWW=$HOME/www ;;
esac
SCRIPTS=$WWW/ai-tools/harness/scripts

# In WSL the Windows-side PATH leaks in and wsl.exe warns about untranslatable entries,
# so the output needs filtering. Capture first and filter after: piping into `grep -v`
# would make the FUNCTION return grep's status, and grep exits 1 when it filters
# everything away — which is precisely what a silent `test -d` produces. That turns
# every passing boolean check into a failure. Return the remote status explicitly.
wsl_() {
  local out rc
  out=$(MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash -lc "$*" 2>&1); rc=$?
  printf '%s\n' "$out" | tr -d '\r' | grep -v 'Failed to translate'
  return $rc
}
have()  { command -v "$1" >/dev/null 2>&1; }

# ==================================================================================
# Checks. Each echoes ONE detail line and returns 0 pass / 1 fail / 77 skip.
# ==================================================================================

check_workspace_mounted() {
  [ -d "$WWW/context/context" ] || { echo "no tree at $WWW/context/context"; return 1; }
  echo "$SYSTEM → $WWW"
}

check_mac_reachable() {
  have ssh || { echo "no ssh client"; return 77; }
  [ "$SYSTEM" = Mac ] && { echo "running on the Mac"; return 0; }
  ssh -o BatchMode=yes -o ConnectTimeout=8 mac true 2>/dev/null \
    || { echo "ssh mac failed — git for the share runs there, so commits are blocked"; return 1; }
  echo "ssh mac ok"
}

check_digest_selftest() {
  [ -x "$SCRIPTS/session-todo.sh" ] || { echo "session-todo.sh missing"; return 1; }
  out=$(bash "$SCRIPTS/session-todo.sh" --selftest 2>&1) \
    || { echo "${out:-selftest failed}"; return 1; }
  echo "$out"
}

# The derived-value check. The count changes as work is done, so asserting a number
# would rot within days. What must hold is that every machine sees the SAME tree.
# A disagreement means a stale mount, an unsynced clone, or a machine-local file
# leaking into a shared digest — all real, all otherwise silent.
check_digest_agreement() {
  local here there_wsl there_mac n
  here=$(bash "$SCRIPTS/session-todo.sh" 2>/dev/null | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
  [ -n "$here" ] || { echo "digest produced no count on $SYSTEM"; return 1; }
  n="$SYSTEM=$here"

  if [ "$SYSTEM" = Windows ] && have wsl.exe; then
    there_wsl=$(wsl_ "bash /mnt/www/ai-tools/harness/scripts/session-todo.sh" | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
    [ -n "$there_wsl" ] && n="$n WSL2=$there_wsl"
  fi
  if [ "$SYSTEM" != Mac ] && ssh -o BatchMode=yes -o ConnectTimeout=8 mac true 2>/dev/null; then
    there_mac=$(ssh mac 'bash ~/www/ai-tools/harness/scripts/session-todo.sh' 2>/dev/null | sed -n '1s/.*— \([0-9]*\) items.*/\1/p')
    [ -n "$there_mac" ] && n="$n Mac=$there_mac"
  fi

  # compare every reported count against the first
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

check_wsl_running() {
  have wsl.exe || { echo "not a Windows host"; return 77; }
  wsl_ 'true' >/dev/null 2>&1 || { echo "WSL2 not responding"; return 1; }
  echo "$(wsl_ 'uptime -p' | head -1)"
}

check_wsl_share_mounted() {
  have wsl.exe || { echo "not a Windows host"; return 77; }
  wsl_ 'test -d /mnt/www/context/context' >/dev/null 2>&1 \
    || { echo "/mnt/www not mounted in WSL — Hermes cannot read the tree"; return 1; }
  echo "/mnt/www mounted"
}

# The staleness trap that has broken this stack twice: HOST_IP is pinned in config
# files and the WSL subnet moves. Compare the pinned value to the live gateway.
check_ollama_reachable() {
  have wsl.exe || { echo "not a Windows host"; return 77; }
  local pinned live code
  pinned=$(wsl_ 'sed -n "s/^HOST_IP=//p" /etc/airgap.conf' | head -1)
  # parse on this side: nested quoting through `bash -lc` eats awk's $3
  live=$(wsl_ 'ip route' | awk '/^default/{print $3; exit}')
  [ -n "$pinned" ] || { echo "no HOST_IP in /etc/airgap.conf"; return 1; }
  [ "$pinned" = "$live" ] || { echo "HOST_IP $pinned != live gateway $live — the classic stale-subnet break"; return 1; }
  code=$(wsl_ "curl -s -m 8 -o /dev/null -w '%{http_code}' http://$pinned:11434/api/tags" | tail -1)
  [ "$code" = 200 ] || { echo "Ollama at $pinned:11434 returned '$code'"; return 1; }
  echo "gateway $pinned, Ollama 200"
}

check_hermes_services() {
  have wsl.exe || { echo "not a Windows host"; return 77; }
  local out bad=""
  for s in hermes-dashboard autossh-cdp tinyproxy; do
    out=$(wsl_ "systemctl is-active $s" | tail -1)
    [ "$out" = active ] || bad="$bad $s=$out"
  done
  [ -z "$bad" ] || { echo "inactive:$bad"; return 1; }
  echo "dashboard, autossh-cdp, tinyproxy all active"
}

# Filesystem confinement (WSL2-HANDOFF §11b). Without `metadata` the 9p mounts ignore
# Unix permissions entirely and the caged hermes uid can delete anything on C:.
check_hermes_fs_confined() {
  have wsl.exe || { echo "not a Windows host"; return 77; }
  wsl_ 'mount | grep -q "on /mnt/c .*metadata"' >/dev/null 2>&1 \
    || { echo "/mnt/c has no metadata option — hermes uid can WRITE the Windows profile"; return 1; }
  echo "/mnt/c enforces Unix permissions (hermes is read-only)"
}

# Local source patches are stashed silently by `hermes update`, so they need checking
# after every update. Both --check scripts read files under the hermes uid's home and
# need root; without it they misreport as "not found".
check_hermes_patches() {
  have wsl.exe || { echo "not a Windows host"; return 77; }
  echo "needs root — run: sudo python3 /mnt/www/local-ai-setup/scripts/hermes-context-floor/install.py --check"
  return 77
}

# ==================================================================================
# Runner
# ==================================================================================
VERBOSE=0; FILTER=""
for a in "$@"; do
  case $a in -v|--verbose) VERBOSE=1 ;; *) FILTER=$a ;;
  esac
done

P=0; F=0; S=0
for fn in $(declare -F | awk '{print $3}' | grep '^check_' | sort); do
  name=${fn#check_}
  case $name in *"$FILTER"*) ;; *) continue ;; esac
  detail=$("$fn"); rc=$?
  case $rc in
    0)  P=$((P+1)); [ "$VERBOSE" = 1 ] && printf '  \033[32mPASS\033[0m  %-24s %s\n' "$name" "$detail" \
                                       || printf '  \033[32mPASS\033[0m  %s\n' "$name" ;;
    77) S=$((S+1)); printf '  \033[33mSKIP\033[0m  %-24s %s\n' "$name" "$detail" ;;
    *)  F=$((F+1)); printf '  \033[31mFAIL\033[0m  %-24s %s\n' "$name" "$detail" ;;
  esac
done

printf '\n  %d passed, %d failed, %d skipped\n' "$P" "$F" "$S"
[ "$F" -eq 0 ]
