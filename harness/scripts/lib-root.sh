#!/usr/bin/env bash
# lib-root.sh — shared workspace-root detection for the harness scripts.
#
# Source it, don't execute it:
#   . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-root.sh"
#   detect_root                # assigns SYSTEM and WWW
#
# Resolution order: harness/.env override (WORKSPACE_ROOT) -> per-OS default.
# Extracted verbatim from session-todo.sh (2026-09-29) — see
# .plans/harness-tool-notebook-split.md. This is an extraction, not a redesign;
# the per-OS case below must stay byte-for-byte what it always was.
set -u

# .env lives at harness/.env, one directory up from this file — resolved from
# ${BASH_SOURCE[0]}, NEVER from a detected workspace root. A script has to be
# able to find its own neighbour before it has found anything else; getting
# this backwards was Finding 2 of the clone test (a script could not find a
# file sitting right next to it) and it must not come back.
LIB_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_ROOT_ENV="$LIB_ROOT_DIR/../.env"
if [ -f "$LIB_ROOT_ENV" ]; then
  set -a
  . "$LIB_ROOT_ENV"
  set +a
fi

# One tree, three mount points: ~/www on the Mac, /mnt/www in WSL2, M:\ (= /m under
# Git Bash) on the PC. Pick by system, then VERIFY — a digest that prints an empty
# list because it looked in the wrong place is indistinguishable from "nothing is
# open", which is the one failure that makes this tool actively misleading.
#
# WSL reports "Linux" from uname, so it must be tested before plain Linux. The
# /proc/version marker is the reliable tell; $WSL_DISTRO_NAME is unset under some
# service managers and sudo's env_reset.
detect_root() {   # assigns SYSTEM and WWW; never call it in a subshell
  # An explicit WORKSPACE_ROOT (set directly, or via harness/.env above) wins
  # over every per-OS guess — checked first, so the case below never runs.
  if [ -n "${WORKSPACE_ROOT:-}" ]; then
    SYSTEM="explicit (WORKSPACE_ROOT)"; WWW=$WORKSPACE_ROOT; return
  fi
  case "$(uname -s)" in
    Darwin)                 SYSTEM=Mac;      WWW=$HOME/www ;;
    MINGW*|MSYS*|CYGWIN*)   SYSTEM=Windows;  WWW=/m ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        SYSTEM=WSL2;        WWW=/mnt/www
      else
        SYSTEM=Linux;       WWW=$HOME/www
      fi ;;
    *)                      SYSTEM=$(uname -s); WWW=$HOME/www ;;
  esac
}
