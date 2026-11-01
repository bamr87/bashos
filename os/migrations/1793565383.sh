#!/usr/bin/env bash
# Image machines (systemd-networkd): network-online means any wired link, as images built since
# 2026-11-01 ship it (os/image/mkosi.extra). Takes effect at the next boot; nothing restarts now.
set -Eeuo pipefail
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"

dropin=/etc/systemd/system/systemd-networkd-wait-online.service.d/10-bashos-any.conf
if [[ ! -f $(os_path /etc/systemd/network/80-bashos-wired.network) ]]; then
  os_log "not an image machine (no bashOS networkd config) — nothing to do"
  exit 0
fi
os_install_file "$OS_SRC/os/image/mkosi.extra$dropin" "$dropin"
if os_systemd_live; then
  os_root systemctl daemon-reload
  os_root systemctl reset-failed systemd-networkd-wait-online.service 2>/dev/null || true
fi
