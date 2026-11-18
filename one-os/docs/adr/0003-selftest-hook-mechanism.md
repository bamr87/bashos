# ADR-0003: File-based self-test hook

Status: accepted · 2026-11-07

## Context
Ventoy boots ISOs unmodified, so tests cannot add kernel parameters per run. We still
need to drive the booted home base (write a canary, run the installer, restock).

## Decision
The home base ships `oneos-selftest.service`. At boot it mounts P1 (label `Ventoy`,
made mountable by `VTOY_LINUX_REMOUNT`) and:

- if `/oneos/selftest/run.sh` is absent → prints `ONEOS-READY` on ttyS0, does nothing else;
- if present → runs it as root (timeout from `# timeout:`), writes
  `/oneos/selftest/results/<name>.json`, prints `ONEOS-SELFTEST <name> PASS|FAIL`, powers off.

The harness writes `run.sh` into a qcow2 overlay of the test image between boots,
so the base image is never modified and tests are isolated.

## Security
`run.sh` executes as root, but it can only come from the stick's own P1, which already
holds the bootloader and the OS images — anyone who can write P1 can replace the whole
system anyway. The hook adds no new trust boundary. It never reads from other disks or
the network. Real-world boots have no `run.sh`, so the service is a no-op.

## Consequences
- Every test is a short shell script plus a serial regex.
- A user who leaves a `run.sh` on their stick will get a power-off after it runs;
  `stage-payload.sh` writes a README in that directory explaining this.
