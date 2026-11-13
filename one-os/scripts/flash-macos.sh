#!/usr/bin/env bash
# flash-macos.sh <diskN> [--i-know-this-is-not-removable] [--confirm=NAME --expect-size=BYTES]
# macOS counterpart of flash.sh (§5.5). macOS has no Ventoy installer and
# Docker Desktop can't see USB/SD devices, so the builder makes an image of
# exactly the device's size (make card-image) and this writes its data extents
# to the raw device, then verifies them. Never run by agents or CI.
#
# --confirm/--expect-size are for the wizard (ui/), which asks the person to type the
# media name in its own dialog: the write proceeds only if both still match the disk.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${CARD_IMAGE:-$ROOT/build/one-os-card.img}"

# Removable USB/SD whole disks right now, e.g. "disk5 (Built In SDXC Reader, 128.2 GB)".
removable_disks() {
  local d
  for d in $(diskutil list | awk '/^\/dev\/disk[0-9]+ /{sub("/dev/","",$1); print $1}'); do
    diskutil info "$d" 2>/dev/null | grep -Eq 'Removable Media: +Removable' || continue
    diskutil info "$d" | awk -v d="$d" -F': +' '/Device \/ Media Name/{n=$2} /Disk Size/{split($2,s," "); z=s[1]" "s[2]} END{printf "%s (%s, %s)\n", d, n, z}'
  done
}
die() {
  printf '[oneos] error: %s\n' "$*" >&2
  local r; r="$(removable_disks)"
  [[ -n "$r" ]] && printf '[oneos] removable disks right now:\n  %s\n' "${r//$'\n'/$'\n'  }" >&2
  exit 1
}
[[ "$(uname -s)" == Darwin ]] || die "this is the macOS flasher; on Linux use 'make flash DEV=/dev/sdX'"

disk="" override=0 confirm="" expect_size=""
for a in "$@"; do
  case "$a" in
    --i-know-this-is-not-removable) override=1 ;;
    --confirm=*) confirm="${a#--confirm=}" ;;
    --expect-size=*) expect_size="${a#--expect-size=}" ;;
    /dev/disk*) disk="${a#/dev/}" ;;
    disk*) disk="$a" ;;
    *) die "unknown argument: $a" ;;
  esac
done

# Guard 1: explicit whole disk, never auto-detected.
[[ -n "$disk" ]] || die "usage: make flash DISK=diskN (see 'diskutil list')"
[[ "$disk" =~ ^disk[0-9]+$ ]] || die "$disk is not a whole disk (expected diskN, not diskNsM)"
# No sudo: write-image.py opens just this device through macOS's authopen (system
# authorization dialog), so nothing else runs as root. Under sudo it opens it directly.
[[ $EUID -eq 0 || -x /usr/libexec/authopen ]] || die "need /usr/libexec/authopen (or run with sudo)"

# plist_key <disk-or-path> <key.path> → raw value ("" if absent)
plist_key() { plutil -extract "$2" raw -o - - <<<"$(diskutil info -plist "$1")" 2>/dev/null || true; }
info() { plist_key "$disk" "$1"; }
# `diskutil info` can still answer for an identifier that went away (card re-inserted
# under a new diskN); `diskutil list` can't.
diskutil list "$disk" >/dev/null 2>&1 || die "no such disk: $disk (re-inserted? check 'diskutil list')"

# Guard 2: never the physical disk under the running macOS (its APFS container's store).
boot_container="$(plist_key / ParentWholeDisk)"
boot_store="$(plist_key "$boot_container" APFSPhysicalStores.0.APFSPhysicalStore)"
boot_disk="$(sed -E 's/^(disk[0-9]+).*/\1/' <<<"${boot_store:-disk0}")"
[[ "$disk" != "$boot_disk" && "$disk" != "$boot_container" && "$disk" != disk0 ]] ||
  die "$disk holds the running macOS — refusing"
[[ "$(info VirtualOrPhysical)" == Physical ]] || die "$disk is not a physical disk"

# Guard 3: removable media on USB or the SD reader (macOS lists built-in SD readers as "internal").
removable="$(info RemovableMedia)"
proto="$(info BusProtocol)"
if [[ "$removable" != true || ! "$proto" =~ ^(USB|Secure\ Digital)$ ]]; then
  [[ $override == 1 ]] || die "$disk is not removable USB/SD (removable=$removable, bus=$proto); pass FLASH_ARGS=--i-know-this-is-not-removable for external SSDs"
  echo "[oneos] warning: $disk is not removable USB/SD — override given" >&2
fi

# Guard 4: an image built for exactly this device.
size="$(info TotalSize)"
[[ -f "$IMG" ]] || die "no $IMG — run 'make card-image DISK=$disk' first"
isize="$(stat -f %z "$IMG")"
[[ "$isize" == "$size" ]] || die "$IMG is $isize bytes but $disk is $size; rebuild with 'make card-image DISK=$disk'"

# Guard 5: show identity and contents, require typing the media name.
name="$(info MediaName)"
[[ -n "$name" ]] || die "$disk reports no media name; refusing (cannot confirm identity)"
cat >&2 <<EOF

  ┌─────────────────────────────────────────────────────────┐
  │  ALL DATA ON THIS DEVICE WILL BE DESTROYED              │
  └─────────────────────────────────────────────────────────┘
    disk   : /dev/$disk
    media  : $name
    bus    : $proto
    size   : $(awk -v s="$size" 'BEGIN{printf "%.1f GB (%d bytes)", s/1e9, s}')
    now on it:
$(diskutil list "$disk" | sed -n '3,$p' | sed 's/^/      /')

EOF
if [[ -n "$confirm" ]]; then
  # Confirmed in the wizard; the disk must still be the one the person looked at.
  [[ -n "$expect_size" && "$expect_size" == "$size" ]] ||
    die "$disk is $size bytes, not the $expect_size the confirmation was for; nothing was written"
  typed="$confirm"
else
  [[ -t 0 ]] || die "flash needs an interactive terminal for confirmation"
  echo "To confirm you mean THIS device, retype its media name shown above (it is not a new name for the stick)." >&2
  read -r -p "Media name [$name]: " typed
fi
[[ $EUID -eq 0 ]] || echo "[oneos] macOS will now ask for an administrator password to open $disk (dialog from 'authopen')." >&2
[[ "$typed" == "$name" ]] || die "confirmation '$typed' did not match '$name'; nothing was written"

diskutil unmountDisk "/dev/$disk" >/dev/null || die "could not unmount $disk (close Finder windows / apps using it)"
python3 "$ROOT/scripts/write-image.py" "$IMG" "/dev/r$disk"
diskutil eject "/dev/$disk" >/dev/null 2>&1 || true
echo "[oneos] done: /dev/$disk now holds one-os ($(basename "$IMG")). It's ejected — safe to remove." >&2
