mkcd() {
  mkdir -p "$1" && cd "$1"
}

proj() {
  local projects_dir="$HOME/github"
  if [[ -z "$1" ]]; then
    echo "Available projects:"
    ls -1 "$projects_dir" 2>/dev/null || echo "No projects found"
  elif [[ -d "$projects_dir/$1" ]]; then
    cd "$projects_dir/$1" && echo "Jumped to $1"
  else
    echo "Project '$1' not found"
    return 1
  fi
}

note() {
  local notes_dir="$HOME/.dev-notes"
  mkdir -p "$notes_dir"
  local today="$(date +%Y-%m-%d)"
  echo "[$(date +%H:%M)] $*" >> "$notes_dir/$today.md"
  echo "Note saved to $notes_dir/$today.md"
}

chui() {
  local cmd=${1:-menu}
  case $cmd in
    menu|tui|"")
      "${CHUI_ROOT}/tui.sh" menu
      [[ -f $HOME/.config/chui/local.zsh ]] && source "$HOME/.config/chui/local.zsh"
      [[ -f $CHUI_ROOT/config/aliases.zsh ]] && source "$CHUI_ROOT/config/aliases.zsh"
      ;;
    update)
      "${CHUI_ROOT}/tui.sh" update
      [[ -f $HOME/.config/chui/local.zsh ]] && source "$HOME/.config/chui/local.zsh"
      [[ -f $CHUI_ROOT/config/aliases.zsh ]] && source "$CHUI_ROOT/config/aliases.zsh"
      ;;
    configure)
      "${CHUI_ROOT}/tui.sh" configure
      [[ -f $HOME/.config/chui/local.zsh ]] && source "$HOME/.config/chui/local.zsh"
      [[ -f $CHUI_ROOT/config/aliases.zsh ]] && source "$CHUI_ROOT/config/aliases.zsh"
      ;;
    home)
      "${CHUI_ROOT}/config/home.sh" "${@:2}"
      ;;
    dash)
      local line
      line=$(printf '─%.0s' {1..56})
      print -P "%F{cyan}╭${line}╮%f"
      print -P "%F{cyan}│%f  %BCHUI%b  ${HOST:r}  $(date '+%Y-%m-%d %H:%M')"
      print -P "%F{cyan}├${line}┤%f"
      print -P "%F{cyan}│%f  shell   %F{green}zsh ${ZSH_VERSION}%f + oh-my-zsh + p10k"
      print -P "%F{cyan}│%f  tools   eza bat fd fzf zoxide delta gum"
      print -P "%F{cyan}│%f  tui     zellij  btop  lazygit  fastfetch"
      print -P "%F{cyan}│%f  git     $(command git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '—')"
      print -P "%F{cyan}│%f  root    ${CHUI_ROOT}"
      print -P "%F{cyan}╰${line}╯%f"
      print "  chui        menu (update / configure)"
      ;;
    help|-h|--help)
      cat <<'EOF'
chui              interactive menu
chui update       pull + reinstall
chui configure    icons / splash / font / theme
chui home         \$HOME map (visible + hidden + next level)
chui home open    maximized zellij layout
chui home sweep   move strays to ~/Documents/Archive
chui dash         status box
chui keys         keyboard shortcuts
chui doctor       font / icons / tools
chui check        verify install
chui backup       snapshot configs
chui restore      restore latest backup

hm                chui home
zh                chui home open
zj                zellij workspace
lg                lazygit
btop              process TUI
ff                fastfetch
forge             remote dev box
proj <name>       jump to ~/github/<name>
note <text>       append to ~/.dev-notes
EOF
      ;;
    keys)    command bat --paging=never --style=plain "${CHUI_ROOT}/docs/KEYS.md" 2>/dev/null || command cat "${CHUI_ROOT}/docs/KEYS.md" ;;
    doctor)
      print -P "%Bchui doctor%b"
      local font
      font=$(osascript -e 'tell application "Terminal" to get font name of default settings' 2>/dev/null || echo unknown)
      if [[ $font == *Meslo* || $font == *Nerd* || $font == *NF* ]]; then
        print -P "  %F{green}ok%f  font  $font"
      else
        print -P "  %F{red}!!%f  font  $font  (chui → Configure → Apply font)"
      fi
      "${CHUI_ROOT}/check.sh"
      ;;
    check)   "${CHUI_ROOT}/check.sh" ;;
    backup)  "${CHUI_ROOT}/backup.sh" ;;
    restore) "${CHUI_ROOT}/uninstall.sh" ;;
    *) echo "unknown: $cmd  (chui help)"; return 1 ;;
  esac
}
