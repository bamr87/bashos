#!/usr/bin/env bash
# chui backup — snapshot every file chui touches into ~/.chui-backups/<stamp>/.
set -euo pipefail

BACKUP_ROOT="${CHUI_BACKUP_ROOT:-$HOME/.chui-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_ROOT}/${STAMP}"
CHUI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$DEST/oh-my-zsh-custom" "$DEST/terminal" "$DEST/zellij"

copy_if() {
  local src=$1 dst=$2
  if [[ -e $src || -L $src ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

copy_if "$HOME/.zshrc" "$DEST/.zshrc"
copy_if "$HOME/.zshenv" "$DEST/.zshenv"
copy_if "$HOME/.zshrc.pre-oh-my-zsh" "$DEST/.zshrc.pre-oh-my-zsh"
copy_if "$HOME/.zprofile" "$DEST/.zprofile"
copy_if "$HOME/.zlogin" "$DEST/.zlogin"
copy_if "$HOME/.p10k.zsh" "$DEST/.p10k.zsh"
copy_if "$HOME/.gitconfig" "$DEST/.gitconfig"
copy_if "$HOME/.config/zellij/config.kdl" "$DEST/zellij/config.kdl"
copy_if "$HOME/.config/zellij/layouts/home.kdl" "$DEST/zellij/layouts/home.kdl"
copy_if "$HOME/.config/chui/local.zsh" "$DEST/chui/local.zsh"
copy_if "$HOME/.local/bin/chui" "$DEST/bin/chui"
copy_if "$HOME/.local/bin/chui-home" "$DEST/bin/chui-home"
copy_if "$HOME/Library/Application Support/Code/User/keybindings.json" "$DEST/vscode/keybindings.json"

if [[ -d $HOME/.oh-my-zsh/custom ]]; then
  cp -a "$HOME/.oh-my-zsh/custom/." "$DEST/oh-my-zsh-custom/"
fi

if command -v defaults >/dev/null; then
  defaults export com.apple.Terminal "$DEST/terminal/com.apple.Terminal.plist" 2>/dev/null || true
fi

# format=2: the snapshot records every path chui links, so a missing file means "did not
# exist" and uninstall.sh may remove chui's link there. Older snapshots never get that.
{
  echo "format=2"
  echo "stamp=$STAMP"
  echo "host=$(hostname)"
  echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "term=${TERM_PROGRAM:-unknown}"
  echo "user=$USER"
  echo "chui=$CHUI_ROOT@$(git -C "$CHUI_ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
} >"$DEST/MANIFEST.txt"

echo "backup: $DEST"
