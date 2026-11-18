#!/usr/bin/env bash
# Sparse file → loop → install-to-device → detach (§5.4).
source "$(dirname "$0")/lib.sh"
require_linux
need losetup truncate

img="${IMAGE:-$BUILD_DIR/one-os-test.img}"
# Default size: at least 16 GiB, and always enough for the payload plus Ventoy's reserved
# space (ventoy.options.reserve_mb) plus 1 GiB for the ESP and filesystem overhead.
# A full cache/ of large ISOs or a bigger reserve no longer overflows a fixed 16 GiB image.
if [[ -n "${IMAGE_SIZE:-}" ]]; then
  size="$IMAGE_SIZE"
else
  payload_mb=$(( $(du -sLB1 --apparent-size "$PAYLOAD_DIR" | cut -f1) / 1048576 ))
  reserve_mb="$(manifest get ventoy.options.reserve_mb)"
  need_gb=$(( (payload_mb + reserve_mb + 1024 + 1023) / 1024 ))
  (( need_gb < 16 )) && need_gb=16
  size="${need_gb}G"
fi

rm -f "$img"
truncate -s "$size" "$img"
trap cleanup_privileged EXIT
dev=""
loop_attach "$img" dev
log "attached $img as $dev"
"$ONEOS_ROOT/scripts/install-to-device.sh" "$dev"
loop_detach_all
log "test image ready: $img ($(du -h "$img" | cut -f1) used of $size)"
