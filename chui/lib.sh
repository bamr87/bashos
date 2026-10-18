# chui/lib.sh — helpers shared by tui.sh, install.sh and check.sh. Sourced, never run.
# shellcheck shell=bash

CHUI_LOCAL="${CHUI_LOCAL:-$HOME/.config/chui/local.zsh}"

# Settings chui owns in local.zsh. Every other line in that file belongs to the user (or
# to tools such as the bamr87 hub's setup-terminal.sh) and is never rewritten.
CHUI_KEYS="CHUI_ICONS CHUI_NO_FETCH CHUI_HOME_MAP BAT_THEME CHUI_FONT_NAME CHUI_ZELLIJ_KEYS"
CHUI_BEGIN="# >>> chui managed — edit with: chui configure >>>"
CHUI_END="# <<< chui managed <<<"

# chui_local_get KEY — print KEY's value from local.zsh without sourcing the file (it is
# zsh, and may source other zsh files). Only the `export KEY=value` form chui writes is read.
chui_local_get() {
  local key=$1 line val=""
  [[ -f $CHUI_LOCAL ]] || return 0
  line=$(grep -E "^export ${key}=" "$CHUI_LOCAL" 2>/dev/null | tail -1) || true
  [[ -n $line ]] || return 0
  # The value was written with printf %q, which is designed to be read back by eval.
  eval "val=${line#export "${key}"=}" 2>/dev/null || val=""
  printf '%s' "$val"
}

# chui_local_write — rewrite only chui's block in local.zsh from the current shell values of
# $CHUI_KEYS, keeping every other line. Lines from the pre-block format ("# managed by chui
# TUI" plus bare exports of chui's keys) are folded into the block.
chui_local_write() {
  local tmp key keys_re
  # shellcheck disable=SC2086  # CHUI_KEYS is a word list
  keys_re=$(printf '%s|' $CHUI_KEYS)
  keys_re="^export (${keys_re%|})="
  mkdir -p "$(dirname "$CHUI_LOCAL")"
  tmp=$(mktemp)
  if [[ -f $CHUI_LOCAL ]]; then
    awk -v b="$CHUI_BEGIN" -v e="$CHUI_END" -v k="$keys_re" '
      $0 == b { skip = 1; next }
      $0 == e { skip = 0; next }
      skip { next }
      /^# managed by chui TUI/ { next }
      $0 ~ k { next }
      { print }
    ' "$CHUI_LOCAL" >"$tmp"
  fi
  {
    printf '%s\n' "$CHUI_BEGIN"
    for key in $CHUI_KEYS; do
      printf 'export %s=%q\n' "$key" "${!key:-}"
    done
    printf '%s\n' "$CHUI_END"
  } >>"$tmp"
  mv "$tmp" "$CHUI_LOCAL"
}

# chui_zellij_config — the Zellij config file this machine uses, from CHUI_ZELLIJ_KEYS:
# classic (the default: ctrl+p/t/n/o/q pick modes) or unlock-first (keys v1).
chui_zellij_config() {
  local mode=${CHUI_ZELLIJ_KEYS:-$(chui_local_get CHUI_ZELLIJ_KEYS)}
  case $mode in
    unlock-first) printf 'config.unlock-first.kdl' ;;
    *) printf 'config.kdl' ;;
  esac
}

# chui_phys PATH — PATH with its directory resolved to a physical path (no symlinks), so two
# spellings of one checkout compare equal.
chui_phys() {
  local dir
  dir=$(cd "$(dirname "$1")" 2>/dev/null && pwd -P) || { printf '%s' "$1"; return 0; }
  printf '%s/%s' "$dir" "$(basename "$1")"
}

# The links chui manages: "<path in repo>|<path under $HOME>". install.sh creates them,
# check.sh verifies them, uninstall.sh removes the ones a backup did not hold.
chui_links() {
  local zsh_custom=${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}
  cat <<EOF
config/zshrc|$HOME/.zshrc
config/zshenv|$HOME/.zshenv
config/p10k.zsh|$HOME/.p10k.zsh
custom/forge.zsh|$zsh_custom/forge.zsh
config/zellij/$(chui_zellij_config)|$HOME/.config/zellij/config.kdl
config/zellij/layouts/home.kdl|$HOME/.config/zellij/layouts/home.kdl
tui.sh|$HOME/.local/bin/chui
config/home.sh|$HOME/.local/bin/chui-home
EOF
}
