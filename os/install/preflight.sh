# os/install/preflight.sh — the machine is one this layer supports. Changes nothing.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

phase_preflight() {
  os_step "preflight"
  local release id="" version="" like="" arch port
  release=$(os_path /etc/os-release)
  if [[ -r $release ]]; then
    id=$(sed -n 's/^ID=//p' "$release" | tr -d '"')
    version=$(sed -n 's/^VERSION_ID=//p' "$release" | tr -d '"')
    like=$(sed -n 's/^ID_LIKE=//p' "$release" | tr -d '"')
  fi
  # A preview is allowed anywhere; a real install only where it can work.
  local strict=1
  { os_dry || os_fake_root; } && strict=0

  if [[ $(uname -s) != Linux ]] && ! os_fake_root; then
    ((strict)) && os_die "bashOS the OS layer is Linux-only (this is $(uname -s)); try --dry-run"
    os_warn "$(uname -s): previewing only — the layer installs on Debian 13"
  elif [[ $id == debian && $version == 13 ]]; then
    os_ok "Debian 13 ($(sed -n 's/^VERSION_CODENAME=//p' "$release"))"
  elif [[ $id == debian || " $like " == *" debian "* ]]; then
    os_warn "${id:-unknown} ${version} — built for Debian 13; package names may differ"
  else
    ((strict)) && os_die "${id:-an unknown distribution}: the layer installs on Debian 13 (apt + systemd)"
    os_warn "${id:-unknown distribution}: previewing only"
  fi

  arch=$(uname -m)
  case $arch in
    x86_64 | aarch64 | arm64) os_ok "architecture $arch" ;;
    *) os_warn "architecture $arch is untested" ;;
  esac

  if ! os_fake_root && ! os_image && [[ $(uname -s) == Linux && ! -d /run/systemd/system ]]; then
    os_warn "systemd is not running here — units are installed but not started"
  fi

  if ! os_is_root && ! os_fake_root && ! os_dry && [[ ${want_system:-1} == 1 ]]; then
    if sudo -n true 2>/dev/null; then
      os_ok "sudo (no prompt)"
    elif [[ -t 0 ]]; then
      os_log "the system phases need root — sudo asks once:"
      sudo -v || os_die "sudo refused"
    else
      os_die "the system phases need root and sudo would prompt with no terminal attached"
    fi
  fi

  # The harness port: on forge the hub's compose stack may already serve it.
  port=${BASHOS_HARNESS_PORT:-4001}
  if [[ ${BASHOS_HARNESS:-native} == native ]] && os_has ss && ! os_fake_root; then
    if ss -Hltn "sport = :$port" 2>/dev/null | grep -q .; then
      if systemctl --user is-active --quiet bashos-harness.service 2>/dev/null; then
        os_ok "harness port $port (bashos-harness)"
      else
        os_warn "port $port is already served — if that is the hub's compose console, set BASHOS_HARNESS=compose in /etc/bashos/os.conf"
      fi
    fi
  fi

  # The forge pattern predates this layer: an existing tty1 console mirror is adopted, not replaced.
  local f
  for f in "$OS_HOME/.zprofile" "$OS_HOME/.bash_profile" "$OS_HOME/.profile"; do
    if [[ -f $f ]] && grep -q '/dev/tty1' "$f" && ! grep -qxF "$OS_BEGIN" "$f"; then
      os_ok "existing tty1 console mirror in ${f/#$OS_HOME/\~} — adopted (bashos-console adds its window)"
    fi
  done
  return 0
}
