# Epic: bashOS and Amrchy as bootable systems

> The next major piece of one-os: make bashOS and Amrchy two operating systems that one-os can build, put on a stick or serve over the network, deploy onto a machine unattended, and prove in QEMU before the first real disk is written.

- **Status:** in progress (2026-11-13): story 2 is done and story 5 half done. [ADR 0005](../../../docs/adr/0005-bashos-is-amrchy-plus-a-layer.md) answers "Which bashOS?"
- **Depends on:** [ADR 0004](../../../docs/adr/0004-one-os.md) (one-os in bashos), [ADR 0002](../../../docs/adr/0002-bashos-os-debian-mkosi.md) (the bashOS Debian image), [ADR 0003](../../../docs/adr/0003-bashos-on-omarchy.md) and epic [bamr87/bashos#73](https://github.com/bamr87/bashos/issues/73) (bashOS as a fork of Omarchy, `bamr87/amrchy`)
- **First machine:** the ASUS ROG Crosshair X870E Dark Hero from the [SteamOS field report](../field-reports/2026-11-12-steamos-silent-network.md); second: forge ([docs/FORGE.md](../../../docs/FORGE.md))

## Goal

From one checkout, with one manifest:

```bash
bin/bashos one-os fetch systems        # build or download bashOS and Amrchy, verified
bin/bashos one-os payload image test   # both on the stick image, both installed in a VM, both checked
```

and then, on a real machine booted from the stick or from PXE, one menu entry each that ends in a machine you can ssh into with your own key.

## What exists today

| Piece | State | Where |
| --- | --- | --- |
| bashOS disk image | Builds and boots in QEMU; a GPT image (ESP + a root that grows) provisioned on first boot from a `BASHOS-SEED` drive. Debian 13 base, retired by ADR 0003 but still in the tree | `os/image/` |
| Amrchy | The Omarchy fork, in this repo as `amrchy/` (a squashed subtree), with layers: the bashOS layer runs last in its installer | `amrchy/`, [docs/AMRCHY.md](../../../docs/AMRCHY.md) |
| The bashOS ISO | Amrchy with the bashOS layer, built by Omarchy's builder at pinned commits (`bashos os iso build`); its `cidata` seed (`bashos os iso seed`); first boot finishes the runtime online (`bashos-firstboot`). The layer and first boot were run on Omarchy's 4.5.0 image; the ISO itself has not been built or installed yet | `os/iso/`, `os/amrchy/layer/` |
| Machine profiles | The X870E desktop's parts and chips, checked against a system's kernel (`oneos-machine check`) | `machines/`, [reference](../reference/machines.md) |
| ISO on the stick | Any pinned ISO becomes a Ventoy menu entry | `manifest.yaml` → `isos` |
| Image onto a disk | Fetch a vendor disk image, write it to an NVMe drive from the home base, fix up EFI entries, report progress to the server (SteamOS only) | `oneos-steamos`, `scripts/fetch-steamos.sh` |
| Network boot | The home base over PXE, with a menu and an event log | `netboot/` |
| Proof | Named VMs with a guest agent, install-to-`/dev/vda` tests, screenshots | `harness/`, `test_50`, `test_120` |

## Stories

Progress, 2026-11-13: story 2 is done (machine profiles, T05). Story 4 merged into story 5: the bashOS that boots is Amrchy with the bashOS layer (ADR 0005), and the Debian image stays as it is. Story 5's build half is done (`bashos os iso build`, `bashos os iso seed`), and its *Done when* is a CI job: the `os iso` workflow builds the ISO and installs it unattended in a KVM VM through first boot (`bashos os iso test`). It still has to pass for the first time, and a one-os harness test for the stick and PXE paths is open. Stories 1, 3, 6 and 7 are open.


1. **A catalog of systems, not just ISOs.** Generalise `isos` and the SteamOS special case into one `systems:` list in `manifest.yaml`. Each entry says what it is (`iso`, `disk-image`), where it comes from (a pinned URL, or a local build command and its output path) and how it is checked. `scripts/manifest.py lint` enforces it. *Done when:* SteamOS, bashOS and Amrchy are three entries of the same shape and the existing tests still pass.
2. **Machine profiles.** `machines/<name>.yaml` records a machine's PCI and USB ids, which kernel first drives each chip, firmware notes (which port PXE-boots, Secure Boot state) and the systems that fit. `oneos-machine check` on the home base compares the hardware in front of it with a system's kernel **before** deploying and says "this OS has no driver for your network card". The X870E table in the field report becomes the first profile; forge is the second. *Done when:* the check, run against SteamOS 3.8 on the X870E profile, reports the missing MT7927 driver.
3. **One deployer.** Lift the image-writing half of `oneos-steamos` into `oneos-deploy --system NAME --target DISK`, keeping the SteamOS specifics as one system's hooks. It writes the image, grows or repairs partitions, creates the EFI entry, and places the operator's public SSH key and a first-boot network check on the target. *Done when:* `test_120` passes through `oneos-deploy` unchanged.
4. **bashOS as a system.** The catalog entry builds the image with `bashos os image build`; the deployer writes it and generates the `BASHOS-SEED` content (user, hostname, key) instead of needing a second stick. *Done when:* a harness test deploys it to `/dev/vda`, reboots without the stick, and reaches the machine by ssh with the seed's key and `bashos os status` exits 0.
5. **Amrchy as a system.** Build the fork's ISO (`omarchy-iso` against the fork's packages, `bin/rebrand` applied), pin the result, put it on the stick as a Ventoy entry and in the PXE menu, and generate its `cidata` seed. *Done when:* a harness test installs it unattended to `/dev/vda` and the installed system boots to its desktop (screenshot) and answers ssh.
6. **Both over the network.** The PXE menu offers "Deploy bashOS" and "Install Amrchy" beside the home base, and the server's event log shows each stage. *Done when:* `test_100`'s pattern passes for both.
7. **Hardware proof.** The maintainer flashes the stick and deploys each system on the X870E, following a checklist; results go into `docs/hardware-results.md` and a field report. *Done when:* both rows say which disk booted (`findmnt`, `efibootmgr`), wired and Wi-Fi state, and how long it took.

