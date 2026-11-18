#!/usr/bin/env bash
# os/amrchy/sync.sh — amrchy/ is a squashed git subtree of bamr87/amrchy, the Omarchy fork that is
# bashOS's framework (ADR 0005). bamr87/amrchy stays the fork of record: its own upstream sync
# brings Omarchy in there, and this keeps the copy here in step with it, both ways.
set -Eeuo pipefail

OS_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"

REPO=${BASHOS_AMRCHY_REPO:-https://github.com/bamr87/amrchy.git}
PREFIX=amrchy

usage() {
  cat <<'EOF'
usage: bashos os amrchy <command>

  status         the bamr87/amrchy commit amrchy/ holds, the bashos commits that changed it since,
                 and where bamr87/amrchy's main is now
  pull [REF]     bring bamr87/amrchy's main (or REF) into amrchy/ as one squashed commit
  push BRANCH    send the bashos commits that changed amrchy/ to bamr87/amrchy as BRANCH, to open
                 a pull request there (never main)
EOF
}

g() { git -C "$OS_SRC" "$@"; }

# The squash commit `git subtree` last made, and the bamr87/amrchy commit it holds.
last_squash() { g log -1 --format=%H --grep="^git-subtree-dir: $PREFIX\$"; }
vendored() { g log -1 --format=%B "$(last_squash)" | sed -n 's/^git-subtree-split: //p'; }

clean_tree() {
  [[ -z $(g status --porcelain --untracked-files=no) ]] || os_die "commit or set aside your changes first (git subtree needs a clean tree)"
}

cmd_status() {
  local squash held remote changed
  squash=$(last_squash)
  [[ -n $squash ]] || os_die "$PREFIX/ is not a git subtree here"
  held=$(vendored)
  printf 'amrchy/  holds bamr87/amrchy %s (squashed in %s)\n' "${held:0:12}" "${squash:0:12}"
  changed=$(g log --no-merges --format='  %h %s' "$squash..HEAD" -- "$PREFIX")
  if [[ -n $changed ]]; then
    printf 'changed here since (bashos os amrchy push BRANCH sends these):\n%s\n' "$changed"
  else
    printf 'changed here since: nothing\n'
  fi
  if remote=$(git ls-remote "$REPO" refs/heads/main 2>/dev/null | cut -f1) && [[ -n $remote ]]; then
    if [[ $remote == "$held" ]]; then
      printf 'bamr87/amrchy main: %s, the same\n' "${remote:0:12}"
    elif g cat-file -e "$remote^{commit}" 2>/dev/null && g merge-base --is-ancestor "$remote" "$held" 2>/dev/null; then
      printf 'bamr87/amrchy main: %s, behind what amrchy/ holds (push a branch and merge it there)\n' "${remote:0:12}"
    else
      printf 'bamr87/amrchy main: %s (bashos os amrchy pull brings it in)\n' "${remote:0:12}"
    fi
  else
    os_warn "could not reach $REPO"
  fi
}

cmd_pull() {
  local ref=${1:-main}
  clean_tree
  g subtree pull --prefix="$PREFIX" --squash -m "chore(amrchy): pull bamr87/amrchy $ref" "$REPO" "$ref"
  os_ok "amrchy/ now holds bamr87/amrchy $(vendored | cut -c1-12) — run make test and make lint"
}

cmd_push() {
  local branch=${1:-}
  [[ -n $branch ]] || os_die "usage: bashos os amrchy push BRANCH"
  [[ $branch != main ]] || os_die "never main: push a branch and open a pull request on bamr87/amrchy"
  g subtree push --prefix="$PREFIX" "$REPO" "$branch"
  os_ok "pushed to bamr87/amrchy $branch — open the pull request there"
}

case ${1:-} in
  status) cmd_status ;;
  pull) shift; cmd_pull "$@" ;;
  push) shift; cmd_push "$@" ;;
  -h | --help | help | "") usage ;;
  *) usage >&2; exit 2 ;;
esac
