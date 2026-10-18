#!/usr/bin/env bash
# chui installer — idempotent, safe to re-run. `--dry-run` shows the plan and changes nothing.
set -euo pipefail

CHUI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
# shellcheck source=lib.sh
source "$CHUI_ROOT/lib.sh"

NO_BACKUP=0
SKIP_BREW=0
NO_TERMINAL=0
DRY_RUN=0
STAMP="$(date +%Y%m%d-%H%M%S)"

usage() {
  cat <<'EOF'
Usage: chui install [options]      (or: ./install.sh)
  -n, --dry-run   print what would change; change nothing
  --no-backup     skip the config snapshot (an existing real file is still moved aside)
  --skip-brew     skip brew bundle
  --no-terminal   leave Apple Terminal and VS Code alone (font, key maps)
  -h, --help      this help
EOF
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--dry-run) DRY_RUN=1 ;;
    --no-backup) NO_BACKUP=1 ;;
    --skip-brew) SKIP_BREW=1 ;;
    --no-terminal) NO_TERMINAL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

log() { printf '==> %s\n' "$*"; }
plan() { printf 'plan: %s\n' "$*"; }

# run CMD... — run it, or under --dry-run print it.
run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    plan "$*"
  else
    "$@"
  fi
}

link() {
  local src=$1 dest=$2 was=""
  if [[ -L $dest ]]; then
    was=$(readlink "$dest")
    if [[ $was == "$src" ]]; then
      log "ok    $dest"
      return 0
    fi
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    if [[ -n $was ]]; then
      plan "relink $dest -> $src  (was $was)"
    elif [[ -e $dest ]]; then
      plan "move $dest -> $dest.chui-$STAMP, then link -> $src"
    else
      plan "link $dest -> $src"
    fi
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  if [[ -e $dest && ! -L $dest ]]; then
    # Never delete a real file: a snapshot may not exist (--no-backup, or a path backup.sh
    # does not cover), so keep the original beside the link.
    mv "$dest" "$dest.chui-$STAMP"
    log "moved $dest -> $dest.chui-$STAMP"
  fi
  ln -sfn "$src" "$dest"
  if [[ -n $was ]]; then
    log "relink $dest -> $src  (was $was)"
  else
    log "link  $dest -> $src"
  fi
}

clone_if_missing() {
  local url=$1 dest=$2
  if [[ -d $dest/.git ]]; then
    log "have  $(basename "$dest")"
    return 0
  fi
  log "clone $url"
  run git clone --depth=1 "$url" "$dest"
}

DARWIN=0
[[ $(uname -s) == Darwin ]] && DARWIN=1
if [[ $DARWIN -eq 0 ]]; then
  log "not macOS: shell, prompt and Zellij install; Apple Terminal steps are skipped"
fi
[[ $DRY_RUN -eq 1 ]] && log "dry run — nothing will change"

if [[ $NO_BACKUP -eq 0 ]]; then
  log "backup"
  if [[ $DRY_RUN -eq 1 ]]; then
    plan "$CHUI_ROOT/backup.sh  → ${CHUI_BACKUP_ROOT:-$HOME/.chui-backups}/$STAMP"
  else
    "$CHUI_ROOT/backup.sh" >/dev/null
  fi
fi

if [[ $SKIP_BREW -eq 0 ]]; then
  if ! command -v brew >/dev/null; then
    echo "homebrew required: https://brew.sh  (or re-run with --skip-brew)" >&2
    exit 4
  fi
  log "brew bundle"
  run brew bundle install --file="$CHUI_ROOT/Brewfile"
fi

if [[ ! -d $HOME/.oh-my-zsh ]]; then
  log "install oh-my-zsh"
  if [[ $DRY_RUN -eq 1 ]]; then
    plan "oh-my-zsh installer (RUNZSH=no CHSH=no KEEP_ZSHRC=yes)"
  else
    RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
  fi
fi

# custom/plugins.txt is the list: "<github owner/repo>  <path under $ZSH_CUSTOM>".
while read -r repo dest; do
  [[ -n $repo && $repo != \#* ]] || continue
  clone_if_missing "https://github.com/$repo.git" "$ZSH_CUSTOM/$dest"
done <"$CHUI_ROOT/custom/plugins.txt"

while IFS='|' read -r rel dest; do
  link "$CHUI_ROOT/$rel" "$dest"
done < <(chui_links)

if command -v git >/dev/null; then
  run git config --global core.pager delta
  run git config --global interactive.diffFilter "delta --color-only"
  run git config --global delta.navigate true
  run git config --global delta.side-by-side true
  run git config --global merge.conflictstyle zdiff3
  log "git delta configured"
fi

if [[ $DARWIN -eq 1 && $NO_TERMINAL -eq 0 ]]; then
  font=$(chui_local_get CHUI_FONT_NAME)
  log "terminal font"
  CHUI_FONT_NAME="${font:-MesloLGS Nerd Font}" run bash "$CHUI_ROOT/config/terminal/macos-font.sh" || true
  if command -v python3 >/dev/null; then
    log "macos terminal keys"
    run python3 "$CHUI_ROOT/config/terminal/macos-keys.py"
    log "vscode terminal keys"
    run python3 "$CHUI_ROOT/config/terminal/vscode-keys.py"
  fi
elif [[ $NO_TERMINAL -eq 1 ]]; then
  log "terminal + vscode settings left alone (--no-terminal)"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  log "dry run done. install for real: chui install"
else
  log "done. open a new terminal or: exec zsh"
  log "verify: chui check"
fi
