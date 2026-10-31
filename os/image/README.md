# os/image — the bootable bashOS image

> How to build the bashOS disk image with mkosi, prove it boots in QEMU, write it to a USB stick or a disk, and boot forge from it.

The image is Debian 13 with the bashOS layer already applied: a GPT disk with an EFI system partition (systemd-boot, a unified kernel image) and an ext4 root that grows to fill whatever disk it is written to. Its first boot provisions the machine from a `BASHOS-SEED` drive, or asks on the monitor. Why this shape: [ADR 0002](../../docs/adr/0002-bashos-os-debian-mkosi.md); what runs on it: [docs/OS.md](../../docs/OS.md).

## Build

```bash
bashos os image build --docker --arch x86-64   # from macOS or any Docker host (privileged debian:trixie)
sudo bashos os image build --arch x86-64       # on Debian 13 itself, e.g. forge (sudo apt install mkosi)
```

The output lands in `os/image/mkosi.output/` (gitignored): `bashos_<version>.raw` (the disk), plus its UKI (`.efi`), kernel and initrd. [`build.sh`](build.sh) stages exactly what git would ship at `/opt/bashos`, stamps `/etc/bashos/build-info`, passes every line of `os/packages/*.list` to mkosi, and runs [`mkosi.postinst.chroot`](mkosi.postinst.chroot), which applies the layer with `os/install.sh --image` and enables networkd, resolved, timesyncd, ssh and avahi. `--seed DIR` bakes a seed into the image (it then carries your keys); `-- ARGS` passes the rest to mkosi.

| File | Role |
| --- | --- |
| `mkosi.conf` | Debian trixie (+ `non-free-firmware`), disk format, systemd-boot, UKI, the base packages |
| `mkosi.conf.d/10-x86-64.conf`, `10-arm64.conf` | Kernel and firmware per architecture (forge: amd64 kernel, microcode, nouveau and NIC firmware) |
| `mkosi.repart/` | The partitions: a 512 MB ESP and a minimised root flagged `GrowFileSystem=yes` |
| `mkosi.extra/` | Files copied into the image: first-boot root growth (`usr/lib/repart.d`), DHCP on wired NICs, resolved kept off mDNS |
| `mkosi.postinst.chroot` | The layer's system phases inside the image |
| `seed.example/` | A documented `BASHOS-SEED` drive ([README](seed.example/README.md)) |
| `test/boot-smoke.sh` | The boot test |

An x86-64 build on an Apple-silicon Mac runs under emulation and is slow; build arm64 there to iterate (`--arch arm64`) and let CI (the `os image` workflow, KVM) or forge build x86-64.

## Test

```bash
bashos os image test --docker --arch x86-64 --harness
```

[`test/boot-smoke.sh`](test/boot-smoke.sh) boots the newest image in QEMU on a 16 GB copy-on-write disk with a generated seed drive (user `smoke`, a fresh ssh key) and checks what the machine's person would: `bashos-provision: ready` on the serial console, ssh with the seed's key, `systemctl is-system-running` = `running`, the root grown past 8 GB, the layer and both engine CLIs present, a kernel dry run (`bashos run -n "/sh …"`), the `console` tmux session with its `bashos` window, and with `--harness` the Harness Console answering `/api/health`. Evidence (serial log, each check's output, `bashos-os status`) lands in `mkosi.output/smoke/`. KVM is used when `/dev/kvm` is writable; under TCG pass `--timeout 2400`.

## Write it and boot it

```bash
# Linux — check the device twice: everything on it is replaced
lsblk -o NAME,SIZE,MODEL,TRAN
sudo dd if=os/image/mkosi.output/bashos_<v>.raw of=/dev/sdX bs=4M conv=fsync status=progress

# macOS
diskutil list
diskutil unmountDisk /dev/diskN
sudo dd if=os/image/mkosi.output/bashos_<v>.raw of=/dev/rdiskN bs=4m
```

Put the seed on a second stick (or a second partition you create after writing the image) labelled `BASHOS-SEED`. Firmware: UEFI with Secure Boot **off** (`mokutil --sb-state`; the image's systemd-boot is unsigned).

**On forge, once, without touching its disk:** plug the stick in, find its boot entry with `efibootmgr`, then `sudo efibootmgr --bootnext XXXX && sudo reboot`. forge boots bashOS one time and returns to Debian at the next reboot. Writing the image over `sda` replaces forge's Debian, its LVM volumes and the restic repository on them — that is a separate, explicitly approved step after an off-box backup ([docs/OS.md § forge, step by step](../../docs/OS.md#forge-step-by-step)).
