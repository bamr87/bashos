# Make targets

Run from the repository root. On macOS (or with `USE_DOCKER=1`) Linux-only steps run in
the builder container; `flash`, `card-boot`, `wizard`, `run` and `vm` run on the host.

| Target | Does | Notes |
|---|---|---|
| `make help` | list targets | default target |
| `make builder` | build `oneos-builder:latest` (+ `:amd64` on non-x86 hosts) | once, and after editing `docker/builder.Dockerfile` |
| `make fetch` | download + verify everything in `manifest.yaml` into `cache/`, unpack Ventoy | `FETCH_LARGE=1` for large ISOs; `CI=true` only `ci: true` items |
| `make lightos` | build `build/oneos-lightos.iso` with live-build | ~25 min on Apple Silicon |
| `make payload` | stage `build/payload/` + `build/payload.SHA256SUMS` | needs the ISO |
| `make image` | Sparse test image `build/one-os-test.img`: 16 GB, or larger when the payload plus the reserved space needs it | `IMAGE_SIZE=…` to fix the size |
| `make card-image DISK=diskN` | image exactly the size of a device → `build/one-os-card.img` | macOS; reads the size via `diskutil` |
| `make flash DISK=diskN` | macOS: guarded write + verify + eject | admin password via macOS dialog; no sudo |
| `make flash DEV=/dev/sdX` | Linux: guarded Ventoy install + payload copy | `FLASH_ARGS=--i-know-this-is-not-usb` for SSDs |
| `sudo make card-boot DISK=diskN` | boot a flashed device in QEMU (UEFI, BIOS), read-only | needs root to read the device |
| `make wizard` | open the flash wizard in the browser | see [operator guide](../operator-guide/01-flash-wizard.md) |
| `make run [VMARGS=…]` | start VM instance `run` in a window | e.g. `VMARGS="--profile bios --fresh"` |
| `make vm ARGS="…"` | pass-through to `scripts/oneos-vm` | e.g. `ARGS="exec run -- uname -a"` |
| `make test [ARGS=…]` | fast harness suite | `ARGS="-k t21 -v"` |
| `make test-full` | all tests incl. nightly | |
| `make test-image` | T00 only (no VM) | |
| `make netboot` | extract the home base for network boot → `build/netboot/` | after `make lightos` |
| `make pxe-start [IFACE=…]` | network boot server in the background (HTTP + ProxyDHCP + TFTP) | see [network boot server](../operator-guide/05-network-boot-server.md) |
| `make pxe-status` / `pxe-logs` / `pxe-restart` / `pxe-stop` | manage it | `pxe-logs ARGS=-f` follows |
| `make pxe-server IFACE=…` | the same, in the foreground | debugging |
| `make steamos-fetch` | cache Valve's SteamOS image for the server (~3.4 GB) | |
| `make lint` | shellcheck, ruff, manifest schema, no `<PIN>` | fast; run often |
| `make bump` | propose new pins → `build/manifest.bump.yaml` + diff | never edits `manifest.yaml` |
| `make shell` | interactive shell in the builder | |
| `make docs-screenshots` | regenerate `docs/images/` from real VMs and the wizard | see [docs/tools](../tools/) |
| `make clean` | remove payload, images, test runs | keeps `cache/` and the ISO |
| `make distclean` | remove `build/` and `cache/` | |
