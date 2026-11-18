# Layers

A layer is a product built on this framework: its own setup, run by the installer after the framework's, without editing the framework's install scripts. bashOS is the first one; it ships its runtime this way on top of Amrchy.

## Shape

A layer is a directory under `install/`:

```text
install/layers/<name>/
├── system.sh   # optional: root, in the installed target, after the rest of the system setup
├── user.sh     # optional: each user, after the rest of the user setup
└── ...         # anything the two scripts need (a payload, units, configs)
```

Nothing in this repository lives under `install/layers/`. A product's build copies its layer there before the packages are built, so the runtime package ships it at `/usr/share/omarchy/install/layers/<name>/` and the ISO's install runs it.

## When each script runs

| Script | Runner | Runs as | When |
| --- | --- | --- | --- |
| `system.sh` | `install/post-install/layers.sh`, the last step of `install/post-install/all.sh` | root | `omarchy-apply-system`: in the target chroot during an ISO install, and again on `--upgrade` |
| `user.sh` | `install/user/layers.sh`, the last step of `install/user/all.sh` | the user | `omarchy-provision-user`: once per user, including users created at first boot |

Layers run in name order. Each script is sourced by `bash -eE` in its own process, so a failing command fails the install step and shows in `/var/log/omarchy-install.log`; nothing is skipped silently.

## What a layer script gets

- `LAYER_DIR`: the layer's own directory, for its payload.
- `LAYER_NAME`: the directory's name.
- Everything the framework's own setup scripts get: `OMARCHY_PATH`, `OMARCHY_INSTALL`, and in `system.sh` also `OMARCHY_INSTALL_USER` (empty for a deferred-provisioning install), `OMARCHY_FIRST_INSTALL` and `OMARCHY_UPGRADE`.

## Rules for a layer

- **Offline.** The ISO installs from its bundled mirror with no network. Work that needs the network (downloads, sign-ins) belongs in a first-boot unit the layer enables, which waits for the network and retries.
- **Idempotent.** `system.sh` runs again on `omarchy apply system --upgrade`.
- **The user's files are theirs.** Seed defaults; never overwrite what a user changed.
- **No framework edits.** A layer that needs the framework to change proposes that change here, where every layer gets it.

## Ownership

`install/post-install/layers.sh`, `install/user/layers.sh`, this page and `test/shell.d/layers-test.sh` are this fork's own (`default/upstream.toml` lists them). The two `run_logged` lines at the end of `install/post-install/all.sh` and `install/user/all.sh` are the only edits to upstream files; an upstream sync keeps them last.
