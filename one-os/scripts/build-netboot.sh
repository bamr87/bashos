#!/usr/bin/env bash
# Assemble build/netboot/: what netboot/server.py serves to network-booting PCs.
#   live/vmlinuz, live/initrd.img, live/filesystem.squashfs   home base, extracted from the ISO
#   tftp/snponly.efi, tftp/ipxe.efi, tftp/undionly.kpxe       iPXE loaders for PXE firmware
source "$(dirname "$0")/lib.sh"
need xorriso

iso="${LIGHTOS_ISO:-$BUILD_DIR/oneos-lightos.iso}"
[[ -f "$iso" ]] || die "missing $iso — run 'make lightos'"
out="$BUILD_DIR/netboot"
# Replace only what this script makes: the server keeps its log, install records and the
# TFTP hand-off files it writes at startup in this directory too.
rm -rf "$out/live"
rm -f "$out/tftp/snponly.efi" "$out/tftp/ipxe.efi" "$out/tftp/undionly.kpxe" "$out/SHA256SUMS"
mkdir -p "$out/live" "$out/tftp"

# Kernel + initrd: live-build names them vmlinuz-<ver> / initrd.img-<ver> (plus plain copies on some builds).
listing="$(xorriso -indev "$iso" -find /live -type f 2>/dev/null | tr -d "'")"
kernel="$(grep -E '^/live/vmlinuz' <<<"$listing" | sort | tail -1)"
initrd="$(grep -E '^/live/initrd\.img' <<<"$listing" | sort | tail -1)"
[[ -n "$kernel" && -n "$initrd" ]] || die "no kernel/initrd under /live in $iso"
xorriso -osirrox on -indev "$iso" \
  -extract "$kernel" "$out/live/vmlinuz" \
  -extract "$initrd" "$out/live/initrd.img" \
  -extract /live/filesystem.squashfs "$out/live/filesystem.squashfs" >/dev/null 2>&1 ||
  die "could not extract the live system from $iso"
chmod 0644 "$out"/live/*

# iPXE loaders (Debian's ipxe package). snponly.efi uses the firmware's own NIC driver —
# the most compatible choice for UEFI PXE; undionly.kpxe is the BIOS equivalent.
for f in snponly.efi ipxe.efi undionly.kpxe; do
  src="$(find /usr/lib/ipxe -maxdepth 2 -name "$f" | head -1)"
  [[ -n "$src" ]] || die "iPXE loader $f not found (builder needs the 'ipxe' package; run 'make builder')"
  cp "$src" "$out/tftp/$f"
done

# tftp/boot.ipxe (the hand-off for iPXE NIC ROMs, e.g. QEMU's) is written by
# netboot/server.py at startup, because it embeds the server's port.

(cd "$out" && find live tftp -type f ! -name '*.ipxe' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum |
  sed 's#  \./#  #') >"$out/SHA256SUMS"
log "netboot files → $out ($(du -sh "$out" | cut -f1))"
