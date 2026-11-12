#!/usr/bin/env bash
# Run the dashboard tests in a container (no node_modules on the host). node_modules lives in a
# named volume, built once with the same toolchain the Dockerfile uses (better-sqlite3 compiles).
# Usage: bash scripts/test-in-docker.sh [vitest args]
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD":/app -v obs-test-nm:/app/node_modules -w /app node:22-bookworm-slim bash -c '
  set -e
  if [ ! -f node_modules/.ok ] || ! cmp -s package-lock.json node_modules/.ok; then
    apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 make g++ >/dev/null
    npm ci --no-audit --no-fund
    cp package-lock.json node_modules/.ok
  fi
  npx tsc --noEmit -p .
  npx vitest run "$@"
' _ "$@"
