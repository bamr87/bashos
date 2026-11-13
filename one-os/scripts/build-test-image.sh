#!/usr/bin/env bash
# Sparse file → loop → install-to-device → detach (§5.4).
source "$(dirname "$0")/lib.sh"
require_linux
need losetup truncate

img="${IMAGE:-$BUILD_DIR/one-os-test.img}"
size="${IMAGE_SIZE:-16G}"

rm -f "$img"
truncate -s "$size" "$img"
trap cleanup_privileged EXIT
dev=""
loop_attach "$img" dev
log "attached $img as $dev"
"$ONEOS_ROOT/scripts/install-to-device.sh" "$dev"
loop_detach_all
log "test image ready: $img ($(du -h "$img" | cut -f1) used of $size)"
