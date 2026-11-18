# Environment variables

## Build

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `USE_DOCKER` | `1` on macOS, `0` on Linux | Makefile | run Linux steps in the builder container |
| `BUILDER_IMAGE` | `oneos-builder:latest` | Makefile | builder image tag |
| `FETCH_LARGE` | `0` | fetch.sh | also fetch `large: true` artifacts |
| `CI` | — | fetch.sh | `true`: only fetch `ci: true` artifacts |
| `CACHE_DIR`, `BUILD_DIR`, `PAYLOAD_DIR` | `cache/`, `build/`, `build/payload/` | scripts | output locations |
| `LIGHTOS_ISO` | `build/oneos-lightos.iso` | stage-payload.sh | ISO to stage |
| `IMAGE`, `IMAGE_SIZE` | `build/one-os-test.img`, at least `16G` (sized to the payload + `reserve_mb`) | build-test-image.sh | image path and size |
| `CARD_IMAGE` | `build/one-os-card.img` | flash-macos.sh | image to flash |
| `SOURCE_DATE_EPOCH` | `1767225600` (2026-01-01) | lib.sh | reproducible timestamps |
| `LB_WORKDIR` | `/var/tmp/oneos-lightos` | build-lightos.sh | live-build work dir (in the container) |
| `ONEOS_MANIFEST` | `manifest.yaml` | manifest.py | alternative manifest |

## Tests and VMs

| Variable | Default | Meaning |
|---|---|---|
| `ONEOS_ACCEL` | `kvm` if `/dev/kvm` is usable, else `tcg` | QEMU accelerator |
| `ONEOS_TIMEOUT_SCALE` | `1` (KVM) / `8` (TCG) | multiplier for test timeouts |
| `ONEOS_KEEP` | `0` | `1`: keep overlays after passing tests |
| `ONEOS_OVERLAY` | auto (`nbd` → `fuse` → `raw`) | how tests edit P1 inside an overlay |
| `ONEOS_IMAGE` | `build/one-os-test.img` | image the harness tests |
| `ONEOS_LIGHTOS_ISO` | `build/oneos-lightos.iso` | ISO for direct-boot tests |
| `ONEOS_RUNS` | `build/test-runs` | test artifact directory |
| `ONEOS_MIRROR` | — | apt mirror for `oneos-install` (T50 in CI uses an apt cache) |
| `PYTEST_ADDOPTS` | — | extra pytest options (passed into the container) |

## Docs

| Variable | Default | Meaning |
|---|---|---|
| `CHROME` | Google Chrome app path | browser for wizard screenshots |
| `DOCS_DISK_MATCH` | `SDXC` | which removable disk to select in wizard screenshots |
