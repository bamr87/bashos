# one-USB in bashOS

> What `one-usb/` is — the multiboot USB stick builder imported from bamr87/one-usb with its history — how to build and test it from this repo, the rules that keep it from touching a real disk, and how it stays in step with its own repository.

`one-usb/` builds one USB stick that boots a persistent Debian **home base**, installs other operating systems onto another drive (from the stick or over the network), and is built from code and tested in QEMU before it touches hardware. A Ventoy menu offers the home base, netboot.xyz and offline installers pinned in `one-usb/manifest.yaml`; the reserved space after Ventoy carries Valve's SteamOS recovery stick; `one-usb/netboot/server.py` serves the home base to PCs over the network (HTTP, ProxyDHCP and TFTP); and a local flash wizard on macOS writes the stick with an admin-password prompt and a typed confirmation.

It is self-contained: its own Makefile, builder container (`one-usb/docker/builder.Dockerfile`), pytest/QEMU harness (`one-usb/harness/`), docs and ADRs. Nothing in `src/bashos/` imports it, and it never widens `opencode/policy.py` or gives a loop a tool.

## Where it comes from

`one-usb/` is a [git subtree](https://git-scm.com/book/en/v2/Git-Tools-Advanced-Merging#_subtree_merge) of [bamr87/one-usb](https://github.com/bamr87/one-usb) (private), added with its full history. Change it in either place; to bring upstream commits in, or send local ones back:

```bash
git subtree pull --prefix=one-usb https://github.com/bamr87/one-usb main
git subtree push --prefix=one-usb https://github.com/bamr87/one-usb <branch>
```

Merge a pull request that changes the subtree with a merge commit, not a squash, or the imported history is flattened.

## Build and test

Run everything from the subtree with `make -C one-usb …`. On macOS every Linux-only step runs in its Docker builder.

```bash
make -C one-usb lint                    # shellcheck, ruff, manifest schema (fast)
make -C one-usb lightos                 # the home base ISO (~25 min on Apple Silicon, amd64 emulated)
make -C one-usb payload image           # stage the stick's tree + a 16 GB sparse test image
make -C one-usb test ARGS="-k t21 -v"   # one harness test in QEMU; the fast suite takes ~30 min emulated
make -C one-usb wizard                  # the flash wizard in a browser
```

Its tests boot VMs, so they are not part of `make test`, and its own workflows (`one-usb/.github/workflows/`) only run in bamr87/one-usb: GitHub reads workflows from the repository root alone. The root `ruff check .` skips `one-usb/`, which lints itself with `make -C one-usb lint`.

## Rules

- **Never write a real disk.** No `make flash`, `scripts/flash*.sh`, `write-image.py`, `dd`, `diskutil erase*` or `oneusb-install` against hardware: those are the maintainer's steps. A physical stick may be booted read-only in a VM, and the maintainer runs that command too.
- The harness is the definition of done: run the test that covers a change before calling it finished.
- Pins live in `one-usb/manifest.yaml`; `scripts/manifest.py lint` rejects an unpinned entry.
- The full working notes are in [one-usb/AGENTS.md](../one-usb/AGENTS.md); read them before changing anything there.

## Documentation

[one-usb/README.md](../one-usb/README.md) is the overview and [one-usb/docs/README.md](../one-usb/docs/README.md) indexes its user, operator and developer guides and reference. Its design is in [one-usb/PLAN.md](../one-usb/PLAN.md) and its own ADRs in `one-usb/docs/adr/`. Those documents keep one-usb's own style: hard-wrapped, without this repo's `>` summary line.
