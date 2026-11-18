# Stick layout and `ventoy.json`

## Partitions

| | Label | Filesystem | Size | Contents |
|---|---|---|---|---|
| P1 | `Ventoy` | exFAT | rest of the device | ISOs, persistence, config (below) |
| P2 | `VTOYEFI` | FAT | 32 MB | Ventoy's EFI loaders, `ENROLL_THIS_KEY_IN_MOKMANAGER.cer` |

GPT partition table; Ventoy's legacy-BIOS boot code sits in the first 1 MiB.

## Files on P1

```
ISO/oneos-lightos.iso          home base
ISO/netboot.xyz.efi             netboot.xyz for UEFI (hidden in BIOS mode)
ISO/netboot.xyz.iso             netboot.xyz for BIOS (hidden in UEFI mode)
ISO/<name>.iso                  optional offline installers (manifest isos:, e.g. ubuntu-desktop,
                                ubuntu-server, debian-netinst, fedora-workstation, linuxmint,
                                archlinux, proxmox-ve, systemrescue)
ISO/windows11.iso               optional, user-supplied
persistence/lightos.dat         ext4, label "persistence", persistence.conf = "/ union"
persistence/lightos.dat.bak     after oneos-restock --backup-persistence
ventoy/ventoy.json              Ventoy plugin config (below)
oneos/manifest.yaml            copy of the build manifest (oneos-restock)
oneos/selftest/README.txt      what the self-test hook is
oneos/selftest/run.sh          only during tests — powers the machine off after running
oneos/selftest/results/*.json  self-test results
```

## `ventoy.json`

Rendered from `config/ventoy.json.j2` by `make payload`. Edit the template to change every
stick, or edit `ventoy/ventoy.json` on one stick directly (any text editor; keep it valid JSON).

```json
{
  "control": [
    { "VTOY_DEFAULT_SEARCH_ROOT": "/ISO" },
    { "VTOY_MENU_TIMEOUT": "10" },
    { "VTOY_DEFAULT_IMAGE": "/ISO/oneos-lightos.iso" },
    { "VTOY_LINUX_REMOUNT": "1" },
    { "VTOY_SECONDARY_BOOT_MENU": "0" }
  ],
  "persistence": [
    { "image": "/ISO/oneos-lightos.iso", "backend": "/persistence/lightos.dat", "autosel": 1, "timeout": 3 }
  ],
  "image_blacklist_uefi":   [ "/ISO/netboot.xyz.iso" ],
  "image_blacklist_legacy": [ "/ISO/netboot.xyz.efi" ],
  "menu_alias": [
    { "image": "/ISO/oneos-lightos.iso", "alias": "Home base (persistent)" },
    { "image": "/ISO/netboot.xyz.efi",    "alias": "Network install (netboot.xyz)" },
    { "image": "/ISO/netboot.xyz.iso",    "alias": "Network install (netboot.xyz)" }
  ]
}
```

| Setting | Why it's there |
|---|---|
| `VTOY_DEFAULT_SEARCH_ROOT` | only `/ISO` is listed in the menu (F2 browses everything) |
| `VTOY_MENU_TIMEOUT`, `VTOY_DEFAULT_IMAGE` | boot the home base after 10 s |
| `VTOY_LINUX_REMOUNT` | lets the booted home base mount P1 |
| `VTOY_SECONDARY_BOOT_MENU: 0` | no "boot in normal mode?" sub-menu blocking auto-boot |
| `persistence … autosel/timeout` | pick persistence automatically after 3 s (otherwise it waits forever) |
| `image_blacklist_uefi/_legacy` | show the netboot build that works in the current firmware mode |
| `menu_alias` | friendly names (ASCII only) |

To add a friendly name for your own ISO, add an entry to `menu_alias`, e.g.
`{ "image": "/ISO/distro.iso", "alias": "My distro" }`. More plugins (themes, auto-install,
password protection): [ventoy.net/en/plugin_entry.html](https://www.ventoy.net/en/plugin_entry.html).
