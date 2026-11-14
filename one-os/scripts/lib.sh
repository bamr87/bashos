# shellcheck shell=bash
# Shared helpers. Source this; don't execute it.
# Every privileged operation in the repo goes through `priv` so it's easy to audit.

set -euo pipefail

ONEOS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${CACHE_DIR:-$ONEOS_ROOT/cache}"
BUILD_DIR="${BUILD_DIR:-$ONEOS_ROOT/build}"
PAYLOAD_DIR="${PAYLOAD_DIR:-$BUILD_DIR/payload}"
export ONEOS_ROOT CACHE_DIR BUILD_DIR PAYLOAD_DIR

# Reproducible timestamps (mkfs, tar, xorriso honour these).
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1767225600}"   # 2026-01-01T00:00:00Z
export E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH"

if [[ -t 2 ]]; then _c_info=$'\e[36m' _c_warn=$'\e[33m' _c_err=$'\e[31m' _c_off=$'\e[0m'
else _c_info="" _c_warn="" _c_err="" _c_off=""; fi

log()  { printf '%s[oneos]%s %s\n' "$_c_info" "$_c_off" "$*" >&2; }
warn() { printf '%s[oneos] warning:%s %s\n' "$_c_warn" "$_c_off" "$*" >&2; }
die()  { printf '%s[oneos] error:%s %s\n' "$_c_err" "$_c_off" "$*" >&2; exit 1; }

need() {
  local c
  for c in "$@"; do command -v "$c" >/dev/null 2>&1 || die "missing required command: $c"; done
}

require_linux() {
  [[ "$(uname -s)" == Linux ]] || die "this step needs Linux; on macOS run it via 'make' (it uses the builder container)"
}

# Run a command as root, logging it. Already-root (container) runs it directly.
priv() {
  log "priv: $*"
  if [[ $EUID -eq 0 ]]; then "$@"; else sudo -- "$@"; fi
}

manifest() { python3 "$ONEOS_ROOT/scripts/manifest.py" "$@"; }

sha256_of() { sha256sum "$1" | awk '{print $1}'; }

# verify_sha256 <file> <expected>
verify_sha256() {
  local got
  got="$(sha256_of "$1")"
  [[ "$got" == "$2" ]] || { warn "checksum mismatch for $1: expected $2, got $got"; return 1; }
}

# download <url> <dest> <sha256>: atomic, verified, never leaves a bad file behind.
download() {
  local url="$1" dest="$2" sum="$3" part="$2.part"
  mkdir -p "$(dirname "$dest")"
  if [[ -f "$dest" ]] && verify_sha256 "$dest" "$sum" 2>/dev/null; then
    log "cached: $(basename "$dest")"; return 0
  fi
  log "downloading $url"
  curl -fL --retry 3 --retry-delay 2 -C - -o "$part" "$url" || { rm -f "$part"; die "download failed: $url"; }
  if ! verify_sha256 "$part" "$sum"; then rm -f "$part"; die "refusing $url: checksum mismatch"; fi
  mv -f "$part" "$dest"
}

# Loop devices -------------------------------------------------------------

LOOP_DEVS=()
# loop_attach <image> <var>: attach and store /dev/loopN in <var>. Not a $(…)
# helper on purpose: LOOP_DEVS must be updated in this shell for cleanup.
loop_attach() {
  local _ldev
  _ldev="$(priv losetup -fP --show "$1")"
  LOOP_DEVS+=("$_ldev")
  # In containers without udev the partition nodes may lag; nudge them.
  priv partprobe "$_ldev" 2>/dev/null || true
  printf -v "$2" '%s' "$_ldev"
}
loop_detach_all() {
  local d
  for d in "${LOOP_DEVS[@]:-}"; do
    if [[ -n "$d" ]]; then priv losetup -d "$d" 2>/dev/null || true; fi
  done
  LOOP_DEVS=()
}

# part_dev <disk> <n>: /dev/sdb + 1 → /dev/sdb1, /dev/loop0 + 1 → /dev/loop0p1
part_dev() {
  if [[ "$1" =~ [0-9]$ ]]; then echo "${1}p$2"; else echo "${1}$2"; fi
}

wait_for_block() {  # wait_for_block <dev> [timeout_s]
  local i
  for ((i = 0; i < ${2:-10} * 10; i++)); do [[ -b "$1" ]] && return 0; sleep 0.1; done
  # No udev (e.g. Docker Desktop): create the node from sysfs.
  local name sys
  name="$(basename "$1")"
  sys="$(find /sys/class/block -maxdepth 1 -name "$name" 2>/dev/null | head -1)"
  if [[ -n "$sys" && -r "$sys/dev" ]]; then
    IFS=: read -r maj min <"$sys/dev"
    priv mknod "$1" b "$maj" "$min" && return 0
  fi
  die "block device $1 did not appear"
}

MOUNTS=()
mount_p1() {  # mount_p1 <part> <dir> [ro]
  mkdir -p "$2"
  priv mount -t exfat -o "${3:-rw},uid=$(id -u),gid=$(id -g)" "$1" "$2"
  MOUNTS+=("$2")
}
umount_all() {
  local m
  for m in "${MOUNTS[@]:-}"; do
    if [[ -n "$m" ]]; then sync; priv umount "$m" 2>/dev/null || true; fi
  done
  MOUNTS=()
}

cleanup_privileged() { umount_all; loop_detach_all; }
