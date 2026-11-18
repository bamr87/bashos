#!/usr/bin/env bash
# Build the home-base ISO with live-build (§5.1).
# Runs as root inside the amd64 builder container (make lightos does that).
# The live-build tree is copied to a container-local work dir: debootstrap
# needs a real Linux filesystem (bind mounts from macOS don't do mknod).
source "$(dirname "$0")/lib.sh"
require_linux
need lb debootstrap python3
[[ $EUID -eq 0 ]] || die "live-build must run as root (use 'make lightos')"

work="${LB_WORKDIR:-/var/tmp/oneos-lightos}"
out="$BUILD_DIR/oneos-lightos.iso"
arch="$(manifest get lightos.architecture)"
[[ "$(dpkg --print-architecture)" == "$arch" ]] ||
  die "builder is $(dpkg --print-architecture) but lightos.architecture is $arch (run the builder with --platform linux/$arch)"

rm -rf "$work"
mkdir -p "$work"
cp -a "$ONEOS_ROOT/lightos/." "$work/"
cd "$work"

# Package list generated from the manifest (desktop + extra_packages).
manifest packages >config/package-lists/manifest.list.chroot
log "packages: $(tr '\n' ' ' <config/package-lists/manifest.list.chroot)"

# Bake the build identity into the image for oneos-selftest / support.
mkdir -p config/includes.chroot/etc
{
  echo "ONEOS_VERSION=$(git -C "$ONEOS_ROOT" describe --always --dirty 2>/dev/null || echo dev)"
  echo "ONEOS_BUILD_EPOCH=$SOURCE_DATE_EPOCH"
} >config/includes.chroot/etc/oneos-release

chmod +x config/includes.chroot/usr/local/bin/* config/hooks/live/*.hook.chroot auto/*

lb clean --purge >/dev/null 2>&1 || true

# Backports: the archive, plus an apt pin so the listed packages (kernel, firmware) come from it.
dist="$(manifest get lightos.distribution)"
mapfile -t bp < <(manifest backports)
if [[ ${#bp[@]} -gt 0 ]]; then
  mkdir -p config/archives
  for stage in chroot binary; do
    echo "deb http://deb.debian.org/debian $dist-backports main contrib non-free non-free-firmware" \
      >"config/archives/backports.list.$stage"
    printf 'Package: %s\nPin: release n=%s-backports\nPin-Priority: 990\n' "${bp[*]}" "$dist" \
      >"config/archives/backports.pref.$stage"
  done
  log "from $dist-backports: ${bp[*]}"
fi
DISTRIBUTION="$(manifest get lightos.distribution)" ARCH="$arch" lb config

# The ISO's own boot menu must not wait for a keypress (Ventoy shows it after
# its own menu). Start from live-build's templates and set short timeouts.
mkdir -p config/bootloaders
cp -a /usr/share/live/build/bootloaders/. config/bootloaders/
find config/bootloaders -type f -name '*.cfg' -print0 | while IFS= read -r -d '' f; do
  sed -i -E 's/^([[:space:]]*set[[:space:]]+timeout=).*/\15/; s/^([[:space:]]*timeout[[:space:]]+)[0-9]+/\150/I' "$f"
done
grep -rqs 'timeout=' config/bootloaders/grub-pc/ || echo 'set timeout=5' >>config/bootloaders/grub-pc/config.cfg
for f in config/bootloaders/isolinux/isolinux.cfg config/bootloaders/syslinux_common/isolinux.cfg; do
  if [[ -f "$f" ]] && ! grep -qi '^timeout' "$f"; then sed -i '1a timeout 50' "$f"; fi
done

# Extra GRUB entry (UEFI; SteamOS is UEFI-only): boot the home base straight into the
# SteamOS installer wizard. live-build fills in the @…@ placeholders.
cat >>config/bootloaders/grub-pc/grub.cfg <<'EOF'

menuentry "Install SteamOS onto this PC's M.2 drive (downloads the latest)" {
	linux	@KERNEL_LIVE@ @APPEND_LIVE@ oneos.task=steamos-install
	initrd	@INITRD_LIVE@
}
EOF

log "lb build (this takes a while)…"
mkdir -p "$BUILD_DIR"   # a fresh checkout has no build/ yet; tee must not fail and cut lb build off
lb build 2>&1 | tee "$BUILD_DIR/lightos-build.log" | grep -E '^(P:|E:|W:)' || true

iso="$(find "$work" -maxdepth 1 -name '*.hybrid.iso' | head -1)"
[[ -f "$iso" ]] || die "live-build produced no ISO; see build/lightos-build.log"
mkdir -p "$BUILD_DIR"
cp -f "$iso" "$out"
(cd "$BUILD_DIR" && sha256sum "$(basename "$out")" >"$(basename "$out").sha256")
log "home base ISO → $out ($(du -h "$out" | cut -f1))"
