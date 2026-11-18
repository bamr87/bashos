# ADR-0002: Build a payload, not a dd image

Status: accepted · 2026-11-07

## Context
A fixed-size `.img` written with `dd` leaves the rest of a larger stick unusable
and must be rebuilt for every size.

## Decision
The build produces `build/payload/` (the P1 file tree). One routine,
`scripts/install-to-device.sh`, runs Ventoy2Disk on a device and copies the payload.
Tests call it on a loop device over a sparse 16 GB file (`make image`); humans call
it on a stick through `scripts/flash.sh` (`make flash DEV=…`).

## Consequences
- What CI tests is exactly what goes onto the stick.
- The stick uses its full capacity; ISOs can be added later by copying.
- Test image builds need loop devices (root/privileged container).
- `install-to-device.sh` refuses non-loop devices unless invoked via `flash.sh`.
