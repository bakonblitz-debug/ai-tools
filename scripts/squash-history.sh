#!/usr/bin/env bash
# squash-history.sh — rewrite a branch into fewer commits with new messages.
# Usage: squash-history.sh <repo> <groups-dir>
#        squash-history.sh --selftest
#
# <groups-dir> holds one message file per new commit, named NN-<sha>.txt, where
# <sha> is the LAST original commit of the group. Files are applied in name order.
#
# Each new commit reuses the exact tree of its group's last original commit, so no
# content can change and nothing can conflict. Author and dates come from that
# commit too. The old tip is kept at backup/pre-squash-<date>.
#
# Limit: a group is a contiguous run of original commits. Merges are flattened.
set -eu

squash() {
  repo="$1"; groups="$2"
  cd "$repo"
  branch="$(git branch --show-current)"
  [ -n "$branch" ] || { echo "squash-history: detached HEAD, refusing" >&2; return 1; }
  old="$(git rev-parse HEAD)"

  parent=""; prev=""; last=""
  for f in "$groups"/*.txt; do
    [ -s "$f" ] || { echo "squash-history: empty message $f" >&2; return 1; }
    sha="$(basename "$f" .txt)"; sha="${sha#*-}"
    last="$(git rev-parse --verify --quiet "$sha^{commit}")" \
      || { echo "squash-history: unknown commit in $f" >&2; return 1; }
    # groups must walk forward through the original history, in order
    git merge-base --is-ancestor "$last" "$old" \
      || { echo "squash-history: $sha is not on $branch" >&2; return 1; }
    if [ -n "$prev" ]; then
      [ "$prev" != "$last" ] && git merge-base --is-ancestor "$prev" "$last" \
        || { echo "squash-history: $f is out of order" >&2; return 1; }
    fi
    prev="$last"
    parent="$(
      GIT_AUTHOR_NAME="$(git log -1 --format=%an "$last")" \
      GIT_AUTHOR_EMAIL="$(git log -1 --format=%ae "$last")" \
      GIT_AUTHOR_DATE="$(git log -1 --format=%aI "$last")" \
      GIT_COMMITTER_DATE="$(git log -1 --format=%cI "$last")" \
      git commit-tree "$last^{tree}" ${parent:+-p "$parent"} -F "$f"
    )"
  done

  [ "$last" = "$old" ] \
    || { echo "squash-history: last group must end at HEAD ($old)" >&2; return 1; }
  [ "$(git rev-parse "$parent^{tree}")" = "$(git rev-parse "$old^{tree}")" ] \
    || { echo "squash-history: final tree differs, refusing" >&2; return 1; }

  backup="backup/pre-squash-$(date +%Y%m%d)"
  git branch "$backup" "$old" 2>/dev/null \
    || { echo "squash-history: $backup already exists, refusing" >&2; return 1; }
  git update-ref -m "squash-history" "refs/heads/$branch" "$parent" "$old"
  echo "$branch: $(git rev-list --count "$old") -> $(git rev-list --count "$parent") commits, old tip at $backup"
}

selftest() {
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  git init -q "$tmp/r"; mkdir "$tmp/g"
  (
    cd "$tmp/r"
    git config user.name t; git config user.email t@t
    for i in 1 2 3 4 5; do echo "$i" > "f$i"; git add .; git commit -qm "c$i"; done
  )
  tip="$(git -C "$tmp/r" rev-parse HEAD)"
  echo "first"  > "$tmp/g/01-$(git -C "$tmp/r" rev-parse --short HEAD~3).txt"
  echo "second" > "$tmp/g/02-$(git -C "$tmp/r" rev-parse --short HEAD).txt"
  ( squash "$tmp/r" "$tmp/g" >/dev/null )
  cd "$tmp/r"
  [ "$(git rev-list --count HEAD)" = 2 ]                                  || { echo "FAIL count"; exit 1; }
  [ "$(git rev-parse HEAD^{tree})" = "$(git rev-parse "$tip^{tree}")" ]   || { echo "FAIL tree"; exit 1; }
  [ "$(git log --format=%s | tr '\n' ' ')" = "second first " ]            || { echo "FAIL messages"; exit 1; }
  [ -z "$(git status --porcelain)" ]                                      || { echo "FAIL dirty"; exit 1; }
  # a group list that stops short of HEAD must be refused and leave the branch alone
  git checkout -q -b short "$tip"; rm "$tmp/g"/02-*.txt
  if ( squash "$tmp/r" "$tmp/g" >/dev/null 2>&1 ); then echo "FAIL short list accepted"; exit 1; fi
  [ "$(git rev-parse HEAD)" = "$tip" ]                                    || { echo "FAIL branch moved"; exit 1; }
  echo "selftest ok"
}

case "${1:-}" in
  --selftest) selftest ;;
  "") echo "usage: squash-history.sh <repo> <groups-dir> | --selftest" >&2; exit 2 ;;
  *) squash "$1" "${2:?groups-dir}" ;;
esac
