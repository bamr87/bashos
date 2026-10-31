#!/usr/bin/env bash
# os/boot.sh — the one-line install, Omarchy-style, on a fresh Debian 13 machine:
#
#   curl -fsSL https://raw.githubusercontent.com/bamr87/bashos/main/os/boot.sh | bash
#
# Clones bashOS into /opt/bashos (root-owned: the platform is not writable by the user's
# processes) and runs its installer as you, with sudo for the system phases. Read it first.
#   BASHOS_REF=<branch|tag>   what to install (default: main)
#   BASHOS_OS_PATH=<dir>      where (default: /opt/bashos)
set -Eeuo pipefail

ref=${BASHOS_REF:-main}
path=${BASHOS_OS_PATH:-/opt/bashos}
repo=${BASHOS_OS_REPO:-https://github.com/bamr87/bashos}

cat <<'LOGO'
 _             _    ___  ____
| |__  __ _ __| |_ / _ \/ ___|
| '_ \/ _` (_-< ' \ (_) \___ \
|_.__/\__,_/__/_||_\___/|____/   the OS layer
LOGO

[[ $(id -u) -ne 0 ]] || { echo "boot.sh: run as the machine's user (sudo is used where needed)" >&2; exit 1; }
command -v git >/dev/null || sudo apt-get install -y --no-install-recommends git ca-certificates
if [[ -d $path/.git ]]; then
  sudo git -C "$path" fetch --quiet origin "$ref"
  sudo git -C "$path" checkout --quiet FETCH_HEAD
else
  sudo git clone --quiet --branch "$ref" "$repo" "$path"
fi
# A pipe is not a terminal: give the installer the real one so sudo can ask.
exec "$path/os/install.sh" "$@" </dev/tty
