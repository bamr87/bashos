# Rebuild / deploy

## Backup

`chui backup` (`./backup.sh`) writes `~/.chui-backups/YYYYMMDD-HHMMSS/`:

- `.zshrc` `.zshenv` `.zprofile` `.zlogin` `.p10k.zsh` `.gitconfig`
- `oh-my-zsh/custom/`
- Zellij config + home layout
- the `chui` / `chui-home` links and `~/.config/chui/local.zsh`
- VS Code `keybindings.json`, Apple Terminal plist
- `MANIFEST.txt` (`format=2`, host, date, and the chui checkout + commit)

`install.sh` runs backup first unless `--no-backup`.

## Package

```bash
brew bundle --file=Brewfile
```

Oh My Zsh plugins are git-cloned by `install.sh` (not brew), from the list in `custom/plugins.txt`:

- powerlevel10k
- zsh-autosuggestions
- zsh-syntax-highlighting
- fzf-tab

## Deploy

Idempotent. Safe to re-run.

```bash
chui install --dry-run     # the plan, nothing changed
chui install
chui install --skip-brew
chui install --no-terminal # leave Apple Terminal + VS Code alone
chui check
```

A real file where a link goes is moved to `<file>.chui-<stamp>`, never deleted, even with `--no-backup`.

Symlinks:

| Home | Repo |
| --- | --- |
| `~/.zshrc` | `config/zshrc` |
| `~/.zshenv` | `config/zshenv` |
| `~/.p10k.zsh` | `config/p10k.zsh` |
| `~/.oh-my-zsh/custom/forge.zsh` | `custom/forge.zsh` |
| `~/.config/zellij/config.kdl` | `config/zellij/config.kdl` (or `config.unlock-first.kdl`) |
| `~/.config/zellij/layouts/home.kdl` | `config/zellij/layouts/home.kdl` |
| `~/.local/bin/chui` | `tui.sh` |
| `~/.local/bin/chui-home` | `config/home.sh` |

## Restore

```bash
chui restore                # latest snapshot
chui restore 20260909-204637
```

A `format=2` snapshot lists every path chui links. When the snapshot has no copy of one, the file didn't exist yet, so restore removes chui's link rather than leave it dangling. Older snapshots only restore files. `~/.config/chui/local.zsh` is never overwritten; the snapshot keeps a copy.

## New machine checklist

1. Homebrew
2. `gh auth login`
3. `gh repo clone bamr87/bashos ~/github/bashos`
4. `~/github/bashos/bin/bashos chui install`
5. Font: MesloLGS NF
6. `exec zsh` then `chui check`
7. Quit and reopen Terminal.app (Cmd/Opt key map)

`install.sh` applies Apple Terminal + VS Code terminal keybindings (skip with `--no-terminal`).

## Update from the TUI

```bash
chui              # menu
chui update       # pull + backup + install
```

`update` pulls the bashOS checkout chui lives in. In a detached checkout (bashos as a submodule), it skips the pull and offers to reinstall from the current tree.

User prefs: `~/.config/chui/local.zsh` (icons, splash, home map, font, bat theme, Zellij keys), in the block between the `>>> chui managed` markers.
