#!/usr/bin/env bash
# os/install.sh — turn a Debian 13 machine into a bashOS machine. Idempotent: run it again to
# repair or to apply an update; --dry-run prints every change and makes none.
#
# The phases run in order (os/install/<phase>.sh); each is `system` (root, through sudo) or
# `user` (the person the machine is for, never root):
#
#   preflight  system  the machine is one this layer supports; nothing changes
#   packages   system  the Debian packages in os/packages/*.list that are missing
#   runtime    system  the layer at $BASHOS_OS_PATH (/opt/bashos), its .venv, the engine CLIs,
#                      the commands on /usr/local/bin
#   system     system  /etc/bashos, never-sleep, the systemd units, tty1 autologin, linger
#   console    user    tty1 and ssh logins attach the shared tmux console; the tmux defaults
#   harness    user    the bamr87 hub checkout and the Harness Console service
#   finish     user    the migration baseline and the summary
#
# Modes: the default runs every phase on this machine. --image runs the system phases inside an
# image build's chroot (the user phases run at first boot, from bashos-provision). --user-only
# runs the user phases (what bashos-provision calls once the user exists).
set -Eeuo pipefail

OS_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib.sh
source "$OS_SRC/os/lib.sh"

usage() {
  cat <<'EOF'
usage: bashos os install [options]

  -n, --dry-run      print every change, make none
      --image        inside an image build (system phases only; nothing is started)
      --user-only    only the user phases (console, harness, finish)
      --system-only  only the system phases
      --user NAME    the machine's user (default: whoever ran sudo, else you)
      --only PHASE   run one phase (repeatable)
      --skip PHASE   skip a phase (repeatable), e.g. --skip packages
      --root DIR     a fake root: system paths land under DIR, nothing privileged runs
  -h, --help
EOF
}

PHASES=(preflight packages runtime system console harness finish)
declare -A SCOPE=([preflight]=system [packages]=system [runtime]=system [system]=system
  [console]=user [harness]=user [finish]=user)
want_system=1 want_user=1
only=() skip=()

while (($#)); do
  case $1 in
    -n | --dry-run) export BASHOS_OS_DRY_RUN=1 ;;
    --image) export BASHOS_OS_IMAGE=1 want_user=0 ;;
    --user-only) want_system=0 ;;
    --system-only) want_user=0 ;;
    --user) export BASHOS_USER=${2:?--user needs a name}; shift ;;
    --only) only+=("${2:?--only needs a phase}"); shift ;;
    --skip) skip+=("${2:?--skip needs a phase}"); shift ;;
    --root) export BASHOS_OS_ROOT=${2:?--root needs a directory}; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done
# Re-read the switches the flags just set (lib.sh read them at source time).
BASHOS_OS_DRY_RUN=${BASHOS_OS_DRY_RUN:-0} BASHOS_OS_IMAGE=${BASHOS_OS_IMAGE:-0}
BASHOS_OS_ROOT=${BASHOS_OS_ROOT:-}

for p in "${only[@]}" "${skip[@]}"; do
  [[ -n ${SCOPE[$p]:-} ]] || os_die "unknown phase '$p' (phases: ${PHASES[*]})"
done

OS_USER=$(os_user)
OS_HOME=$(os_user_home "$OS_USER")
export OS_USER OS_HOME BASHOS_USER_HOME="$OS_HOME"
os_conf_load

if ((want_user)) && os_is_root && [[ $OS_USER == root ]] && ! os_fake_root; then
  os_die "the user phases are never root's: run as the machine's user, or pass --user NAME"
fi

selected() {
  local phase=$1 p
  for p in "${skip[@]}"; do [[ $p == "$phase" ]] && return 1; done
  if ((${#only[@]})); then
    for p in "${only[@]}"; do [[ $p == "$phase" ]] && return 0; done
    return 1
  fi
  case ${SCOPE[$phase]} in
    system) ((want_system)) ;;
    user) ((want_user)) ;;
  esac
}

mode="this machine"
os_image && mode="an image build"
os_fake_root && mode="fake root $BASHOS_OS_ROOT"
os_dry && mode="$mode, dry run"
printf '%sbashOS%s os install · %s · user %s · layer %s\n' "$_os_b" "$_os_0" "$mode" "$OS_USER" "$BASHOS_OS_PATH"

for phase in "${PHASES[@]}"; do
  selected "$phase" || continue
  # shellcheck source=/dev/null
  source "$OS_DIR/install/$phase.sh"
  "phase_$phase"
done

os_dry && printf '\n%sdry run: nothing was changed%s\n' "$_os_b" "$_os_0"
exit 0
