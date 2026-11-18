#!/usr/bin/env bash
# make lint: shellcheck, ruff, manifest schema + no <PIN>s, ventoy.json renders.
source "$(dirname "$0")/lib.sh"
need shellcheck ruff python3
cd "$ONEOS_ROOT"
rc=0

log "shellcheck"
mapfile -t sh_files < <(
  { ls scripts/*.sh scripts/oneos-vm scripts/oneos-wizard scripts/oneos-remote remote/agent/oneos-gui remote/agent/oneos-claude lightos/auto/* lightos/config/hooks/live/*;
    grep -l '^#!.*bash' lightos/config/includes.chroot/usr/local/bin/*; } | sort -u)
shellcheck -x -P scripts -P remote/agent "${sh_files[@]}" || rc=1

log "ruff"
ruff check --config harness/pyproject.toml harness scripts/manifest.py scripts/write-image.py scripts/card-boot.py scripts/capture-steamos.py scripts/stick-add-netboot.py scripts/render-docs.py ui/server.py netboot/server.py netboot/watch.py remote/agent/oneos-input remote/agent/oneos-monitor \
  lightos/config/includes.chroot/usr/local/bin/oneos-restock || rc=1

log "manifest"
manifest lint || rc=1

log "ventoy.json template"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
PRESENT="$(manifest artifacts | jq -r .file | tr '\n' ' ')" \
  manifest render-ventoy config/ventoy.json.j2 "$tmp/ventoy.json" || rc=1

[[ $rc -eq 0 ]] || die "lint failed"
log "lint OK"
