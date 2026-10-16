# chui

Rebuildable terminal CHUI for macOS: Oh My Zsh + Powerlevel10k + modern CLI + Zellij.

## From scratch

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh && gh auth login
gh repo clone bamr87/chui ~/github/chui
cd ~/github/chui && make backup && make install
exec zsh
```

Font must be **MesloLGS Nerd Font** (not SF Mono) or `ls` icons show as `?`. Install sets it; `chui doctor` verifies. **Quit Terminal.app** after install so keys apply.

## Everyday

| Command | What |
| --- | --- |
| `chui` | interactive menu (update / configure) |
| `chui home` | map `~` + next level (two columns when maximized) |
| `chui home open` | zellij layout: visible \| hidden + strays |
| `chui home sweep` | move `$HOME` strays into `~/Documents/Archive` |
| `hm` / `zh` | aliases for `chui home` / `chui home open` |
| `chui check` | verify install |
| `chui backup` | snapshot configs |
| `chui restore` | roll back last snapshot |
| `zj` | zellij |
| `lg` | lazygit |
| `btop` | processes |
| `z <dir>` | jump (zoxide) |
| `forge` | remote dev box |
| `chui keys` | keyboard shortcuts |
| `chui update` | git pull + reinstall |
| `chui configure` | icons, splash, font, theme |

Prefs live in `~/.config/chui/local.zsh` (not git). TUI: **↑↓** choose · **enter** · **esc** back.

Maximize the window, then `hm`. Finder hides dotfiles; a plain `ls` hides the next level and file size. The map splits **visible** vs **hidden**, expands one level down, flags **LARGE** files, and tags **stray** items that should not live at `$HOME` root. `chui home sweep` moves selected strays to `~/Documents/Archive` (nothing is deleted). Set `CHUI_HOME_MAP=1` to show the map when a new shell starts in `~`.

**Keys:** ⌘←/→ line · ⌥←/→ word · ⌘⌫ kill to start · ⌃R fuzzy history. Full list: [docs/KEYS.md](docs/KEYS.md).

## Layout

```
Brewfile              packages
install.sh            idempotent bootstrap
backup.sh             ~/.chui-backups/<stamp>
uninstall.sh          restore latest backup
check.sh              smoke test
config/zshrc          linked to ~/.zshrc
config/zshenv         linked to ~/.zshenv (disables session restore)
config/p10k.zsh       linked to ~/.p10k.zsh
config/aliases.zsh
config/functions.zsh
config/keybindings.zsh
config/terminal/      Apple Terminal + VS Code key maps
config/zellij/        config + home layout
config/home.sh        $HOME map / sweep
custom/forge.zsh      linked into oh-my-zsh custom
```

Backups live in `~/.chui-backups/` (not in git). Secrets are never committed.

## Rollback

```bash
cd ~/github/chui && make uninstall
```
