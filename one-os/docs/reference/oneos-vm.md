# `scripts/oneos-vm` reference

```
oneos-vm <command> NAME [options]
```

Instances live in `build/vms/NAME/` (names: lowercase letters, digits, dashes, ≤ 24 chars).
Exit codes: `0` ok · `1` usage/state error · `3` guest agent unavailable · `4` timeout ·
for `exec`, the guest command's own exit code.

| Command | Options | Does |
|---|---|---|
| `start NAME` | `--window` show the screen · `--profile uefi\|bios\|uefi-sb` · `--fresh` discard overlay/NVRAM/target · `--image IMG` raw stick image · `--iso ISO` boot an ISO as CD-ROM · `--disk diskN` physical stick (sudo) · `--write` with `--disk`: write through · `--target SIZE` empty install disk `/dev/vda` · `--no-usb` boot the target only · `--no-net` · `--mem MB` (4096) · `--smp N` (4) | start in the background and return |
| `list` | | instances and state |
| `status NAME` | | state, uptime, READY marker, agent, last serial lines |
| `wait NAME` | `--agent` (default) · `--ready` · `--serial REGEX` · `--screen TEXT` (OCR) · `--timeout S` (600) | block until the condition |
| `exec NAME [--timeout S] -- CMD…` | `--timeout` (600) | run as root in the guest; one argument → `/bin/sh -c` |
| `cp NAME SRC DST` | | copy a file; prefix the guest side with `vm:` |
| `screenshot NAME [OUT.png]` | | save the screen (default `build/vms/NAME/NAME.screen.png`) |
| `keys NAME KEY…` | | QMP qcodes, chords with `-`: `ret esc tab spc up down left right f1 ctrl-alt-f2 shift-a` |
| `type NAME TEXT` | | type text (`\n` = Enter) |
| `serial NAME` | `-n N` lines (40) · `-f` follow | ttyS0 log, escape codes stripped |
| `console NAME` | `--send TEXT` · `--read S` (3) | interactive ttyS0 (Ctrl-] exits); scripted with `--send` |
| `logs NAME` | | paths of all logs and captures |
| `stop NAME` | `--force` · `--timeout S` (120) | clean poweroff via agent, else ACPI; `--force` quits QEMU |
| `rm NAME` | | delete a stopped instance |

Defaults: the stick image is `build/one-os-card.img` if present, else
`build/one-os-test.img`. Acceleration is KVM on Linux with `/dev/kvm`, TCG otherwise.
