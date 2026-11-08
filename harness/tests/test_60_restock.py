"""T60 — oneusb-restock brings back a deleted ISO with the right checksum (nightly)."""
import json

import pytest
from conftest import selftest

pytestmark = [pytest.mark.vm, pytest.mark.network, pytest.mark.nightly]
ISO = "ISO/netboot.xyz.efi"


def test_restock_replaces_missing_iso(overlay, make_vm, cfg):
    want = next(a["sha256"] for a in _manifest(cfg)["netboot"] if a["file"] == ISO)
    if overlay.sha256(ISO) is None:
        pytest.skip(f"{ISO} not on the stick")
    overlay.remove(ISO)
    r = selftest(make_vm, overlay, "t60-restock", "oneusb-restock --p1 \"$ONEUSB_P1\"\noneusb-restock --p1 \"$ONEUSB_P1\" --list")
    assert r["status"] == "PASS", r["output"]
    assert overlay.sha256(ISO) == want


def _manifest(cfg) -> dict:
    import yaml
    return yaml.safe_load((cfg.repo / "manifest.yaml").read_text())


def test_result_is_json(overlay):  # cheap guard that read_result works without a VM
    overlay.put_selftest("noop", "true")
    with overlay.p1() as p1:
        (p1 / "oneusb/selftest/results/noop.json").write_text(json.dumps({"status": "PASS"}))
    assert overlay.read_result("noop")["status"] == "PASS"
