#!/usr/bin/env bash
# Run a command on the Mac, inside a workspace project.
#
# Usage:
#   on-mac.sh <project> <command...>     # run in ~/www/projects/<project>
#   on-mac.sh --repo <name> <command...> # run in ~/www/<name>, for top-level repos
#   on-mac.sh --root <command...>        # run in ~/www itself
#
# Examples:
#   on-mac.sh notary bash run-conformance.sh
#   on-mac.sh notary git commit -m "a message with spaces"
#   on-mac.sh --repo cve-watch uv run pytest -q
#
# Arguments are passed as argv, not as shell text, so quoting survives and there
# is no accidental expansion. Pipes and redirects therefore need an explicit
# shell:
#
#   on-mac.sh notary bash -c 'ls spec | head -3'
#
# Exit codes propagate: the remote command's status is this script's status.
# A missing project directory exits 66.
#
# WHY THIS EXISTS
#
# The workspace lives on the Mac and is exposed to the PC over SMB as M:. Reading
# and editing through that mount is fine; *running* things through it is not:
#
#   - Docker Desktop on Windows cannot bind-mount M:. The mapped drive mounts
#     EMPTY and silently (no error, just an empty directory inside the container),
#     the UNC path is rejected outright, and Docker's own WSL distro cannot see
#     another distro's CIFS mount at /mnt/www.
#   - Git object writes fail over the SMB mount, so commits must happen Mac-side.
#
# On the Mac, ~/www is local disk, so Docker and git both behave normally. This
# script is the one obvious way to get there, so neither constraint has to be
# rediscovered.
#
# Requires `Host mac` in ~/.ssh/config.

set -uo pipefail

HOST="${ON_MAC_HOST:-mac}"
WWW="${ON_MAC_WWW:-\$HOME/www}"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-1}"
}

[ $# -ge 1 ] || usage 1

case "$1" in
  -h|--help)
    usage 0
    ;;
  --root)
    shift
    DIR="$WWW"
    ;;
  --repo)
    shift
    [ $# -ge 1 ] || usage 1
    DIR="$WWW/$1"
    shift
    ;;
  *)
    DIR="$WWW/projects/$1"
    shift
    ;;
esac

[ $# -ge 1 ] || usage 1

# Quote each argument so it survives the trip through the remote shell intact —
# paths with spaces, quoted commit messages, globs meant for the Mac, and so on.
REMOTE_CMD=""
for arg in "$@"; do
  REMOTE_CMD+=" $(printf '%q' "$arg")"
done

# -t only when we have a terminal, so piping and capturing output stay clean.
SSH_FLAGS=()
[ -t 1 ] && SSH_FLAGS+=(-t)

# Homebrew is NOT on the PATH for a non-interactive ssh session, not even under
# `bash -lc` — the shellenv line lives in a profile that only interactive shells
# read. Without this, `gh`, and anything else brew-installed, reports "command not
# found" while the binary is sitting right there. Cost an incorrect "gh is not
# installed anywhere" conclusion on 2026-08-30 before the cause was spotted.
BREW_PATH="${ON_MAC_BREW_PATH:-/opt/homebrew/bin:/opt/homebrew/sbin}"

exec ssh "${SSH_FLAGS[@]}" "$HOST" \
  "export PATH=$BREW_PATH:\$PATH; cd $DIR 2>/dev/null || { echo \"on-mac: no such directory: $DIR\" >&2; exit 66; }; exec bash -lc$(printf ' %q' "$REMOTE_CMD")"
