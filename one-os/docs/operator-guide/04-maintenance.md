# Maintenance

## Updating pinned versions

`manifest.yaml` pins every external file by URL and SHA-256. To see what's newer:

```bash
make bump        # prints a diff of proposed pins (Ventoy release, netboot.xyz checksums)
```

Review the diff, copy `build/manifest.bump.yaml` over `manifest.yaml` if it looks right,
then rebuild and test:

```bash
make fetch lightos payload image && make test
```

The nightly CI job does the same and opens a pull request when pins change.

## Refreshing sticks in the field

| Change | What to do on existing sticks |
|---|---|
| New/updated offline ISO in the manifest | Boot the home base: `sudo oneos-restock` (or copy the ISO into `ISO/`) |
| New home-base ISO | Copy `build/oneos-lightos.iso` over `ISO/oneos-lightos.iso` on the stick, or re-flash |
| New Ventoy version / menu config | Re-flash (persistence data is lost — back it up first) |

Back up a user's persistence before re-flashing: `sudo oneos-restock --backup-persistence`,
then copy `persistence/lightos.dat.bak` off the stick.

## Release checklist

1. `make lint` and `make test` green locally; nightly green (`test-full`).
2. `make bump` reviewed; no `<PIN>` placeholders (`make lint` enforces).
3. Flash one stick with the wizard; boot test passes.
4. Run the [hardware checklist](../hardware-checklist.md) on at least a UEFI laptop with
   Secure Boot, an older BIOS machine and a desktop with wired Ethernet.
5. Record results in [hardware results](../hardware-results.md).
6. Tag the release; the nightly job's `payload.tar.zst` + `SHA256SUMS` are the artifacts.

## Housekeeping

```bash
scripts/oneos-vm list              # VM instances and their state
scripts/oneos-vm rm <name>         # delete a stopped instance (overlay, logs)
make clean                          # images, payload, test runs (keeps cache/ and the ISO)
make distclean                      # everything generated
```

Wizard logs (`build/wizard/`) and `build/flash-history.jsonl` are kept until you delete them.
