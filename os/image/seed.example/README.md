# bashOS first-boot seed (example)

> What a BASHOS-SEED drive carries so a freshly written bashOS image provisions itself with no keyboard: the user, the machine's name, ssh keys and harness secrets.

`bashos-provision` (the image's first-boot service) looks for a FAT or ISO volume labelled `BASHOS-SEED` — the bashOS twin of Omarchy's `cidata` drive — and reads, from its top level:

| File | Required | What it does |
| --- | --- | --- |
| `seed.env` | yes | `KEY=value` lines (this directory's copy documents every key). Read as data, never sourced. |
| `authorized_keys` | no | Installed as the user's `~/.ssh/authorized_keys` (0600), so the box is reachable over ssh at once. |
| `harness.env` | no | Installed as `~/.config/bashos/harness.env` (0600): `DASH_CONSOLE_TOKEN`, `GH_TOKEN`. Required before the harness binds a LAN address. |

Make one on a USB stick from Linux (`sudo mkfs.vfat -n BASHOS-SEED /dev/sdX1`, then copy the files) or from macOS (`diskutil eraseVolume FAT32 BASHOS-SEED /dev/diskN`), or as an image file with mtools: `mformat -C -f 1440 -v BASHOS-SEED -i seed.img ::` then `mcopy -i seed.img seed.env authorized_keys ::`. Without a seed, the first boot asks for a user name, hostname and password on the monitor.
