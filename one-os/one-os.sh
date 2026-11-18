#!/usr/bin/env bash
# bashos one-os …: the entry point to one-os from the bashOS launcher.
#   bashos one-os                 the targets (make help)
#   bashos one-os <target> [VAR=value …]   a make target: lint, fetch, lightos, payload, image, test, wizard, pxe-start, …
#   bashos one-os vm <args>       scripts/oneos-vm: drive named VMs (start, wait, exec, screenshot, stop)
#   bashos one-os machine <args>  scripts/oneos-machine: machine profiles, and a system's kernel checked against them
# Plain shell with no Python dependency, so it runs before bashOS's virtualenv exists.
# Works under macOS's stock bash 3.2.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-help}" in
  vm) shift; exec "${HERE}/scripts/oneos-vm" "$@" ;;
  machine) shift; exec python3 "${HERE}/scripts/oneos-machine" "$@" ;;
  -h|--help|help) exec make -C "${HERE}" --no-print-directory help ;;
  *) exec make -C "${HERE}" --no-print-directory "$@" ;;
esac
