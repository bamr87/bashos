# ADR-0004: qemu-guest-agent as the VM control channel

Status: accepted · 2026-11-07

## Context
Tests and live debugging (by people and by Claude Code) need to run commands and move
files inside a booted home base. ADR-0003's file hook works on unmodified boots but is
one-shot (run, write result, power off) and can't answer follow-up questions. SSH would
need a network path and credentials, and shipping `sshd` with the live default password
on a rescue stick is a liability on real networks.

## Decision
Ship `qemu-guest-agent` in the home base. Every harness/CLI VM gets a virtio-serial port
named `org.qemu.guest_agent.0`, exposed on the host as `<name>.qga`. `harness/oneos_harness/qga.py`
implements exec (with exit code, stdout, stderr), file read/write and shutdown;
`VM.exec()` and `scripts/oneos-vm exec|cp` use it. Serial (ttyS0) is a socket with a
log file, so it is both the boot oracle and an interactive fallback console.

## Consequences
- Root command execution in VMs with no network or credentials; works headless in CI.
- On hardware there is no such virtio port: the agent's systemd unit is bound to that
  device and never starts. Nothing listens on the network.
- The self-test hook (ADR-0003) stays for tests that must work on unmodified boots and
  for flows that power off (install, persistence across reboots).
- If a future qemu-guest-agent build disables `guest-exec` by default, T22 fails first;
  re-enable it with a systemd drop-in passing `--allow-rpcs`.