Stories 1 to 3 are groundwork and can land one at a time; 4 and 5 are independent of each other.

## Open questions

- **Which bashOS?** Answered 2026-11-13 ([ADR 0005](../../../docs/adr/0005-bashos-is-amrchy-plus-a-layer.md)): bashOS is Amrchy with the bashOS layer. Story 4 is part of story 5, and the Debian image gets no new work. Applying bashOS's brand to the image (`bin/rebrand`, the boot and login screens) is still open.
- **Kernel versus the X870E.** Debian 13's kernel 6.12 has no driver for the board's 10 GbE port (needs 6.16) or its Wi-Fi (needs 7.2); the 5 GbE port works. The bashOS Debian image would need the backports kernel the home base already uses, or it targets forge only. Amrchy is Arch and rolling, so its kernel version is whatever the ISO was built with: record it in the catalog entry.
- **Does the Amrchy ISO boot under Ventoy?** Unknown until tested. The fallback is the same as SteamOS: a native image on its own card, or PXE.
- **Encryption and unattended installs.** Decided for now: `bashos os iso seed` writes unencrypted installs only. An encrypted unattended install would carry its passphrase in clear on the seed and still stop at the first boot to ask for it; encryption stays with the interactive installer.
- **Secure Boot.** bashOS's systemd-boot is unsigned and needs Secure Boot off; the stick's Ventoy path uses MOK enrollment (`test_80`). State per system what the firmware must be set to.

## Rules that carry over

- An agent never writes a real disk; story 7 is the maintainer's.
- Every story ships with the harness test named in its *Done when*, and the docs page that describes it.
- No story gives a bashOS loop a tool or touches `opencode/policy.py`.
- The lessons of the first deployment are requirements here: know which disk booted before changing anything, check that the server's sockets are actually listening, and never trust a process that merely exists.
