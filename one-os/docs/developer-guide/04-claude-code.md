# Working with Claude Code

The repository is set up so an AI coding agent can build, test and debug it with the
same tools a person uses, inside clear limits.

## What Claude Code reads

| File | Purpose |
|---|---|
| [`CLAUDE.md`](../../CLAUDE.md) | ground rules, the build → test loop, the VM workflow, the wizard, a map of the repo |
| [`.claude/skills/oneos-vm/SKILL.md`](../../.claude/skills/oneos-vm/SKILL.md) | how to drive live VMs: start → wait → exec → screenshot → debug → encode as a test |
| [`PLAN.md`](../../PLAN.md), [`docs/adr/`](../adr/) | design decisions to stay consistent with |
| [`docs/spike.md`](../spike.md) | traps already found (read before "fixing" a config value) |

## Guard rails

- **Never writes a real disk.** No `make flash`, `flash*.sh`, `write-image.py`, `dd`,
  `diskutil erase*` or `oneos-install` against hardware. Those need the human's admin
  password and typed confirmation anyway.
- Physical sticks may be *booted read-only* in a VM, but that needs `sudo`, so it asks you.
- Agents work on loop devices, qcow2 overlays and named VM instances only.
- "Done" means a harness test proves it, not a screenshot that looks right.

## A good task looks like

> "T21 fails on the new image — find out why and fix it."
> "Add `htop` to the home base and prove it's installed with a test."
> "The netboot menu screenshot in the docs is out of date — regenerate it."

The agent can then: rebuild (`make lightos payload image`), reproduce
(`scripts/oneos-vm start dev` → `exec`/`screenshot`), fix, encode the check in
`harness/tests/`, and run it (`make test ARGS="-k …"`).

## What it can see

`scripts/oneos-vm screenshot NAME` writes a PNG the agent reads directly, so it can check
menus and desktops itself; `exec` gives it logs and state as root; `serial` covers early
boot. The wizard's read-only API (`/api/state`, `/api/devices`) shows build freshness and
attached devices.

## Long operations

`make lightos` (~25 min) and the full test suite (~30 min under emulation) should run in
the background; the agent is notified when they finish. Wizard jobs and test runs write
complete logs under `build/` for review.
