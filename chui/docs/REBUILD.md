# Rebuild / deploy

## Backup

`./backup.sh` writes `~/.chui-backups/YYYYMMDD-HHMMSS/`:

- `.zshrc` `.zprofile` `.p10k.zsh` `.gitconfig`
- `oh-my-zsh/custom/`
- Zellij config
- Apple Terminal plist

`install.sh` runs backup first unless `--no-backup`.

## Package

```bash
brew bundle --file=Brewfile
```

Oh My Zsh plugins are git-cloned by `install.sh` (not brew):

- powerlevel10k
- zsh-autosuggestions
- zsh-syntax-highlighting
- fzf-tab

## Deploy

Idempotent. Safe to re-run.

```bash
./install.sh
./install.sh --skip-brew
./check.sh
```

Symlinks:

| Home | Repo |
| --- | --- |
| `~/.zshrc` | `config/zshrc` |
| `~/.p10k.zsh` | `config/p10k.zsh` |
| `~/.oh-my-zsh/custom/forge.zsh` | `custom/forge.zsh` |
| `~/.config/zellij/config.kdl` | `config/zellij/config.kdl` |
| `~/.config/zellij/layouts/home.kdl` | `config/zellij/layouts/home.kdl` |
| `~/.local/bin/chui` | `tui.sh` |
| `~/.local/bin/chui-home` | `config/home.sh` |

## Restore

```bash
./uninstall.sh              # latest snapshot
./uninstall.sh 20260909-204637
```

## New machine checklist

1. Homebrew
2. `gh auth login`
3. Clone this repo to `~/github/chui`
4. `make install`
5. Font: MesloLGS NF
6. `exec zsh` then `chui check`
7. Quit and reopen Terminal.app (Cmd/Opt key map)

`install.sh` applies Apple Terminal + VS Code terminal keybindings.

## Update from the TUI

```bash
chui              # menu
chui update       # pull + backup + install
```

User prefs: `~/.config/chui/local.zsh` (icons, splash, font, bat theme).
