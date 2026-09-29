#!/usr/bin/env bash
# context-index.sh — generate the mechanical half of the context tree.
#
# Two outputs, both derived, neither ever hand-edited:
#
#   1. A delimited block in every folder's CONTEXT.md listing that folder's
#      leaves. Hand-maintained index lines rotted twice in career/ (51 of ~60
#      leaves unreachable on 2026-09-29, after a sweep on 2026-09-04 fixed the
#      same thing). A generated block cannot rot, so the orphan check in
#      health-check.sh stops being a nag and becomes a regression test.
#   2. A LEDGER.md per folder, derived from git history: which commit touched
#      which leaf, when, and by how much. Materialised rather than recomputed
#      because git only runs on the Mac (SMB cannot write objects, see
#      jobhunt/docs/SMB-GIT.md) while the PC and Hermes can only read the share.
#      A file they can grep is the only provenance they get.
#
# What this script deliberately does NOT do: infer intent. A diff shows added
# and removed lines, never "superseded" vs "corrected". The why belongs in the
# leaf, as an append-only block with a stable {#anchor}; the ledger only says
# which commit changed what. A semantic verb here would have to be hand-written,
# and hand-written is the rot vector this script exists to remove.
#
# Mac only: git lives there, and the orphan check measured 47s over SMB against
# 1s locally. Elsewhere it prints a notice and exits 0.
#
# Usage:
#   context-index.sh <context-repo-root>            # generate
#   context-index.sh <context-repo-root> --check    # drift only, no writes
#   context-index.sh --selftest                     # synthetic fixtures
set -euo pipefail

GEN_OPEN='<!-- generated: leaves -->'
GEN_CLOSE='<!-- /generated -->'
SUMMARY_WIDTH=${SUMMARY_WIDTH:-110}

die() { echo "context-index: $*" >&2; exit 1; }

# The leaf's H1, whitespace collapsed, truncated at a fixed width. No dates, no
# locale-dependent anything: identical input must produce identical bytes or the
# drift check flaps forever.
summary_of() {
  LC_ALL=C awk -v w="$SUMMARY_WIDTH" '
    /^# / { sub(/^# /, ""); gsub(/[[:space:]]+/, " "); gsub(/^ | $/, "")
            if (length($0) > w) $0 = substr($0, 1, w - 1) "…"
            print; exit }
  ' "$1"
}

# Every .md in the folder except the three generated/index files, sorted by
# filename under LC_ALL=C so two machines agree on order.
leaves_in() {
  LC_ALL=C find "$1" -maxdepth 1 -name '*.md' \
    ! -name CONTEXT.md ! -name COMPLETED.md ! -name LEDGER.md -print |
    LC_ALL=C sort
}

# Rewrite (or append) the generated block. Everything outside the delimiters is
# human-curated and is never touched.
write_block() {
  idx=$1 bodyfile=$2
  [ -r "$idx" ] || die "no index at $idx"
  # No awk -v for the body: a multi-line value breaks awk's string parser. Line
  # numbers plus head/tail keeps it to three reads and no quoting hazards.
  o=$(LC_ALL=C grep -nxF "$GEN_OPEN" "$idx" | head -1 | cut -d: -f1 || true)
  c=$(LC_ALL=C grep -nxF "$GEN_CLOSE" "$idx" | head -1 | cut -d: -f1 || true)
  if [ -n "$o" ] && [ -n "$c" ] && [ "$c" -gt "$o" ]; then
    { head -n "$o" "$idx"; cat "$bodyfile"; tail -n "+$c" "$idx"; } > "$idx.tmp"
  else
    { cat "$idx"; printf '\n%s\n' "$GEN_OPEN"; cat "$bodyfile"; printf '%s\n' "$GEN_CLOSE"; } > "$idx.tmp"
  fi
  mv "$idx.tmp" "$idx"
}

