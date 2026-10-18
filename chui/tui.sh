#!/usr/bin/env bash
# chui — the menu and every subcommand. On PATH as ~/.local/bin/chui; also `bashos chui …`.
set -u

_src="${BASH_SOURCE[0]}"
while [[ -L $_src ]]; do
  _dir="$(cd "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ $_src == /* ]] || _src="$_dir/$_src"
done
ROOT="$(cd "$(dirname "$_src")" && pwd)"
unset _src _dir
export CHUI_ROOT="$ROOT"
# shellcheck source=lib.sh
source "$ROOT/lib.sh"
LOCAL="$CHUI_LOCAL"

interactive() { [[ -t 0 && -t 1 && -z ${CI:-} ]]; }

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
  interactive || return 0
  printf 'press enter… '
  read -r _
}

load_local() {
  local key val
  for key in $CHUI_KEYS; do
    val=$(chui_local_get "$key")
    printf -v "$key" '%s' "$val"
  done
  CHUI_ICONS="${CHUI_ICONS:-auto}"
  BAT_THEME="${BAT_THEME:-Catppuccin Mocha}"
  CHUI_FONT_NAME="${CHUI_FONT_NAME:-MesloLGS Nerd Font}"
  CHUI_ZELLIJ_KEYS="${CHUI_ZELLIJ_KEYS:-classic}"
}

write_local() {
  chui_local_write
  say "saved $LOCAL"
}

# Point ~/.config/zellij/config.kdl at the config for the chosen key mode.
relink_zellij() {
  local dest="$HOME/.config/zellij/config.kdl" src
  src="$ROOT/config/zellij/$(chui_zellij_config)"
  if [[ -e $dest && ! -L $dest ]]; then
    say "$dest is your own file, not chui's link: run chui install to adopt it"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  ln -sfn "$src" "$dest"
  say "zellij keys: ${CHUI_ZELLIJ_KEYS} (new zellij sessions pick it up)"
}

do_update() {
  say "backup + pull + install"
  "$ROOT/backup.sh" || true
  if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
    git -C "$ROOT" status -sb
    confirm "local changes exist. pull anyway?" || return 0
  fi
  if ! git -C "$ROOT" symbolic-ref -q HEAD >/dev/null; then
    # A detached checkout (e.g. bashos as a submodule): the parent repo owns its version.
    say "detached HEAD in $(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null): not pulling"
    confirm "reinstall from the current tree?" || return 0
  else
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
  fi
  "$ROOT/install.sh" --no-backup
  "$ROOT/check.sh" || true
  say "update complete. exec zsh or open a new terminal."
  pause
}

do_restore() {
  local stamp=${1:-}
  if [[ -z $stamp ]]; then
    stamp=$(ls -1 "${CHUI_BACKUP_ROOT:-$HOME/.chui-backups}" 2>/dev/null | tail -1 || true)
    [[ -n $stamp ]] || { say "no backups"; pause; return 0; }
    if interactive; then
      confirm "restore $stamp ?" || return 0
    fi
  fi
  "$ROOT/uninstall.sh" "$stamp"
  pause
}

do_font() {
  load_local
  local pick
  pick=$(
    {
      printf '%s\n' "MesloLGS Nerd Font" "MesloLGS Nerd Font Mono" "MesloLGM Nerd Font Mono"
      fc-list : family 2>/dev/null | tr ',' '\n' | sed 's/^ *//' | grep -i -E 'nerd|meslo' | sort -u
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

do_zellij_keys() {
  load_local
  say "classic       ctrl+p/t/n/o pick a mode, ctrl+q quits zellij"
  say "unlock-first  starts locked so every key reaches the app; ctrl+g, then p/t/r/o/q"
  local pick
  pick=$(choose classic unlock-first) || return 0
  [[ -n $pick ]] || return 0
  CHUI_ZELLIJ_KEYS=$pick
  write_local
  relink_zellij
  pause
}

