#!/usr/bin/env bash
# flash.sh <device> [--i-know-this-is-not-usb]
# Safety-guarded wrapper around install-to-device.sh for real sticks (§5.5).
# Never run by agents or CI.
source "$(dirname "$0")/lib.sh"
require_linux
need lsblk findmnt

dev="" not_usb_ok=0
for a in "$@"; do
  case "$a" in
    --i-know-this-is-not-usb) not_usb_ok=1 ;;
    /dev/*) dev="$a" ;;
    *) die "unknown argument: $a" ;;
  esac
done

# Guard 1: explicit device, never auto-detected.
[[ -n "$dev" ]] || die "DEV must be set explicitly, e.g. make flash DEV=/dev/sdX"
[[ -b "$dev" ]] || die "$dev is not a block device"
[[ "$(lsblk -dno TYPE "$dev")" == disk ]] || die "$dev is not a whole disk (got $(lsblk -dno TYPE "$dev"))"
[[ "$dev" =~ ^/dev/loop ]] && die "use 'make image' for loop devices"

# Guard 2: nothing on it may be mounted, and it must not back / or /boot.
for mp in / /boot /boot/efi; do
  src="$(findmnt -no SOURCE "$mp" 2>/dev/null || true)"
  [[ -z "$src" ]] && continue
  parent="$(lsblk -no PKNAME "$src" 2>/dev/null | head -1)"
  [[ "/dev/$parent" == "$dev" || "$src" == "$dev" ]] && die "$dev holds $mp — refusing"
done
if lsblk -nro MOUNTPOINTS "$dev" 2>/dev/null | grep -q .; then
  lsblk -o NAME,MOUNTPOINTS "$dev" >&2
  die "$dev has active mounts — unmount them first"
fi

# Guard 3: removable USB unless explicitly overridden.
read -r rm tran < <(lsblk -dno RM,TRAN "$dev")
if [[ "$rm" != 1 || "$tran" != usb ]]; then
  [[ $not_usb_ok == 1 ]] || die "$dev is not a removable USB disk (RM=$rm TRAN=$tran); pass --i-know-this-is-not-usb for external SSDs"
  warn "$dev is not removable USB (RM=$rm TRAN=$tran) — override given"
fi

# Guard 4: show identity, require typing the model name.
model="$(lsblk -dno MODEL "$dev" | sed 's/[[:space:]]*$//')"
serial="$(lsblk -dno SERIAL "$dev" | sed 's/[[:space:]]*$//')"
size="$(lsblk -dno SIZE "$dev")"
[[ -n "$model" ]] || die "$dev reports no model name; refusing (cannot confirm identity)"
cat >&2 <<EOF

  ┌─────────────────────────────────────────────────────────┐
  │  ALL DATA ON THIS DEVICE WILL BE DESTROYED              │
  └─────────────────────────────────────────────────────────┘
    device : $dev
    model  : $model
    serial : ${serial:-?}
    size   : $size

EOF
[[ -t 0 ]] || die "flash needs an interactive terminal for confirmation"
read -r -p "Type the model name exactly to continue: " typed
[[ "$typed" == "$model" ]] || die "confirmation did not match; nothing was written"

ONEOS_FLASH_GUARDED=1 "$ONEOS_ROOT/scripts/install-to-device.sh" "$dev"
log "done. You can remove $dev once this prompt returns."
