# bashOS migrations

> One-shot shell scripts that bring an existing bashOS machine forward when an update changes something `bashos os install` cannot simply re-apply.

`bashos os update` pulls the layer, re-runs the idempotent installer, then runs every migration here that this user has not run yet. Most changes need no migration: a new unit, package, link or default lands on the next install pass by itself. A migration is for what an idempotent pass cannot express — renaming a file the layer used to write, moving a setting, removing something an older version installed.

- **Name:** `<unix-timestamp>.sh` (`date +%s`), so they sort in the order they were written — Omarchy's convention.
- **State:** a marker per script in `~/.local/state/bashos/migrations/`; `bashos os migrate --pending` lists what has not run (exit 1 when nothing has).
- **Fresh installs** mark every shipped migration as applied (`os/install/finish.sh`): migrations exist for older installs, never for new ones.
- **Each script** runs with `bash`, as the user, with `OS_SRC` set to the layer; source `"$OS_SRC/os/lib.sh"` for `os_root`, `os_block_put` and the rest. It must be idempotent and must exit non-zero on failure — the runner stops there and does not mark it.
