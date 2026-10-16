#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${CHUI_BACKUP_ROOT:-$HOME/.chui-backups}"
STAMP="${1:-}"

if [[ -z $STAMP ]]; then
  STAMP="$(ls -1 "$BACKUP_ROOT" 2>/dev/null | tail -1 || true)"
fi

if [[ -z $STAMP || ! -d $BACKUP_ROOT/$STAMP ]]; then
  echo "no backup found in $BACKUP_ROOT" >&2
  exit 1
fi

SRC="$BACKUP_ROOT/$STAMP"
echo "restore from $SRC"

restore() {
  local from=$1 to=$2
  [[ -e $from || -L $from ]] || return 0
  mkdir -p "$(dirname "$to")"
  rm -rf "$to"
  cp -a "$from" "$to"
}

restore "$SRC/.zshrc" "$HOME/.zshrc"
restore "$SRC/.zshenv" "$HOME/.zshenv"
restore "$SRC/.zprofile" "$HOME/.zprofile"
restore "$SRC/.p10k.zsh" "$HOME/.p10k.zsh"
restore "$SRC/.gitconfig" "$HOME/.gitconfig"
restore "$SRC/zellij/config.kdl" "$HOME/.config/zellij/config.kdl"
restore "$SRC/vscode/keybindings.json" "$HOME/Library/Application Support/Code/User/keybindings.json"

if [[ -d $SRC/oh-my-zsh-custom && -d $HOME/.oh-my-zsh/custom ]]; then
  rm -rf "$HOME/.oh-my-zsh/custom"
  mkdir -p "$HOME/.oh-my-zsh/custom"
  cp -a "$SRC/oh-my-zsh-custom/." "$HOME/.oh-my-zsh/custom/"
fi

if [[ -f $SRC/terminal/com.apple.Terminal.plist ]] && command -v defaults >/dev/null; then
  defaults import com.apple.Terminal "$SRC/terminal/com.apple.Terminal.plist" 2>/dev/null || true
fi

echo "restored. open a new terminal or: exec zsh"
