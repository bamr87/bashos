#!/usr/bin/env bash
set -euo pipefail

CHUI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
NO_BACKUP=0
SKIP_BREW=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]
  --no-backup   skip config snapshot
  --skip-brew   skip brew bundle
  -h, --help    this help
EOF
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --no-backup) NO_BACKUP=1 ;;
    --skip-brew) SKIP_BREW=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

log() { printf '==> %s\n' "$*"; }

link() {
  local src=$1 dest=$2
  mkdir -p "$(dirname "$dest")"
  if [[ -e $dest && ! -L $dest ]]; then
    rm -rf "$dest"
  fi
  ln -sfn "$src" "$dest"
  log "link $dest -> $src"
}

clone_if_missing() {
  local url=$1 dest=$2
  if [[ -d $dest/.git ]]; then
    log "have $(basename "$dest")"
    return 0
  fi
  log "clone $url"
  git clone --depth=1 "$url" "$dest"
}

if [[ $NO_BACKUP -eq 0 ]]; then
  log "backup"
  "$CHUI_ROOT/backup.sh" >/dev/null
fi

if [[ $SKIP_BREW -eq 0 ]]; then
  if ! command -v brew >/dev/null; then
    echo "homebrew required: https://brew.sh" >&2
    exit 4
  fi
  log "brew bundle"
  brew bundle install --file="$CHUI_ROOT/Brewfile"
fi

if [[ ! -d $HOME/.oh-my-zsh ]]; then
  log "install oh-my-zsh"
  RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
fi

clone_if_missing https://github.com/romkatv/powerlevel10k.git "$ZSH_CUSTOM/themes/powerlevel10k"
clone_if_missing https://github.com/zsh-users/zsh-autosuggestions "$ZSH_CUSTOM/plugins/zsh-autosuggestions"
clone_if_missing https://github.com/zsh-users/zsh-syntax-highlighting.git "$ZSH_CUSTOM/plugins/zsh-syntax-highlighting"
clone_if_missing https://github.com/Aloxaf/fzf-tab "$ZSH_CUSTOM/plugins/fzf-tab"

link "$CHUI_ROOT/config/zshrc" "$HOME/.zshrc"
link "$CHUI_ROOT/config/zshenv" "$HOME/.zshenv"
link "$CHUI_ROOT/config/p10k.zsh" "$HOME/.p10k.zsh"
link "$CHUI_ROOT/custom/forge.zsh" "$ZSH_CUSTOM/forge.zsh"
link "$CHUI_ROOT/config/zellij/config.kdl" "$HOME/.config/zellij/config.kdl"
link "$CHUI_ROOT/config/zellij/layouts/home.kdl" "$HOME/.config/zellij/layouts/home.kdl"
mkdir -p "$HOME/.local/bin"
link "$CHUI_ROOT/tui.sh" "$HOME/.local/bin/chui"
link "$CHUI_ROOT/config/home.sh" "$HOME/.local/bin/chui-home"

if command -v git >/dev/null; then
  git config --global core.pager delta
  git config --global interactive.diffFilter "delta --color-only"
  git config --global delta.navigate true
  git config --global delta.side-by-side true
  git config --global merge.conflictstyle zdiff3
  log "git delta configured"
fi

if command -v osascript >/dev/null; then
  log "terminal font"
  bash "$CHUI_ROOT/config/terminal/macos-font.sh" || true
fi

if command -v python3 >/dev/null; then
  log "macos terminal keys"
  python3 "$CHUI_ROOT/config/terminal/macos-keys.py"
  log "vscode terminal keys"
  python3 "$CHUI_ROOT/config/terminal/vscode-keys.py"
fi

log "done. open a new terminal or: exec zsh"
log "verify: $CHUI_ROOT/check.sh"
