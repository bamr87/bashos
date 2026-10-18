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

# chui lives in tui.sh (one CLI for zsh, bash, scripts and `bashos chui`). This wrapper
# only re-reads prefs afterwards, so a change made in the menu applies to this shell too.
chui() {
  "${CHUI_ROOT}/tui.sh" "$@"
  local rc=$?
  case ${1:-menu} in
    menu|tui|update|configure|install)
      [[ -f $HOME/.config/chui/local.zsh ]] && source "$HOME/.config/chui/local.zsh"
      [[ -f $CHUI_ROOT/config/aliases.zsh ]] && source "$CHUI_ROOT/config/aliases.zsh"
      ;;
  esac
  return $rc
}
