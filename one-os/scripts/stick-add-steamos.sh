#!/usr/bin/env bash
# stick-add-steamos.sh <whole-block-device>
# Put Valve's SteamOS recovery stick inside the stick's reserved space (Ventoy -r), so the
# one-os stick boots Valve's own installer the normal way: Ventoy → F6 → "SteamOS recovery".
#
# Valve's recovery image is a whole disk (esp, efi-A, rootfs-A, var-A, home), not an ISO, so it
# can't live in Ventoy's file area. Each partition is copied byte for byte into new GPT entries
# after Ventoy's two, with Valve's partition type, PARTUUID and name: Valve's boot loader and
# initramfs find their partitions exactly as on Valve's own stick. ventoy/ventoy_grub.cfg (F6)
# chainloads Valve's loader from the copied ESP.
#
# Called by install-to-device.sh (step 5) when manifest steamos.recovery_on_stick is true.
source "$(dirname "$0")/lib.sh"
require_linux
need sfdisk dd blkid blockdev partprobe python3

dev="${1:-}"
[[ -b "$dev" ]] || die "usage: $0 /dev/<disk>"
if [[ "${ONEOS_FLASH_GUARDED:-0}" != 1 && ! "$dev" =~ ^/dev/loop ]]; then
  die "refusing to touch $dev directly; use 'make flash' (scripts/flash.sh)"
fi

# Valve's recovery image: build/steamos/recovery.img, else the newest cached .img.bz2 unpacked.
img="${STEAMOS_RECOVERY_IMG:-$BUILD_DIR/steamos/recovery.img}"
if [[ ! -f $img ]]; then
  # `|| true`: with no cached image, ls fails, and under pipefail that would end the script with
  # status 2 and no message.
  # shellcheck disable=SC2012  # newest by mtime; Valve names have no odd characters
  bz="$(ls -t "$ONEOS_ROOT"/cache/steamos/*.img.bz2 2>/dev/null | head -1 || true)"
  if [[ -z $bz && ${CI:-} == true ]]; then
    # CI has no 8 GB Valve image: its test stick goes without, and T120 skips. A stick for a
    # machine still needs it (below).
    warn "no SteamOS recovery image in CI: the reserved space stays empty"
    exit 0
  fi
  [[ -n $bz ]] || die "no SteamOS recovery image: run 'make steamos-fetch'"
  log "unpacking $(basename "$bz") → $img (~8 GB)"
  mkdir -p "$(dirname "$img")"
  if command -v lbzip2 >/dev/null; then lbzip2 -dc "$bz"; else bzip2 -dc "$bz"; fi >"$img.part"
  mv "$img.part" "$img"
fi

# The image's partitions, in order: start size type uuid name (sectors of 512 bytes).
mapfile -t parts < <(sfdisk -J "$img" | python3 -c '
import json, sys
for p in json.load(sys.stdin)["partitiontable"]["partitions"]:
    print(p["start"], p["size"], p["type"], p["uuid"], p.get("name", ""))')
[[ ${#parts[@]} -ge 4 ]] || die "$img doesn't look like a SteamOS recovery image (${#parts[@]} partitions)"
printf '%s\n' "${parts[@]}" | awk '{print $5}' | grep -qx rootfs-A || die "$img has no rootfs-A partition"

# Free space after Ventoy's partitions (its reserved area), 1 MiB aligned.
start="$(priv sfdisk -J "$dev" | python3 -c '
import json, sys
t = json.load(sys.stdin)["partitiontable"]
end = max(p["start"] + p["size"] for p in t["partitions"])
print(-(-end // 2048) * 2048)')"
need_s="$(printf '%s\n' "${parts[@]}" | awk '{s += int(($2 + 2047) / 2048) * 2048} END {print s}')"
total_s="$(priv blockdev --getsz "$dev")"
(( start + need_s + 34 <= total_s )) ||
  die "reserved space too small: need $(( need_s / 2048 )) MiB after Ventoy, have $(( (total_s - start - 34) / 2048 )) MiB (raise ventoy.options.reserve_mb)"

# New GPT entries 3.., same type / PARTUUID / name as Valve's.
script="" at=$start
for p in "${parts[@]}"; do
  read -r _s size type uuid name <<<"$p"
  script+="start=$at, size=$size, type=$type, uuid=$uuid, name=\"$name\""$'\n'
  at=$(( at + (size + 2047) / 2048 * 2048 ))
done
log "adding Valve's recovery partitions after Ventoy's: $(printf '%s\n' "${parts[@]}" | awk '{printf "%s ", $5}')"
printf '%s' "$script" | priv sfdisk --append --no-reread --quiet "$dev" >/dev/null
priv partprobe "$dev" 2>/dev/null || true

# Copy each partition. Real zeros, not holes: write-image.py skips holes, and a stick's
# old contents must not show through inside Valve's filesystems.
n=3
for p in "${parts[@]}"; do
  read -r s size _t _u name <<<"$p"
  pdev="$(part_dev "$dev" "$n")"
  wait_for_block "$pdev" 15
  log "  $name → $pdev ($(( size / 2048 )) MiB)"
  priv dd if="$img" of="$pdev" bs=4M iflag=skip_bytes,count_bytes skip=$(( s * 512 )) count=$(( size * 512 )) \
    status=none conv=fsync
  n=$(( n + 1 ))
done

# Ventoy F6 menu: chainload Valve's loader from the copied ESP (found by its FAT serial, which a
# PC's own SteamOS install doesn't share: Valve's installer formats its ESP afresh).
esp_n=3 esp_uuid=""
for p in "${parts[@]}"; do
  read -r _s _z type _u name <<<"$p"
  if [[ ${type^^} == C12A7328-F81F-11D2-BA4B-00A0C93EC93B ]]; then
    esp_uuid="$(priv blkid -o value -s UUID "$(part_dev "$dev" "$esp_n")")"; break
  fi
  esp_n=$(( esp_n + 1 ))
done
[[ -n $esp_uuid ]] || die "copied ESP has no filesystem UUID"
version="$(basename "$img")"
[[ -f $img.version ]] && version="$(cat "$img.version")"

mnt="$(mktemp -d)"
mount_p1 "$(part_dev "$dev" 1)" "$mnt"
mkdir -p "$mnt/ventoy"
cat >"$mnt/ventoy/ventoy_grub.cfg" <<EOF
# one-os: Valve's SteamOS recovery, on this stick's partitions $esp_n.. (scripts/stick-add-steamos.sh)
menuentry "SteamOS recovery - Valve's installer (re-image this PC's M.2)" --class=custom {
    search --no-floppy --fs-uuid --set=root $esp_uuid
    chainloader /efi/boot/bootx64.efi
}
menuentry "<-- back to the one-os menu" --class=vtoyret VTOY_RET {
    echo "Return ..."
}
EOF
echo "$version" >"$mnt/ventoy/steamos-recovery.txt"
sync
umount_all
rmdir "$mnt"
log "SteamOS recovery on $dev: Ventoy menu → F6 → \"SteamOS recovery\" (ESP $esp_uuid)"