# The generated block is a SAFETY NET, not the whole index: a leaf the human already
# linked in the curated prose is left alone, so the two halves never list the same
# file twice. Still deterministic — the exclusion set is read from the file itself,
# outside the delimiters.
build_body() {
  d=$1 out=$2
  : > "$out"
  curated=$(LC_ALL=C awk -v gopen="$GEN_OPEN" -v gclose="$GEN_CLOSE" \
    '$0 == gopen { inb = 1; next } $0 == gclose { inb = 0; next } !inb { print }' "$d/CONTEXT.md" 2>/dev/null)
  [ -f "$d/LEDGER.md" ] && ! printf '%s' "$curated" | grep -qF 'LEDGER.md' &&
    printf -- '- [LEDGER.md](LEDGER.md) — generated change ledger for this folder (date | commit | status | file | delta)\n' >> "$out"
  leaves_in "$d" | while IFS= read -r f; do
    b=${f##*/}
    case $curated in *"$b"*) continue ;; esac
    s=$(summary_of "$f")
    [ -n "$s" ] || s="(no H1)"
    printf -- '- [%s](%s) — %s\n' "$b" "$b" "$s" >> "$out"
  done
}

# One git pass for statuses and one for line counts over the whole tree, joined
# in awk by (sha, path). Combining --name-status with --numstat does not work:
# git emits only the former (verified 2026-09-29). Per-folder git calls would be
# 20 spawns for the same data.
# A ledger is generated BEFORE the commit that carries it, so it can never contain
# its own commit and always trails HEAD by one. Comparing it to a fresh HEAD-based
# build would therefore report drift forever. So each ledger records the rev it was
# built at, and --check reproduces it AS OF that rev: a difference then means someone
# edited the generated half by hand, which is the only thing worth failing on.
build_ledgers() {
  root=$1 outdir=$2 rev=${3:-HEAD}
  ( cd "$root" && git log --format='C|%h|%ad' --date=short --name-status "$rev" -- context ) > "$outdir/.status"
  ( cd "$root" && git log --format='C|%h' --numstat "$rev" -- context ) > "$outdir/.numstat"
  # Single-pass join: statuses carry the date, numstat carries the deltas.
  LC_ALL=C awk -F'\t' -v outdir="$outdir" '
    NR == FNR {
      if ($0 ~ /^C\|/) { split($0, c, "|"); sha = c[2]; date = c[3]; next }
      if (NF >= 2) { key = sha "\t" $2; status[key] = $1; when[key] = date; order[++n] = key }
      next
    }
    {
      if ($0 ~ /^C\|/) { split($0, c, "|"); sha2 = c[2]; next }
      if (NF >= 3) { key = sha2 "\t" $3; a[key] = $1; d[key] = $2 }
    }
    END {
      for (i = n; i >= 1; i--) {
        key = order[i]
        split(key, k, "\t"); sha = k[1]; path = k[2]
        if (path !~ /\.md$/) continue
        base = path; sub(/.*\//, "", base)
        if (base == "LEDGER.md") continue
        dir = path; sub(/\/[^\/]*$/, "", dir)
        aa = (key in a) ? a[key] : "0"; dd = (key in d) ? d[key] : "0"
        # git prints "-" for a file it treats as binary; it genuinely cannot count
        # those lines, so say so rather than inventing a number.
        if (aa == "-") aa = "?"; if (dd == "-") dd = "?"
        printf "%s | %s | %s | %s | +%s -%s\n", when[key], sha, status[key], base, aa, dd \
          >> (outdir "/" dir "/LEDGER.md.new")
      }
    }
  ' "$outdir/.status" "$outdir/.numstat"
  rm -f "$outdir/.status" "$outdir/.numstat"
  full=$( cd "$root" && git rev-parse "$rev" )
  for nf in $(LC_ALL=C find "$outdir" -name 'LEDGER.md.new' | LC_ALL=C sort); do
    { printf '# generated-at: %s\n' "$full"; cat "$nf"; } > "$nf.h" && mv "$nf.h" "$nf"
  done
}

generate() {
  root=$1 check=${2:-}
  t="$root/context"
  [ -d "$t" ] || die "no context tree at $t"
  folders=$(LC_ALL=C find "$t" -name CONTEXT.md | sed 's|/[^/]*$||' | LC_ALL=C sort)
  [ -n "$folders" ] || die "found 0 index files — nothing was scanned"
  drift=0 n=0

  # Ledgers, written into the tree itself (or compared, under --check).
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  if [ -n "$check" ]; then
    # Build once per DISTINCT watermark, with every folder's directory present: one
    # awk pass writes all folders' ledgers, so a missing directory makes the redirect
    # fail for the others (caught by the selftest, which has two folders).
    wms=""
    for d in $folders; do
      led="$d/LEDGER.md"; [ -f "$led" ] || continue
      wm=$(LC_ALL=C sed -n '1s/^# generated-at: //p' "$led")
      [ -n "$wm" ] || { echo "ledger has no watermark: ${d#"$t"/}"; drift=1; continue; }
      case " $wms " in *" $wm "*) ;; *) wms="$wms $wm" ;; esac
    done
    for wm in $wms; do
      sub="$tmp/$wm"
      for d in $folders; do mkdir -p "$sub/${d#"$root"/}"; done
      if ! build_ledgers "$root" "$sub" "$wm" 2>/dev/null; then
        echo "ledger watermark unknown to git: $wm"; drift=1; continue
      fi
      for d in $folders; do
        led="$d/LEDGER.md"; [ -f "$led" ] || continue
        [ "$(LC_ALL=C sed -n '1s/^# generated-at: //p' "$led")" = "$wm" ] || continue
        new="$sub/${d#"$root"/}/LEDGER.md.new"
        [ -f "$new" ] || continue
        cmp -s "$new" "$led" || { echo "hand-edited ledger: ${d#"$t"/}"; drift=1; }
      done
    done
  else
    for d in $folders; do mkdir -p "$tmp/${d#"$root"/}"; done
    build_ledgers "$root" "$tmp"
    for d in $folders; do
      new="$tmp/${d#"$root"/}/LEDGER.md.new"
      [ -f "$new" ] || continue
      cp "$new" "$d/LEDGER.md"
    done
  fi

  # Index blocks AFTER the ledgers, so LEDGER.md already exists when the block that
  # points at it is built. The other order needs two runs to settle.
  for d in $folders; do
    n=$((n+1))
    bf=$(mktemp); build_body "$d" "$bf"
    if [ -n "$check" ]; then
      cf=$(mktemp)
      # `close` is a reserved awk function name and cannot be a variable.
      LC_ALL=C awk -v gopen="$GEN_OPEN" -v gclose="$GEN_CLOSE" \
        '$0 == gopen { inb = 1; next } $0 == gclose { inb = 0; next } inb { print }' "$d/CONTEXT.md" > "$cf"
      cmp -s "$bf" "$cf" || { echo "stale index: ${d#"$t"/}"; drift=1; }
      rm -f "$cf"
    else
      write_block "$d/CONTEXT.md" "$bf"
    fi
    rm -f "$bf"
  done

  [ "$n" -gt 0 ] || die "scanned nothing"
  if [ -n "$check" ]; then
    [ "$drift" = 0 ] || return 1
    echo "$n folders, generated blocks and ledgers current"
  else
    echo "$n folders regenerated"
  fi
}

