# chui

> The optional macOS terminal environment of bashOS — Oh My Zsh, Powerlevel10k, Zellij and the modern CLI — and how to install, use, configure and roll it back.

The macOS terminal environment of bashOS: Oh My Zsh + Powerlevel10k + modern CLI + Zellij, rebuildable from this directory. It is the environment layer (L0) the bashOS desktop and every fleet TUI run in. Formerly the standalone `bamr87/chui` repo, merged here with its history.

## From scratch

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh && gh auth login
gh repo clone bamr87/bashos ~/github/bashos
~/github/bashos/bin/bashos chui install --dry-run   # see every change first
~/github/bashos/bin/bashos chui install
exec zsh
```

`bin/bashos chui …` is plain shell, so it runs before bashOS's Python virtualenv exists. From inside `chui/`, `make dry-run` and `make install` do the same.

Font must be **MesloLGS Nerd Font** (not SF Mono) or `ls` icons show as `?`. Install sets it, and `chui check` verifies it. **Quit Terminal.app** after install so the keys apply.

## Moving from the standalone bamr87/chui clone

Your links point into `~/github/chui`. Re-run the installer from bashOS and it re-points them, with nothing moved or deleted:

```bash
~/github/bashos/bin/bashos chui install --dry-run --skip-brew   # lists each "relink … (was ~/github/chui/…)"
~/github/bashos/bin/bashos chui install --skip-brew
chui check                                                     # flags any link still in the old tree
```

`~/.config/chui/local.zsh` and `~/.chui-backups/` are kept as they are. Delete `~/github/chui` once `chui check` passes.

## Everyday

| Command | What |
| --- | --- |
| `chui` | interactive menu (update / configure) |
| `chui install [--dry-run]` | install or re-link; `--skip-brew`, `--no-backup`, `--no-terminal` |
| `chui home` | map `~` + next level (two columns when maximized) |
| `chui home open` | zellij layout: visible \| hidden + strays |
| `chui home sweep` | move `$HOME` strays into `~/Documents/Archive` |
| `hm` / `zh` | aliases for `chui home` / `chui home open` |
| `chui check` | verify install (`chui doctor` is the same) |
| `chui backup` | snapshot configs |
| `chui restore [stamp]` | roll back to a snapshot (default: the latest) |
| `chui dash` | status box |
| `zj` | zellij |
| `lg` | lazygit |
| `btop` | processes |
| `z <dir>` | jump (zoxide) |
| `forge` | remote dev box |
| `chui keys` | keyboard shortcuts |
| `chui update` | backup + git pull + reinstall |
| `chui configure` | icons, splash, home map, font, bat theme, Zellij keys |

Every subcommand works from zsh, bash, scripts and `make`, and as `bashos chui …`. With no terminal attached (a pipe, or `CI` set), `chui` prints help instead of opening the menu.

Prefs live in `~/.config/chui/local.zsh` (not in git). chui owns only the block between its `>>> chui managed` markers. Every other line (for example the bamr87 hub's `devtools-env.sh` hook) is left as it is. TUI: **↑↓** choose · **enter** · **esc** back.

Maximize the window, then `hm`. Finder hides dotfiles, and a plain `ls` hides the next level and file size. The map splits **visible** vs **hidden**, expands one level down, flags **LARGE** files, and tags **stray** items that should not live at `$HOME` root. `chui home sweep` moves selected strays to `~/Documents/Archive` (nothing is deleted). Set `CHUI_HOME_MAP=1` to show the map when a new shell starts in `~`.

**Keys:** ⌘←/→ line · ⌥←/→ word · ⌘⌫ kill to start · ⌃R fuzzy history. Full list: [docs/KEYS.md](docs/KEYS.md).

**Zellij keys.** `classic` (the default) is the setup as it has always been: `ctrl+p/t/n/o` pick a mode and `ctrl+q` quits. `unlock-first` follows bashOS keys v1. Zellij starts locked, so every `ctrl` key reaches the app inside it, such as the bashOS desktop, lazygit or vim. `ctrl+g` unlocks it, then a plain letter picks the mode. Switch with `chui configure` → Zellij keys.

## Layout

```text
Brewfile              packages
install.sh            idempotent bootstrap (--dry-run shows the plan)
backup.sh             ~/.chui-backups/<stamp>
uninstall.sh          restore a snapshot (chui restore)
check.sh              smoke test (chui check)
lib.sh                helpers: local.zsh block, link table, zellij mode
tui.sh                the chui menu and every subcommand
config/zshrc          linked to ~/.zshrc
config/zshenv         linked to ~/.zshenv (disables session restore)
config/p10k.zsh       linked to ~/.p10k.zsh
config/aliases.zsh
config/functions.zsh
config/keybindings.zsh
config/terminal/      Apple Terminal + VS Code key maps, font
config/zellij/        config (classic + unlock-first) + home layout
config/home.sh        $HOME map / sweep
custom/forge.zsh      linked into oh-my-zsh custom
custom/plugins.txt    oh-my-zsh plugins install.sh clones
tests/                offline tests against a throwaway $HOME (pytest chui/tests)
```

Backups live in `~/.chui-backups/` (not in git). Secrets are never committed. Install never deletes a real file: one that sits where a link goes is moved to `<file>.chui-<stamp>`.

## Rollback

```bash
chui restore            # latest snapshot
chui restore 20260920-205857
```

Rebuild details: [docs/REBUILD.md](docs/REBUILD.md).
