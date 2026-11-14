#!/usr/bin/env bash
# install-to-device.sh <whole-block-device>
# The ONE code path that puts Ventoy + payload on a disk, used for loop
# devices (tests/CI) and real sticks (via flash.sh). §5.3.
source "$(dirname "$0")/lib.sh"
require_linux
need lsblk blkid mount umount rsync partprobe

dev="${1:-}"
[[ -n "$dev" ]] || die "usage: $0 /dev/<disk>"
[[ -b "$dev" ]] || die "$dev is not a block device"
[[ "$(lsblk -dno TYPE "$dev")" =~ ^(disk|loop)$ ]] || die "$dev is not a whole disk"
[[ -d "$PAYLOAD_DIR/ISO" ]] || die "no payload at $PAYLOAD_DIR — run 'make payload'"

if [[ "${ONEOS_FLASH_GUARDED:-0}" != 1 && ! "$dev" =~ ^/dev/loop ]]; then
  die "refusing to touch $dev directly; use 'make flash DEV=$dev' (scripts/flash.sh)"
fi

v_ver="$(manifest get ventoy.version)"
v_dir="$BUILD_DIR/ventoy/ventoy-$v_ver"
[[ -x "$v_dir/Ventoy2Disk.sh" ]] || die "Ventoy $v_ver not unpacked — run 'make fetch'"

args=(-I)
[[ "$(manifest get ventoy.options.partition_style)" == gpt ]] && args+=(-g)
[[ "$(manifest get ventoy.options.secure_boot)" == true ]] && args+=(-s)
reserve="$(manifest get ventoy.options.reserve_mb)"
[[ "$reserve" -gt 0 ]] && args+=(-r "$reserve")

trap cleanup_privileged EXIT

# 1–2. Ventoy2Disk. It asks for confirmation twice even with -I; answer from here.
log "Ventoy2Disk.sh ${args[*]} $dev"
(cd "$v_dir" && printf 'y\ny\n' | priv ./Ventoy2Disk.sh "${args[@]}" "$dev") ||
  die "Ventoy2Disk.sh failed"

# 3. Wait for P1, verify its label.
priv partprobe "$dev" 2>/dev/null || true
p1="$(part_dev "$dev" 1)"
p2="$(part_dev "$dev" 2)"
wait_for_block "$p1" 15
wait_for_block "$p2" 15
label="$(priv blkid -o value -s LABEL "$p1" || true)"
[[ "$label" == Ventoy ]] || die "P1 label is '$label', expected 'Ventoy'"

# 4. Copy the payload.
mnt="$(mktemp -d)"
mount_p1 "$p1" "$mnt"
log "copying payload → $p1"
# exFAT has no owners/permissions/symlinks: copy content + times only.
rsync -rt --inplace --info=progress2 "$PAYLOAD_DIR/" "$mnt/"
sync
umount_all
rmdir "$mnt"

# 5. Reserved space (Ventoy -r): Valve's SteamOS recovery stick, bootable from Ventoy's F6 menu.
if [[ "$reserve" -gt 0 ]]; then
  if [[ "$(manifest get steamos.recovery_on_stick)" == true ]]; then
    "$ONEOS_ROOT/scripts/stick-add-steamos.sh" "$dev"
  else
    warn "reserve_mb=$reserve: nothing configured for the reserved space; left unformatted"
  fi
fi
log "installed Ventoy $v_ver + payload on $dev"