selftest() {
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  ok() { echo "  ok   $1"; }
  bad() { echo "  FAIL $1"; exit 1; }

  mkdir -p "$t/context/alpha" "$t/context/beta"
  ( cd "$t" && git init -q && git config user.email t@e && git config user.name t )
  printf '# Alpha\n\n## Start here\n\n- hand-written prose stays\n' > "$t/context/alpha/CONTEXT.md"
  printf '# Beta\n' > "$t/context/beta/CONTEXT.md"
  printf '# Zeta leaf title\n\nbody\n' > "$t/context/alpha/zeta-1-20260101.md"
  printf '# Able leaf title\n\nbody\n' > "$t/context/alpha/able-2-20260102.md"
  ( cd "$t" && git add -A && git commit -qm one )

  "$0" "$t" >/dev/null

  grep -qF 'hand-written prose stays' "$t/context/alpha/CONTEXT.md" || bad "human prose was clobbered"
  ok "human prose outside the delimiters survives"

  LC_ALL=C awk -v o="$GEN_OPEN" -v c="$GEN_CLOSE" '$0==o{i=1;next} $0==c{i=0;next} i' \
    "$t/context/alpha/CONTEXT.md" > "$t/blk"
  head -1 "$t/blk" | grep -qF '[LEDGER.md](LEDGER.md)' ||
    bad "the ledger pointer should lead the block: $(head -1 "$t/blk")"
  [ "$(sed -n 2p "$t/blk")" = '- [able-2-20260102.md](able-2-20260102.md) — Able leaf title' ] ||
    bad "leaves are not sorted by filename, or the summary is wrong: $(sed -n 2p "$t/blk")"
  [ "$(grep -c . "$t/blk")" = 3 ] || bad "expected ledger + 2 leaf lines, got $(grep -c . "$t/blk")"
  ok "ledger pointer first, then leaves sorted with the H1 as summary"

  printf -- '- [zeta-1-20260101.md](zeta-1-20260101.md) — curated by hand\n' >> "$t/context/beta/CONTEXT.md"
  printf '# Zeta in beta\n' > "$t/context/beta/zeta-1-20260101.md"
  "$0" "$t" >/dev/null
  [ "$(grep -c 'zeta-1-20260101.md' "$t/context/beta/CONTEXT.md")" = 1 ] ||
    bad "a hand-curated leaf was duplicated by the generated block"
  ok "curated pointers are not duplicated"

  cp "$t/context/alpha/CONTEXT.md" "$t/before"
  "$0" "$t" >/dev/null
  cmp -s "$t/before" "$t/context/alpha/CONTEXT.md" || bad "second run changed the file (not idempotent)"
  ok "idempotent"

  "$0" "$t" --check >/dev/null || bad "--check reported drift on a freshly generated tree"
  ok "--check is green when current"

  printf '# New leaf\n' > "$t/context/beta/new-3-20260103.md"
  ( cd "$t" && git add -A && git commit -qm two )
  if "$0" "$t" --check >/dev/null 2>&1; then bad "--check missed an unindexed new leaf"; fi
  ok "--check catches an unindexed leaf"

  "$0" "$t" >/dev/null
  grep -q '^2[0-9-]* | [0-9a-f]\{7,\} | [AMDR] | zeta-1-20260101.md | +[0-9]* -[0-9]*$' \
    "$t/context/alpha/LEDGER.md" || bad "ledger line grammar wrong: $(head -1 "$t/context/alpha/LEDGER.md")"
  ok "ledger lines carry date, sha, status, file, deltas"

  grep -q 'LEDGER.md' "$t/context/alpha/LEDGER.md" && bad "ledger recorded itself — infinite growth"
  ok "ledger excludes itself"

  head -1 "$t/context/alpha/LEDGER.md" | grep -q '^# generated-at: [0-9a-f]\{40\}$' ||
    bad "ledger carries no watermark"
  ok "ledger records the rev it was generated at"

  ( cd "$t" && git add -A && git commit -qm three )
  "$0" "$t" --check >/dev/null 2>&1 ||
    bad "a new commit made --check red — the ledger always trails HEAD by one and that is not drift"
  ok "--check survives history moving on"

  printf 'hand-written rubbish\n' >> "$t/context/alpha/LEDGER.md"
  if "$0" "$t" --check >/dev/null 2>&1; then bad "--check missed a hand-edited ledger"; fi
  ok "--check catches a hand-edited ledger"

  empty=$(mktemp -d)
  if "$0" "$empty" >/dev/null 2>&1; then bad "scanning nothing exited 0"; fi
  rm -rf "$empty"
  ok "fails loudly when it scans nothing"

  echo "selftest passed"
}

case ${1:-} in
  --selftest) selftest ;;
  "") die "usage: context-index.sh <context-repo-root> [--check] | --selftest" ;;
  *)
    case $(uname -s) in
      Darwin) ;;
      *) echo "context-index: generation runs on the Mac only (git and local disk live there); nothing done"; exit 0 ;;
    esac
    generate "$1" "${2:-}"
    ;;
esac
