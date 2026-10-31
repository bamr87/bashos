# os/install/system.sh — /etc/bashos, never-sleep, the systemd units, tty1 autologin, linger.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

# The getty drop-in that auto-logs USER in on tty1 — the physical monitor.
os_autologin_conf() {
  printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin %s --noclear %%I $TERM\n' "$1"
}

# Some other drop-in (forge's 03-console-mirror.sh wrote autologin.conf) already logs USER in.
os_autologin_elsewhere() {
  local f dir
  dir=$(os_path /etc/systemd/system/getty@tty1.service.d)
  for f in "$dir"/*.conf; do
    [[ -f $f && $(basename "$f") != bashos-autologin.conf ]] || continue
    grep -q -- "--autologin $1" "$f" && return 0
  done
  return 1
}

os_units() {
  local unit changed=0 before after
  before=$(cat "$(os_path /usr/local/lib/systemd)"/{system,user}/bashos-* 2>/dev/null | cksum || true)
  for unit in "$OS_DIR"/systemd/system/*; do
    os_install_file "$unit" "/usr/local/lib/systemd/system/$(basename "$unit")"
  done
  for unit in "$OS_DIR"/systemd/user/*; do
    os_install_file "$unit" "/usr/local/lib/systemd/user/$(basename "$unit")"
  done
  after=$(cat "$(os_path /usr/local/lib/systemd)"/{system,user}/bashos-* 2>/dev/null | cksum || true)
  [[ $before == "$after" ]] || changed=1
  if ((changed)) && os_systemd_live; then
    os_root systemctl daemon-reload
  fi
}

os_never_sleep() {
  [[ ${BASHOS_NEVER_SLEEP:-yes} == yes ]] || return 0
  os_write_file /etc/systemd/logind.conf.d/bashos-no-sleep.conf <<'EOF'
# bashOS: a dev box never sleeps (BASHOS_NEVER_SLEEP in /etc/bashos/os.conf).
[Login]
HandleSuspendKey=ignore
HandleHibernateKey=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF
  local masked=1 t
  for t in sleep suspend hibernate hybrid-sleep; do
    [[ $(readlink "$(os_path "/etc/systemd/system/$t.target")" 2>/dev/null) == /dev/null ]] || masked=0
  done
  if ((masked)); then
    os_log "${_os_d}unchanged${_os_0} sleep targets masked"
  else
    os_systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
  fi
}

os_console_login() {
  local user=$1
  [[ ${BASHOS_CONSOLE:-auto} != off ]] || { os_log "console off: tty1 left alone"; return 0; }
  if os_autologin_elsewhere "$user"; then
    os_ok "tty1 already logs $user in (an existing getty drop-in) — kept"
    return 0
  fi
  os_autologin_conf "$user" | os_write_file /etc/systemd/system/getty@tty1.service.d/bashos-autologin.conf
}

os_linger() {
  local user=$1 marker
  marker=$(os_path "/var/lib/systemd/linger/$user")
  if [[ -e $marker ]]; then
    os_log "${_os_d}unchanged${_os_0} linger for $user"
  elif os_systemd_live; then
    os_root loginctl enable-linger "$user"
  else
    # loginctl only writes this marker; offline the marker is the whole operation.
    os_root mkdir -p "$(dirname "$marker")"
    os_root touch "$marker"
  fi
}

os_harness_firewall() {
  local host=${BASHOS_HARNESS_HOST:-127.0.0.1} port=${BASHOS_HARNESS_PORT:-4001}
  os_loopback "$host" && return 0
  if [[ -z ${BASHOS_LAN_CIDR:-} ]]; then
    os_warn "the harness binds $host but BASHOS_LAN_CIDR is empty — no firewall rule added"
    return 0
  fi
  if os_has ufw && ! os_fake_root; then
    os_root ufw allow from "$BASHOS_LAN_CIDR" to any port "$port" proto tcp comment 'bashos harness'
  fi
}

phase_system() {
  os_step "system"
  if [[ -f $(os_path /etc/bashos/os.conf) ]]; then
    os_log "${_os_d}kept${_os_0} /etc/bashos/os.conf (the machine's settings)"
  else
    os_install_file "$OS_DIR/config/os.conf" /etc/bashos/os.conf
  fi
  os_never_sleep
  os_units
  if os_image; then
    # The user does not exist yet: bashos-provision creates them at first boot, then writes
    # their autologin and linger. Every user's manager starts the harness and the heal timer.
    os_systemctl enable bashos-provision.service
    os_user_systemctl root enable bashos-harness.service bashos-heal.timer
    return 0
  fi
  os_console_login "$OS_USER"
  os_linger "$OS_USER"
  os_harness_firewall
}