do_configure() {
  load_local
  local item
  while true; do
    item=$(choose \
      "Icons          [${CHUI_ICONS}]" \
      "Splash         [$([[ -z ${CHUI_NO_FETCH:-} ]] && echo on || echo off)]" \
      "Home map       [$([[ -n ${CHUI_HOME_MAP:-} ]] && echo on || echo off)]" \
      "Font           [${CHUI_FONT_NAME}]" \
      "Bat theme      [${BAT_THEME}]" \
      "Zellij keys    [${CHUI_ZELLIJ_KEYS}]" \
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
      Zellij*) do_zellij_keys ;;
      "Apply keys")
        python3 "$ROOT/config/terminal/macos-keys.py"
        python3 "$ROOT/config/terminal/vscode-keys.py"
        pause
        ;;
      "Apply font")
        CHUI_FONT_NAME="${CHUI_FONT_NAME}" bash "$ROOT/config/terminal/macos-font.sh"
        pause
        ;;
      Edit*)
        ${EDITOR:-code --wait} "$LOCAL"
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

do_keys() {
  local pager=${1:-never}
  command bat --paging="$pager" --style=plain "$ROOT/docs/KEYS.md" 2>/dev/null \
    || if [[ $pager == always ]]; then command less "$ROOT/docs/KEYS.md"; else command cat "$ROOT/docs/KEYS.md"; fi
}

do_dash() {
  local c="" r="" b="" g="" line zv branch
  if [[ -t 1 && -z ${NO_COLOR:-} ]]; then
    c=$'\033[36m' r=$'\033[0m' b=$'\033[1m' g=$'\033[32m'
  fi
  line=$(printf '─%.0s' {1..56})
  zv=$(zsh --version 2>/dev/null | awk '{print $2}')
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '—')
  printf '%s╭%s╮%s\n' "$c" "$line" "$r"
  printf '%s│%s  %sCHUI%s  %s  %s\n' "$c" "$r" "$b" "$r" "$(hostname -s)" "$(date '+%Y-%m-%d %H:%M')"
  printf '%s├%s┤%s\n' "$c" "$line" "$r"
  printf '%s│%s  shell   %szsh %s%s + oh-my-zsh + p10k\n' "$c" "$r" "$g" "${zv:-?}" "$r"
  printf '%s│%s  tools   eza bat fd fzf zoxide delta gum\n' "$c" "$r"
  printf '%s│%s  tui     zellij (%s keys)  btop  lazygit  fastfetch\n' "$c" "$r" \
    "$(chui_zellij_config | sed 's/config.kdl/classic/; s/config.unlock-first.kdl/unlock-first/')"
  printf '%s│%s  git     %s\n' "$c" "$r" "$branch"
  printf '%s│%s  root    %s\n' "$c" "$r" "$ROOT"
  printf '%s╰%s╯%s\n' "$c" "$line" "$r"
  printf '  chui        menu (update / configure)\n'
}

usage() {
  cat <<'EOF'
chui                  interactive menu
chui install [opts]   install / re-link (--dry-run · --skip-brew · --no-backup · --no-terminal)
chui update           backup + pull + reinstall
chui configure        icons / splash / home map / font / bat theme / zellij keys
chui home [map|open|sweep]
                      $HOME map (visible + hidden + next level) · zellij layout · archive strays
chui dash             status box
chui keys             keyboard shortcuts
chui check            verify install (doctor is the same)
chui backup           snapshot configs
chui restore [stamp]  roll back to a snapshot (default: the latest)

hm                    chui home
zh                    chui home open
zj                    zellij workspace
lg                    lazygit
btop                  process TUI
ff                    fastfetch
forge                 remote dev box
proj <name>           jump to ~/github/<name>
note <text>           append to ~/.dev-notes
EOF
}

menu() {
  if ! interactive; then
    # Never sit in a menu on a pipe or in CI.
    usage
    return 0
  fi
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
      Keys) do_keys always ;;
      Edit) do_edit ;;
      Quit) exit 0 ;;
    esac
  done
}

cmd=${1:-menu}
[[ $# -gt 0 ]] && shift
case $cmd in
  menu|tui) menu ;;
  install) exec "$ROOT/install.sh" "$@" ;;
  update) do_update ;;
  configure)
    interactive || { echo "chui configure needs a terminal" >&2; exit 2; }
    do_configure
    ;;
  home) exec "$ROOT/config/home.sh" "$@" ;;
  dash) do_dash ;;
  keys) do_keys never ;;
  check|doctor) exec "$ROOT/check.sh" ;;
  backup) exec "$ROOT/backup.sh" ;;
  restore|uninstall) do_restore "$@" ;;
  help|-h|--help) usage ;;
  *)
    printf 'unknown: %s  (chui help)\n' "$cmd" >&2
    exit 2
    ;;
esac
