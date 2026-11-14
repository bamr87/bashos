# os/install/packages.sh — the packages in os/packages/*.list that are missing: Debian's names
# under os/packages/, Arch's (Amrchy) under os/packages/arch/.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

# os_packages [--all] LIST… — the package names those lists ask for, one per line. A line whose
# `cmd:NAME` guard is already installed (on PATH or in the person's own tool directories,
# os_user_bins) is skipped, unless --all (an image starts from nothing).
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
      if [[ -n $guard ]] && ((!all)) && os_user_has "$guard"; then
        continue
      fi
      printf '%s\n' "${words[@]}"
    done <"$(os_package_dir)/$list.list"
  done
}

# Where this base's lists live: Arch names for Amrchy and Arch, Debian names otherwise.
os_package_dir() {
  if os_arch_base; then printf '%s' "$OS_DIR/packages/arch"; else printf '%s' "$OS_DIR/packages"; fi
}

# The lists this machine wants: the console's kiosk unless BASHOS_CONSOLE is vt/off, the
# container plane unless the harness is off.
os_package_lists() {
  printf '%s\n' base
  # The kiosk (cage + foot) is Debian's; on Amrchy the console is a window on its desktop.
  if ! os_arch_base; then
    case $(os_console_mode) in vt | off) ;; *) printf '%s\n' console ;; esac
  fi
  [[ ${BASHOS_HARNESS:-native} == off ]] || printf '%s\n' services
}

phase_packages() {
  os_step "packages"
  if os_image; then
    os_ok "installed by the image build"
    return 0
  fi
  local lists=() wanted=() missing=() p
  mapfile -t lists < <(os_package_lists)
  mapfile -t wanted < <(os_packages "${lists[@]}")
  local query=dpkg-query
  os_arch_base && query=pacman
  if os_fake_root || ! os_has "$query"; then
    os_log "${_os_d}skip (no $query here):${_os_0} ${#wanted[@]} packages from ${lists[*]}"
    return 0
  fi
  for p in "${wanted[@]}"; do
    if os_arch_base; then
      pacman -Q -- "$p" >/dev/null 2>&1 || missing+=("$p")
    else
      dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null | grep -q '^ii' || missing+=("$p")
    fi
  done
  if ((!${#missing[@]})); then
    os_ok "all ${#wanted[@]} packages present (${lists[*]})"
    return 0
  fi
  os_log "missing: ${missing[*]}"
  if os_arch_base; then
    # --needed and no -y: an install, never a partial upgrade (Amrchy's own updates go through
    # `omarchy update`, which its pacman hook guards).
    os_root pacman -S --needed --noconfirm -- "${missing[@]}"
  else
    os_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    os_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
  fi
  os_dry || os_ok "installed ${#missing[@]} packages"
}
