# Adding and updating ISOs

Any bootable `.iso` (and `.efi`, `.img`, `.wim`, `.vhd`) copied onto the stick appears in
the Ventoy menu at the next boot. There's nothing to install or re-flash.

## Drag and drop (any computer)

1. Plug the stick into any Windows, macOS or Linux computer.
2. Open the drive named **Ventoy**.
3. Copy the ISO into the **`ISO`** folder. (Files elsewhere are reachable with **F2** *Browse*.)
4. Eject the drive properly, then boot.

The menu shows the file name. Friendly names (aliases) for the built-in entries come from
`ventoy/ventoy.json`; you can add your own the same way ([stick layout](../reference/stick-layout.md)).

## From the home base: `oneusb-restock`

The stick carries a copy of its manifest (`oneusb/manifest.yaml`) listing what belongs on
it, with checksums.

```bash
sudo oneusb-restock --list        # what the manifest wants vs. what's on the stick
sudo oneusb-restock               # download anything missing or outdated, verify, put in place
sudo oneusb-restock --include-large   # also large items (e.g. the 3 GB Ubuntu Server ISO)
```

Add an ISO of your own and record it in the stick's manifest:

```bash
sudo oneusb-restock --add https://example.org/distro.iso \
     --sha256 <64-hex-digit checksum from the distro's site> --alias "My distro"
```

The alias is recorded in the stick's manifest (so `--list` shows it), but the Ventoy menu
shows the file name. To give it a menu name, add a `menu_alias` entry to
`ventoy/ventoy.json` on the stick ([stick layout](../reference/stick-layout.md#ventoyjson)).
To ship it on every stick you build, add it to the project's `manifest.yaml` instead.

Downloads go to a temporary `.part` file, are checked against the SHA-256 and only then
renamed into place — a bad or interrupted download never replaces a good ISO.

Tidy up ISOs the manifest doesn't know: `sudo oneusb-restock --prune` (use `--dry-run` first).

## Windows

Windows ISOs are never downloaded by the build (licensing). To include one:

- **On an existing stick**: copy `Win11_*.iso` into `ISO/` and boot it.
- **In every stick you build**: put it at `local-isos/windows11.iso` in the project before
  building — the operator guide covers this ([building](../operator-guide/02-building.md#offline-installers)).

## Space

A 128 GB stick has ~120 GB free after the built-in files (home base 1.2 GB, persistence
4 GB, netboot ~5 MB). Check with `df -h` in the home base or the drive's properties elsewhere.
