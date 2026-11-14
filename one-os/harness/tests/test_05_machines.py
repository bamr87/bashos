"""T05 — machine profiles and the kernel check (scripts/oneos-machine), no VM."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts/oneos-machine"


def machine(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                          input=stdin, check=False)


def test_profiles_and_systems_lint():
    p = machine("lint")
    assert p.returncode == 0, p.stderr
    assert "x870e-dark-hero" in machine("list").stdout


def test_steamos_38_has_no_driver_for_the_x870e_wifi():
    """The epic's story 2: the check names the gap the 2026-11-12 deployment found by hand."""
    p = machine("check", "x870e-dark-hero", "--system", "steamos-3.8")
    assert p.returncode == 1
    assert "[MISS] Wi-Fi 7" in p.stdout and "MT7927" in p.stdout
    assert "[ OK ] 5 GbE Ethernet" in p.stdout and "[ OK ] 10 GbE Ethernet" in p.stdout


@pytest.mark.parametrize("system", ["bashos", "steamos-3.9", "home-base"])
def test_a_72_kernel_drives_every_known_x870e_chip(system):
    p = machine("check", "x870e-dark-hero", "--system", system)
    assert p.returncode == 0, p.stdout
    assert "[MISS]" not in p.stdout


def test_no_network_chip_means_no_unattended_deploy():
    p = machine("check", "x870e-dark-hero", "--kernel", "6.6")
    assert p.returncode == 2 and "cannot finish" in p.stdout


def test_lspci_mode_checks_only_the_chips_present():
    lspci = ("09:00.0 Network controller [0280]: MEDIATEK Corp. Device [14c3:7927]\n"
             "0b:00.0 VGA compatible controller [0300]: Some GPU [abcd:0001]\n")
    p = machine("check", "--lspci", "-", "--system", "debian-13", stdin=lspci)
    assert p.returncode == 2  # its only known chip is the Wi-Fi, which 6.12 cannot drive
    assert "2 devices, 1 chips a profile knows" in p.stdout


def test_an_unknown_system_is_refused():
    p = machine("check", "x870e-dark-hero", "--system", "windows-95")
    assert p.returncode != 0 and "unknown system" in p.stderr
