---
name: oneusb-vm
description: Boot, inspect and debug one-usb VMs with scripts/oneusb-vm — run commands as root in the guest, read its screen, drive menus, follow the serial console. Use when asked to try, run, debug, reproduce or check something on the stick/home base/netboot in a VM, or when a harness test fails and you need a live instance.
---

# Driving one-usb VMs

Work on a named instance; it keeps its overlay between runs, so state you set up
(packages, files, persistence) survives `stop`/`start`. Use `--fresh` to reset.

## Loop

1. `scripts/oneusb-vm start <name> [--profile bios] [--target 20G]` — returns at once.
2. `scripts/oneusb-vm wait <name> --agent --timeout 600` — guest agent up = userspace up.
   If it times out: `scripts/oneusb-vm serial <name> -n 80` to see how far boot got,
   then `screenshot` + Read the PNG (Ventoy menu / GRUB / persistence prompt are screen-only).
3. Investigate with `exec` first: `scripts/oneusb-vm exec <name> -- 'systemctl --failed; journalctl -b -p warning --no-pager | tail -80'`.
   Commands run as root via /bin/sh -c; exit code is passed through.
4. Change something → reproduce in the live VM → encode it as a harness test
   (`harness/tests/`, use `vm.exec(...)` / `vm.wait_agent()`), then fix the image.
5. `scripts/oneusb-vm stop <name>` when done (clean poweroff). `list` shows what's running.

## Seeing and typing

- `scripts/oneusb-vm screenshot <name>` → prints a path; Read it to look at the screen.
- Keys use QMP qcodes: `ret esc tab spc up down left right f1..f12 ctrl-alt-f2 shift-a`.
  `scripts/oneusb-vm type <name> 'user\n'` for text.
- Ventoy menu: entries are aliases from config/ventoy.json.j2; Enter boots the highlighted one.
- Serial login on ttyS0: `scripts/oneusb-vm console <name> --send '\n'` (user / live).

## Rules

- Never write physical disks. Booting one read-only (`--disk diskN`) needs sudo: ask the human.
- Timeouts: on Apple Silicon x86 is emulated (TCG) — boot ≈ 90 s, desktop sluggish.
- The human can watch the same instance only if it was started with `--window`
  (`make run` starts instance `run` that way).
