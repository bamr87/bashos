#!/usr/bin/env bash
set -u

_src="${BASH_SOURCE[0]}"
while [[ -L $_src ]]; do
  _dir="$(cd "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ $_src == /* ]] || _src="$_dir/$_src"
done
ROOT="$(cd "$(dirname "$_src")" && pwd)"
unset _src _dir
LOCAL="${CHUI_LOCAL:-$HOME/.config/chui/local.zsh}"
export CHUI_ROOT="$ROOT"

header() {
  local sha
  sha=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)
  if command -v gum >/dev/null; then
    gum style --foreground 14 --border-foreground 14 --border rounded --padding "0 2" --width 52 \
      "CHUI  ${sha}  $(hostname -s)"
  else
    printf '\n  CHUI  %s  %s\n\n' "$sha" "$(hostname -s)"
  fi
}

say() {
  if command -v gum >/dev/null; then
    gum style --foreground 15 "$1"
  else
    printf '%s\n' "$1"
  fi
}

choose() {
  if command -v gum >/dev/null; then
    gum choose "$@"
  elif command -v fzf >/dev/null; then
    printf '%s\n' "$@" | fzf --prompt 'chui> ' --height 16 --reverse --cycle
  else
    PS3='chui> '
    select item in "$@"; do
      [[ -n ${item:-} ]] && { printf '%s\n' "$item"; break; }
    done
  fi
}

confirm() {
  if command -v gum >/dev/null; then
    gum confirm "$1"
  else
    printf '%s [y/N] ' "$1"
    read -r ans
    [[ ${ans:-} == [yY] ]]
  fi
}

pause() {
  printf 'press enter… '
  read -r _
}

load_local() {
  if [[ -f $LOCAL ]]; then
    # shellcheck disable=SC1090
    source "$LOCAL"
  fi
  CHUI_ICONS="${CHUI_ICONS:-auto}"
  CHUI_NO_FETCH="${CHUI_NO_FETCH:-}"
  CHUI_HOME_MAP="${CHUI_HOME_MAP:-}"
  BAT_THEME="${BAT_THEME:-Catppuccin Mocha}"
  CHUI_FONT_NAME="${CHUI_FONT_NAME:-MesloLGS Nerd Font}"
}

write_local() {
  mkdir -p "$(dirname "$LOCAL")"
  cat >"$LOCAL" <<EOF
# managed by chui TUI — not in git
export CHUI_ICONS=$(printf '%q' "${CHUI_ICONS:-auto}")
export CHUI_NO_FETCH=$(printf '%q' "${CHUI_NO_FETCH:-}")
export CHUI_HOME_MAP=$(printf '%q' "${CHUI_HOME_MAP:-}")
export BAT_THEME=$(printf '%q' "${BAT_THEME:-Catppuccin Mocha}")
export CHUI_FONT_NAME=$(printf '%q' "${CHUI_FONT_NAME:-MesloLGS Nerd Font}")
EOF
  say "saved $LOCAL"
}

do_update() {
  say "backup + pull + install"
  "$ROOT/backup.sh" || true
  if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
    git -C "$ROOT" status -sb
    confirm "local changes exist. pull anyway?" || return 0
  fi
  if command -v gum >/dev/null; then
    gum spin --title "git fetch" -- git -C "$ROOT" fetch origin
  else
    git -C "$ROOT" fetch origin
  fi
  if ! git -C "$ROOT" pull --ff-only; then
    say "pull failed (not fast-forward). resolve in $ROOT"
    pause
    return 1
  fi
  "$ROOT/install.sh" --no-backup
  "$ROOT/check.sh" || true
  say "update complete. exec zsh or open a new terminal."
  pause
}

do_restore() {
  local stamp
  stamp=$(ls -1 "$HOME/.chui-backups" 2>/dev/null | tail -1 || true)
  [[ -n $stamp ]] || { say "no backups"; pause; return 0; }
  confirm "restore $stamp ?" || return 0
  "$ROOT/uninstall.sh" "$stamp"
  pause
}

do_font() {
  load_local
  local pick
  pick=$(
    {
      printf '%s\n' "MesloLGS Nerd Font" "MesloLGS Nerd Font Mono" "MesloLGM Nerd Font Mono"
      fc-list : family 2>/dev/null | tr ',' '\n' | sed 's/^ *//' | rg -i 'nerd|meslo' | sort -u
    } | awk 'NF && !seen[$0]++' | {
      if command -v gum >/dev/null; then gum filter --placeholder 'font'; else fzf --prompt 'font> '; fi
    }
  ) || return 0
  [[ -n $pick ]] || return 0
  CHUI_FONT_NAME=$pick
  write_local
  CHUI_FONT_NAME=$pick bash "$ROOT/config/terminal/macos-font.sh"
  pause
}

