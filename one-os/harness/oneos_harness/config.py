"""Paths, firmware locations and acceleration, discovered once per session."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("BUILD_DIR", REPO / "build"))

# Debian/Ubuntu `ovmf` package layout first, then Homebrew/Fedora fallbacks.
OVMF_CANDIDATES = {
    "code": ["/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/edk2/ovmf/OVMF_CODE.fd",
             "/opt/homebrew/share/qemu/edk2-x86_64-code.fd"],
    "vars": ["/usr/share/OVMF/OVMF_VARS_4M.fd", "/usr/share/edk2/ovmf/OVMF_VARS.fd",
             "/opt/homebrew/share/qemu/edk2-i386-vars.fd"],
    "code_sb": ["/usr/share/OVMF/OVMF_CODE_4M.secboot.fd", "/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd",
                "/opt/homebrew/share/qemu/edk2-x86_64-secure-code.fd"],
    "vars_ms": ["/usr/share/OVMF/OVMF_VARS_4M.ms.fd", "/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd"],
}


def _first(paths: list[str]) -> Path | None:
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return None


@dataclass
class Config:
    repo: Path = REPO
    build: Path = BUILD
    image: Path = field(default_factory=lambda: Path(os.environ.get("ONEOS_IMAGE", BUILD / "one-os-test.img")))
    lightos_iso: Path = field(default_factory=lambda: Path(os.environ.get("ONEOS_LIGHTOS_ISO", BUILD / "oneos-lightos.iso")))
    payload: Path = field(default_factory=lambda: BUILD / "payload")
    runs: Path = field(default_factory=lambda: Path(os.environ.get("ONEOS_RUNS", BUILD / "test-runs")))
    accel: str = field(default_factory=lambda: os.environ.get("ONEOS_ACCEL", "") or detect_accel())
    keep: bool = field(default_factory=lambda: os.environ.get("ONEOS_KEEP", "0") == "1")

    @property
    def timeout_scale(self) -> float:
        env = os.environ.get("ONEOS_TIMEOUT_SCALE")
        if env:
            return float(env)
        return 1.0 if self.accel in ("kvm", "hvf") else 8.0  # TCG is roughly 5–10× slower

    def t(self, seconds: float) -> float:
        """Scale a KVM-calibrated timeout for the current accelerator."""
        return seconds * self.timeout_scale

    def firmware(self, kind: str) -> Path:
        p = _first(OVMF_CANDIDATES[kind])
        if p is None:
            raise FileNotFoundError(f"no OVMF firmware for {kind!r}; install the 'ovmf' package")
        return p

    @staticmethod
    def qemu_binary() -> str:
        # sudo resets PATH on macOS, so also look where Homebrew installs it.
        b = shutil.which("qemu-system-x86_64") or next(
            (p for p in ("/opt/homebrew/bin/qemu-system-x86_64", "/usr/local/bin/qemu-system-x86_64")
             if Path(p).exists()), None)
        if not b:
            raise FileNotFoundError("qemu-system-x86_64 not found")
        return b


def detect_accel() -> str:
    if os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK):
        return "kvm"
    return "tcg"
