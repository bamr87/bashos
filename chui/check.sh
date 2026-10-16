#!/usr/bin/env bash
set -u

fail=0
ok() { printf '  [ok] %s\n' "$1"; }
bad() { printf '  [!!] %s\n' "$1"; fail=1; }

CHUI_ROOT="${CHUI_ROOT:-$(cd "$(dirname "$0")" && pwd)}"

echo "chui check"

[[ -L $HOME/.zshrc && $(readlink "$HOME/.zshrc") == *chui/config/zshrc ]] && ok "zshrc symlink" || bad "zshrc not linked to chui"
[[ -L $HOME/.zshenv && $(readlink "$HOME/.zshenv") == *chui/config/zshenv ]] && ok "zshenv symlink" || bad "zshenv not linked to chui"
[[ -L $HOME/.p10k.zsh ]] && ok "p10k symlink" || bad "p10k not linked"
[[ -d $HOME/.oh-my-zsh ]] && ok "oh-my-zsh" || bad "oh-my-zsh missing"
[[ -d $HOME/.oh-my-zsh/custom/themes/powerlevel10k ]] && ok "powerlevel10k" || bad "powerlevel10k missing"
[[ -d $HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions ]] && ok "autosuggestions" || bad "autosuggestions missing"
[[ -d $HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting ]] && ok "syntax-highlighting" || bad "syntax-highlighting missing"
[[ -d $HOME/.oh-my-zsh/custom/plugins/fzf-tab ]] && ok "fzf-tab" || bad "fzf-tab missing"
[[ -e $HOME/.oh-my-zsh/custom/forge.zsh ]] && ok "forge.zsh" || bad "forge.zsh missing"
[[ -L $HOME/.config/zellij/config.kdl ]] && ok "zellij config" || bad "zellij config not linked"
[[ -L $HOME/.config/zellij/layouts/home.kdl ]] && ok "zellij home layout" || bad "zellij home layout not linked"
[[ -L $HOME/.local/bin/chui-home && -x $CHUI_ROOT/config/home.sh ]] && ok "chui-home" || bad "chui-home missing"

for cmd in zsh brew git eza bat fd fzf zoxide delta btop lazygit fastfetch zellij gum; do
  command -v "$cmd" >/dev/null && ok "$cmd" || bad "$cmd missing"
done

if [[ -L $HOME/.zshrc ]]; then
  grep -q 'ZSH_THEME="powerlevel10k/powerlevel10k"' "$HOME/.zshrc" && ok "theme p10k" || bad "theme not p10k"
  grep -q 'keybindings.zsh' "$HOME/.zshrc" && ok "keybindings sourced" || bad "keybindings not sourced"
  grep -q 'completions.zsh' "$HOME/.zshrc" && ok "completions sourced" || bad "completions not sourced"
fi
[[ -f ${CHUI_ROOT:-$HOME/github/chui}/config/keybindings.zsh ]] && ok "keybindings.zsh" || bad "keybindings.zsh missing"
if command -v osascript >/dev/null; then
  font=$(osascript -e 'tell application "Terminal" to get font name of default settings' 2>/dev/null || true)
  [[ $font == *Meslo* || $font == *Nerd* || $font == *NF* ]] && ok "terminal font $font" || bad "terminal font is ${font:-unknown} (want MesloLGS Nerd Font)"
fi

echo
if [[ $fail -eq 0 ]]; then
  echo "all checks passed"
  exit 0
fi
echo "some checks failed"
exit 1
