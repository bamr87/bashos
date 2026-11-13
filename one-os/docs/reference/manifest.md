# `manifest.yaml` reference

The single source of truth for everything external. `make lint` checks it
(`scripts/manifest.py lint`); `make fetch` refuses any file whose checksum doesn't match.

```yaml
schema: 1

ventoy:
  version: "1.1.18"
  url: "https://github.com/ventoy/Ventoy/releases/download/v1.1.18/ventoy-1.1.18-linux.tar.gz"
  sha256: "d86ff9de…"
  options:
    partition_style: gpt          # gpt | mbr  (Ventoy2Disk -g)
    secure_boot: true             # Ventoy2Disk -s
    reserve_mb: 0                 # space left after Ventoy's partitions (future native home base)
  menu_timeout: 10                # seconds before the default entry boots
  windows11: {bypass_check: true, bypass_nro: true}  # Ventoy: skip TPM/Secure Boot/RAM checks; allow a local account

lightos:
  builder: live-build
  distribution: trixie
  architecture: amd64
  desktop: xfce                   # xfce | lxqt | none
  file: ISO/oneos-lightos.iso    # where it goes on the stick (must be under ISO/)
  persistence_mb: 4096
  extra_packages: [gparted, network-manager, …]
  backports: ["linux-image-*", "firmware-*", …]  # from <distribution>-backports (apt pin 990): new kernel + firmware for new hardware

netboot:                          # same fields as isos
  - name: netboot.xyz-efi
    file: ISO/netboot.xyz.efi
    url: "https://boot.netboot.xyz/ipxe/netboot.xyz.efi"
    sha256: "d0488741…"
    sha256_from: "https://boot.netboot.xyz/ipxe/netboot.xyz-sha256-checksums.txt"   # used by make bump
    alias: "Network install (netboot.xyz)"
    mode: uefi                    # any | uefi | legacy
    ci: true

isos:
  - name: ubuntu-server
    file: ISO/ubuntu-server.iso
    url: "https://releases.ubuntu.com/resolute/ubuntu-26.04.1-live-server-amd64.iso"
    sha256: "cc8a95cd…"
    sha256_from: "https://releases.ubuntu.com/resolute/SHA256SUMS"   # make bump refreshes from it
    alias: "Ubuntu Server 26.04.1 LTS installer (offline)"
    ci: true
    optional: true
    large: true                   # fetched only with FETCH_LARGE=1
  - name: windows11
    file: ISO/windows11.iso
    source: user-supplied         # copied from local-isos/windows11.iso; never downloaded
    optional: true
    ci: false                     # must be false for user-supplied
```

## Artifact fields (`netboot`, `isos`)

| Field | Required | Meaning |
|---|---|---|
| `name` | ✓ | identifier |
| `file` | ✓ | path on the stick (unique) |
| `url`, `sha256` | for downloads | source and its SHA-256 (64 lowercase hex) |
| `source` | | `url` (default) or `user-supplied` (from `local-isos/`) |
| `sha256_from` | | publisher's checksum list, used by `make bump` |
| `alias` | | menu name; **ASCII only** (Ventoy's font has no emoji) |
| `mode` | | `any` (default), `uefi` or `legacy` — hidden in the other firmware mode |
| `ci` | | fetch in CI (`CI=true`) |
| `optional` | | missing is a warning, not an error |
| `large` | | skip unless `FETCH_LARGE=1` |

## Lint rules

No `<PIN>` placeholders · `schema: 1` · Ventoy `url` contains `version` · `partition_style`
is `gpt`/`mbr` · `desktop` is known · `lightos.file` under `ISO/` · unique `file`s · URL
artifacts have a well-formed `sha256` · `mode` valid · aliases ASCII · user-supplied
artifacts have `ci: false`.
