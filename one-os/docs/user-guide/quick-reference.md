# one-os quick reference

*One page — print it and keep it with the stick.*

## Boot it

| | |
|---|---|
| Boot-menu key | Dell/Lenovo/Acer/Gigabyte **F12** · HP **F9** · ASUS **F8**/**Esc** · MSI/ASRock **F11** · NUC **F10** · Surface: hold **Vol−** + power · Intel Mac: hold **⌥** |
| Pick | `UEFI: <stick>` if offered |
| SD card | many PCs need a **USB SD adapter** to boot it |
| Secure Boot, first time | *Verification failed* → OK → Enroll key from disk → **VTOYEFI** → `ENROLL_THIS_KEY_IN_MOKMANAGER.cer` → Continue → Yes → Reboot |

## Menu

| Entry | |
|---|---|
| **Home base (persistent)** | default after 10 s · Debian + Xfce · changes are kept |
| **Network install (netboot.xyz)** | wired Ethernet only |
| other ISOs | anything you copied into `ISO/` |
| keys | ↑↓ Enter · F2 browse · F4 boot the PC's disk · F5 tools |

## Home base

| | |
|---|---|
| Login | **user** / **live** |
| Admin | `sudo …` (password `live`) |
| Wi-Fi | network icon in the panel · `nmcli device wifi connect "SSID" password "…"` |
| Shut down | always from the menu — protects your saved changes |

## Commands

```bash
sudo oneos-install                         # install Debian/Ubuntu/Arch onto another drive (ERASES it)
sudo oneos-install --target /dev/nvme0n1 --distro debian --hostname box --user me
sudo oneos-restock --list                  # what's on the stick vs. its manifest
sudo oneos-restock                         # download/verify missing ISOs
sudo oneos-restock --backup-persistence    # back up your saved changes
lsblk -o NAME,SIZE,MODEL,TRAN               # which drive is which (the stick is TRAN usb)
sudo smartctl -H /dev/nvme0n1               # drive health
sudo testdisk                               # recover partitions / files
```

## If something's wrong

| Problem | Try |
|---|---|
| stick not in boot menu | other port, enable USB boot, SD → USB adapter |
| black screen after *Home base* | wait 2 min |
| netboot: no DHCP | plug in a cable; else use `oneos-install` over Wi-Fi |
| everything else | [Troubleshooting](../troubleshooting.md) |
