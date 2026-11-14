# os/install/console.sh — tty1 (on Amrchy, a window on the desktop) and interactive ssh logins
# attach the shared tmux console, and tmux starts from bashOS's defaults. Each change is a managed
# block in a user dotfile, or a file bashOS owns whole.
# shellcheck shell=bash disable=SC2154  # the _os_* colours come from lib.sh, which install.sh sources first

# The login file a shell reads for a login on tty1, and the rc file for an interactive ssh login.
# Debian's bash skeleton has ~/.profile and no ~/.bash_profile: creating one would shadow it.
os_login_file() {
  case $(os_user_shell "$OS_USER") in
    zsh) printf '%s' "$OS_HOME/.zprofile" ;;
    *) if [[ -f $OS_HOME/.bash_profile ]]; then printf '%s' "$OS_HOME/.bash_profile"; else printf '%s' "$OS_HOME/.profile"; fi ;;
  esac
}
os_rc_file() {
  case $(os_user_shell "$OS_USER") in
    zsh) printf '%s' "$OS_HOME/.zshrc" ;;
    *) printf '%s' "$OS_HOME/.bashrc" ;;
  esac
}

# An earlier hand-made hook does the same job (forge's console-mirror blocks): adopt it.
os_hook_elsewhere() {
  local file=$1 pattern=$2
  [[ -f $file ]] || return 1
  awk -v b="$OS_BEGIN" -v e="$OS_END" '$0 == b { s = 1 } !s { print } $0 == e { s = 0 }' "$file" | grep -q -- "$pattern"
}

phase_console() {
  os_step "console"
  local login rc
  login=$(os_login_file)
  rc=$(os_rc_file)

  local mode
  mode=$(os_console_mode)
  if [[ $mode == off || $mode == desktop ]]; then
    os_log "console $mode: no tty1 hook"
    os_block_drop "$login"
  elif os_hook_elsewhere "$login" /dev/tty1; then
    os_ok "tty1 hook already in ${login/#$OS_HOME/\~} — kept (the heal timer adds the bashos window)"
  else
    os_block_put "$login" '# tty1 is the physical monitor: it shows the shared tmux console (bashos-console).
if [ "$(tty)" = /dev/tty1 ] && [ -z "${TMUX:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -x /usr/local/bin/bashos-console ]; then
  exec /usr/local/bin/bashos-console
fi'
  fi

  if [[ ${BASHOS_CONSOLE_SSH_JOIN:-yes} != yes ]]; then
    os_block_drop "$rc"
  elif os_hook_elsewhere "$rc" SSH_CONNECTION; then
    os_ok "ssh join already in ${rc/#$OS_HOME/\~} — kept"
  else
    os_block_put "$rc" '# Interactive ssh logins join the monitor'"'"'s tmux console. Escape hatch: ssh -t HOST NOTMUX=1 bash -l
if [ -n "${SSH_CONNECTION:-}" ] && [ -z "${TMUX:-}" ] && [ -z "${NOTMUX:-}" ] && [ -t 0 ] && [ -x /usr/local/bin/bashos-console ]; then
  case $- in *i*) exec /usr/local/bin/bashos-console --attach ;; esac
fi'
  fi

  # tmux reads bashOS's defaults first, so every line the user wrote below still wins.
  os_block_put "$OS_HOME/.tmux.conf" "source-file -q $BASHOS_OS_PATH/os/config/tmux.conf" top

  os_desktop_console "$mode"
  [[ ${BASHOS_CONSOLE_VNC:-no} == yes ]] && os_vnc_conf
  return 0
}

# On Amrchy's desktop (BASHOS_CONSOLE=desktop, what `auto` means there) the shared console opens in
# a terminal window when Hyprland starts, and the app launcher lists the console and the bashOS
# desktop. The autostart line is a managed block in the user's own hypr/autostart.lua; the
# launchers are files bashOS owns whole. Any other mode removes all three.
OS_CONSOLE_APP=org.bashos.console
os_desktop_console() {
  local mode=$1 apps="$OS_HOME/.local/share/applications" autostart="$OS_HOME/.config/hypr/autostart.lua"
  if [[ $mode != desktop ]]; then
    os_block_drop "$autostart" --
    rm -f "$apps/bashos-console.desktop" "$apps/bashos.desktop"
    return 0
  fi
  if [[ -f $autostart ]]; then
    os_block_put "$autostart" "-- The shared bashOS console (tmux session ${BASHOS_CONSOLE_SESSION:-console}) in a terminal at login.
o.launch_on_start(\"xdg-terminal-exec --app-id=$OS_CONSOLE_APP -e /usr/local/bin/bashos-console --attach\")" bottom --
  else
    os_warn "no ~/.config/hypr/autostart.lua — the console does not open at login (bashos-console --attach does)"
  fi
  os_user_write "$apps/bashos-console.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=bashOS Console
Comment=The machine's shared tmux console: the session the desktop and every ssh login see
Exec=xdg-terminal-exec --app-id=$OS_CONSOLE_APP -e /usr/local/bin/bashos-console --attach
Icon=utilities-terminal
Terminal=false
Categories=System;TerminalEmulator;
EOF
  os_user_write "$apps/bashos.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=bashOS
Comment=The bashOS desktop: slash commands, the engine, health and trace in one terminal
Exec=xdg-terminal-exec --app-id=org.bashos.desktop -e /usr/local/bin/bashos
Icon=utilities-terminal
Terminal=false
Categories=Development;System;
EOF
}

# The kiosk's VNC account (BASHOS_CONSOLE_VNC=yes): mode 0600, created once with a generated
# password, never rewritten and never printed. bashos-console binds wayvnc to loopback.
os_vnc_conf() {
  local conf="$OS_HOME/.config/bashos/wayvnc.conf" pw
  if [[ -f $conf ]]; then
    os_log "${_os_d}kept${_os_0} ${conf/#$OS_HOME/\~}"
    return 0
  fi
  if os_dry; then
    os_run "create ${conf/#$OS_HOME/\~} (0600, a generated password)"
    return 0
  fi
  pw=$(head -c 30 /dev/urandom | base64 | tr -d '/+=\n')
  mkdir -p "$(dirname "$conf")"
  (umask 077 && cat >"$conf" <<EOF
# wayvnc for the kiosk (BASHOS_CONSOLE_VNC=yes) — mode 0600, never committed. bashos-console
# binds it to 127.0.0.1, so it is reached through ssh, and the tunnel is the encryption: Apple
# Diffie-Hellman (relax_encryption) is the password scheme macOS Screen Sharing speaks.
enable_auth=true
relax_encryption=true
username=$OS_USER
password=${pw:0:20}
EOF
  )
  os_ok "created ${conf/#$OS_HOME/\~} (0600) — the VNC password is in it"
}
