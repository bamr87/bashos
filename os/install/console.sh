# os/install/console.sh — tty1 and interactive ssh logins attach the shared tmux console, and
# tmux starts from bashOS's defaults. Each change is a managed block in a user dotfile.
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

  if [[ ${BASHOS_CONSOLE:-auto} == off ]]; then
    os_log "console off: no tty1 hook"
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
}
