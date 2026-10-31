# os/install/packages.sh — the Debian packages in os/packages/*.list that are missing.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

# os_packages [--all] LIST… — the package names those lists ask for, one per line. A line whose
# `cmd:NAME` guard is already on PATH is skipped, unless --all (an image starts from nothing).
os_packages() {
  local all=0 list line guard words
  [[ ${1:-} == --all ]] && { all=1; shift; }
  for list in "$@"; do
    while IFS= read -r line || [[ -n $line ]]; do
      line=${line%%#*}
      read -ra words <<<"$line"
      ((${#words[@]})) || continue
      guard=""
      if [[ ${words[-1]} == cmd:* ]]; then
        guard=${words[-1]#cmd:}
        unset 'words[-1]'
      fi
      if [[ -n $guard ]] && ((!all)) && os_has "$guard"; then
        continue
      fi
      printf '%s\n' "${words[@]}"
    done <"$OS_DIR/packages/$list.list"
  done
}

# The lists this machine wants: the console's kiosk unless BASHOS_CONSOLE is vt/off, the
# container plane unless the harness is off.
os_package_lists() {
  printf '%s\n' base
  case ${BASHOS_CONSOLE:-auto} in vt | off) ;; *) printf '%s\n' console ;; esac
  [[ ${BASHOS_HARNESS:-native} == off ]] || printf '%s\n' services
}

phase_packages() {
  os_step "packages"
  if os_image; then
    os_ok "installed by the image build (mkosi --package)"
    return 0
  fi
  local lists=() wanted=() missing=() p
  mapfile -t lists < <(os_package_lists)
  mapfile -t wanted < <(os_packages "${lists[@]}")
  if os_fake_root || ! os_has dpkg-query; then
    os_log "${_os_d}skip (no dpkg here):${_os_0} ${#wanted[@]} packages from ${lists[*]}"
    return 0
  fi
  for p in "${wanted[@]}"; do
    dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null | grep -q '^ii' || missing+=("$p")
  done
  if ((!${#missing[@]})); then
    os_ok "all ${#wanted[@]} packages present (${lists[*]})"
    return 0
  fi
  os_log "missing: ${missing[*]}"
  os_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  os_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
  os_dry || os_ok "installed ${#missing[@]} packages"
}
