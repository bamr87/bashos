#!/usr/bin/env bash
# chui restore — roll back to a snapshot from backup.sh (default: the latest).
set -euo pipefail

BACKUP_ROOT="${CHUI_BACKUP_ROOT:-$HOME/.chui-backups}"

case ${1:-} in
  -h|--help)
    cat <<EOF
Usage: chui restore [stamp]      (or: ./uninstall.sh [stamp])
  Restore the files chui manages from $BACKUP_ROOT/<stamp> (default: the latest).
  Your ~/.config/chui/local.zsh is kept as it is; the snapshot holds a copy.
  Snapshots: $(ls -1 "$BACKUP_ROOT" 2>/dev/null | tr '\n' ' ')
EOF
    exit 0
    ;;
esac

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
FORMAT=1
grep -q '^format=2' "$SRC/MANIFEST.txt" 2>/dev/null && FORMAT=2

# A link chui made: one pointing into a chui checkout (this one, or the old bamr87/chui clone).
chui_owned() {
  [[ -L $1 ]] || return 1
  case $(readlink "$1") in
    */chui/*) return 0 ;;
  esac
  return 1
}

restore() {
  local from=$1 to=$2
  if [[ -e $from || -L $from ]]; then
    mkdir -p "$(dirname "$to")"
    rm -rf "$to"
    cp -a "$from" "$to"
    return 0
  fi
  # The snapshot has no copy. A format-2 snapshot records every chui path, so the file did
  # not exist then: drop chui's link rather than leave it dangling once chui is removed.
  if [[ $FORMAT -eq 2 ]] && chui_owned "$to"; then
    rm -f "$to"
    echo "removed $to"
  fi
}

restore "$SRC/.zshrc" "$HOME/.zshrc"
restore "$SRC/.zshenv" "$HOME/.zshenv"
restore "$SRC/.zprofile" "$HOME/.zprofile"
restore "$SRC/.p10k.zsh" "$HOME/.p10k.zsh"
restore "$SRC/.gitconfig" "$HOME/.gitconfig"
restore "$SRC/zellij/config.kdl" "$HOME/.config/zellij/config.kdl"
restore "$SRC/zellij/layouts/home.kdl" "$HOME/.config/zellij/layouts/home.kdl"
restore "$SRC/bin/chui" "$HOME/.local/bin/chui"
restore "$SRC/bin/chui-home" "$HOME/.local/bin/chui-home"
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
