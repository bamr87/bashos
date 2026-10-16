#!/usr/bin/env bash
# chui check — verify the install. Exits 1 on any [!!]; [--] lines are advice only.
set -u

CHUI_ROOT="${CHUI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
# shellcheck source=lib.sh
source "$CHUI_ROOT/lib.sh"

fail=0
ok() { printf '  [ok] %s\n' "$1"; }
bad() { printf '  [!!] %s\n' "$1"; fail=1; }
note() { printf '  [--] %s\n' "$1"; }

# chk CONDITION... -- OK-TEXT BAD-TEXT
chk() {
  local args=()
  while [[ $1 != -- ]]; do args+=("$1"); shift; done
  shift
  if "${args[@]}"; then ok "$1"; else bad "$2"; fi
}

echo "chui check  ($CHUI_ROOT)"

# Every link must point into THIS checkout. One that points into another chui (say the old
# standalone ~/github/chui clone) still works today, but stops tracking this tree.
here=$(chui_phys "$CHUI_ROOT/x")
here=${here%/x}
while IFS='|' read -r rel dest; do
  name=${dest/#$HOME/\~}
  if [[ ! -L $dest ]]; then
    bad "$name not linked to chui  (run: chui install)"
    continue
  fi
  target=$(readlink "$dest")
  [[ $target == /* ]] || target="$(dirname "$dest")/$target"
  target=$(chui_phys "$target")
  case $rel in
    config/zellij/config*.kdl) want="$here/config/zellij/" ;;
    *) want="$here/$rel" ;;
  esac
  if [[ $target == "$want"* ]]; then
    ok "$name"
  elif [[ $target == */chui/* ]]; then
    bad "$name links another checkout: $target  (run: chui install)"
  else
    bad "$name points at $target, not chui"
  fi
done < <(chui_links)

chk test -d "$HOME/.oh-my-zsh" -- "oh-my-zsh" "oh-my-zsh missing"
while read -r _ dest; do
  [[ -n $dest ]] || continue
  chk test -d "$ZSH_CUSTOM/$dest" -- "$(basename "$dest")" "$(basename "$dest") missing"
done <"$CHUI_ROOT/custom/plugins.txt"

for cmd in zsh brew git eza bat fd fzf zoxide delta btop lazygit fastfetch zellij gum; do
  if command -v "$cmd" >/dev/null; then ok "$cmd"; else bad "$cmd missing  (run: chui install)"; fi
done

if [[ -L $HOME/.zshrc ]]; then
  chk grep -q 'ZSH_THEME="powerlevel10k/powerlevel10k"' "$HOME/.zshrc" -- "theme p10k" "theme not p10k"
  chk grep -q 'keybindings.zsh' "$HOME/.zshrc" -- "keybindings sourced" "keybindings not sourced"
  chk grep -q 'completions.zsh' "$HOME/.zshrc" -- "completions sourced" "completions not sourced"
fi

if [[ $(uname -s) == Darwin ]] && command -v osascript >/dev/null; then
  font=$(osascript -e 'tell application "Terminal" to get font name of default settings' 2>/dev/null || true)
  case $font in
    *Meslo* | *Nerd* | *NF*) ok "terminal font $font" ;;
    *) bad "terminal font is ${font:-unknown} (want MesloLGS Nerd Font: chui configure → Apply font)" ;;
  esac
fi

# Advice: settings that only matter for keys v1 (docs/TERMINAL-FRAMEWORK.md §6.1).
note "zellij keys: $(chui_zellij_config | sed 's/config.kdl/classic/; s/config.unlock-first.kdl/unlock-first/')  (chui configure → Zellij keys)"
vscode="$HOME/Library/Application Support/Code/User/settings.json"
if [[ -f $vscode ]] && ! grep -Eq '"terminal\.integrated\.macOptionIsMeta"[[:space:]]*:[[:space:]]*true' "$vscode"; then
  note "VS Code: set \"terminal.integrated.macOptionIsMeta\": true for alt+key chords in TUIs"
fi

echo
if [[ $fail -eq 0 ]]; then
  echo "all checks passed"
  exit 0
fi
echo "some checks failed"
exit 1
