#!/usr/bin/env bash
# Images built before 2026-11-02 installed OpenCode with npm into /usr/local: all four linux-x64
# builds, ~800 MB, never updated. The managed engine (os/install/engine.sh) replaces it; once it
# runs and /usr/local/bin/opencode points at it, the npm copy goes. In-place installs are left
# alone: an npm opencode there is the person's own.
set -Eeuo pipefail
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"
# shellcheck source=../install/engine.sh
source "$OS_SRC/os/install/engine.sh"

old=/usr/local/lib/node_modules/opencode-ai
if [[ ! -f $(os_path /etc/systemd/network/80-bashos-wired.network) ]]; then
  os_log "not an image machine — an npm opencode here is the person's own; nothing to do"
  exit 0
fi
if [[ ! -d $(os_path "$old") ]]; then
  os_log "no npm-installed opencode — nothing to do"
  exit 0
fi
if [[ ! -x $(os_path "$OS_ENGINE_BIN") ]]; then
  os_warn "the managed engine is not installed yet — run: bashos os engine update, then: bashos os migrate"
  exit 1
fi
os_engine_link
os_root rm -rf "$(os_path "$old")"
os_ok "removed the npm copy of opencode ($old); bashOS runs $OS_ENGINE_BIN"