do_theme() {
  load_local
  local pick
  pick=$(bat --list-themes --color=never 2>/dev/null | sed 's/[: ].*//' | {
    if command -v gum >/dev/null; then gum filter --placeholder 'bat theme'; else fzf --prompt 'theme> '; fi
  }) || return 0
  [[ -n $pick ]] || return 0
  BAT_THEME=$pick
  write_local
  pause
}

do_configure() {
  load_local
  local item
  while true; do
    item=$(choose \
      "Icons          [${CHUI_ICONS:-auto}]" \
      "Splash         [$([[ -z ${CHUI_NO_FETCH:-} ]] && echo on || echo off)]" \
      "Home map       [$([[ -n ${CHUI_HOME_MAP:-} ]] && echo on || echo off)]" \
      "Font           [${CHUI_FONT_NAME:-MesloLGS Nerd Font}]" \
      "Bat theme      [${BAT_THEME:-Catppuccin Mocha}]" \
      "Apply keys" \
      "Apply font" \
      "Edit local.zsh" \
      "Back") || return 0
    case $item in
      Icons*)
        CHUI_ICONS=$(choose auto always never) || continue
        write_local
        ;;
      Splash*)
        if confirm "show fastfetch on new shells?"; then
          CHUI_NO_FETCH=
        else
          CHUI_NO_FETCH=1
        fi
        write_local
        ;;
      "Home map"*)
        if confirm "show \$HOME map when a new shell starts in ~ ?"; then
          CHUI_HOME_MAP=1
        else
          CHUI_HOME_MAP=
        fi
        write_local
        ;;
      Font*) do_font ;;
      Bat*) do_theme ;;
      "Apply keys")
        python3 "$ROOT/config/terminal/macos-keys.py"
        python3 "$ROOT/config/terminal/vscode-keys.py"
        pause
        ;;
      "Apply font")
        CHUI_FONT_NAME="${CHUI_FONT_NAME:-MesloLGS Nerd Font}" bash "$ROOT/config/terminal/macos-font.sh"
        pause
        ;;
      Edit*)
        ${EDITOR:-code --wait} "$LOCAL"
        load_local
        ;;
      Back) return 0 ;;
    esac
    load_local
  done
}

do_edit() {
  local item
  item=$(choose "aliases.zsh" "zshrc" "keybindings.zsh" "local.zsh" "p10k configure" "open repo" "Back") || return 0
  case $item in
    aliases.zsh) ${EDITOR:-code --wait} "$ROOT/config/aliases.zsh" ;;
    zshrc) ${EDITOR:-code --wait} "$ROOT/config/zshrc" ;;
    keybindings.zsh) ${EDITOR:-code --wait} "$ROOT/config/keybindings.zsh" ;;
    local.zsh)
      mkdir -p "$(dirname "$LOCAL")"
      touch "$LOCAL"
      ${EDITOR:-code --wait} "$LOCAL"
      ;;
    "p10k configure")
      say "run in zsh: p10k configure"
      pause
      ;;
    "open repo") command code "$ROOT" 2>/dev/null || command open "$ROOT" ;;
    Back) return 0 ;;
  esac
}

menu() {
  local item
  while true; do
    header
    item=$(choose \
      "Update" \
      "Home" \
      "Configure" \
      "Backup" \
      "Restore" \
      "Doctor" \
      "Keys" \
      "Edit" \
      "Quit") || exit 0
    case $item in
      Update) do_update ;;
      Home)
        "$ROOT/config/home.sh" map
        pause
        ;;
      Configure) do_configure ;;
      Backup) "$ROOT/backup.sh"; pause ;;
      Restore) do_restore ;;
      Doctor)
        "$ROOT/check.sh" || true
        pause
        ;;
      Keys)
        command bat --paging=always --style=plain "$ROOT/docs/KEYS.md" 2>/dev/null || command less "$ROOT/docs/KEYS.md"
        ;;
      Edit) do_edit ;;
      Quit) exit 0 ;;
    esac
  done
}

cmd=${1:-menu}
case $cmd in
  menu|tui|"") menu ;;
  update) do_update ;;
  configure) do_configure ;;
  home) exec "$ROOT/config/home.sh" "${@:2}" ;;
  *)
    printf 'usage: chui [menu|update|configure|home]\n' >&2
    exit 2
    ;;
esac
