"""T60 — oneos-restock brings back a deleted ISO with the right checksum (nightly)."""
import json

import pytest
from conftest import selftest

pytestmark = [pytest.mark.vm, pytest.mark.network, pytest.mark.nightly]
ISO = "ISO/netboot.xyz-snp.efi"


def test_restock_replaces_missing_iso(overlay, make_vm, cfg):
    want = next(a["sha256"] for a in _manifest(cfg)["netboot"] if a["file"] == ISO)
    if overlay.sha256(ISO) is None:
        pytest.skip(f"{ISO} not on the stick")
    overlay.remove(ISO)
    r = selftest(make_vm, overlay, "t60-restock", "oneos-restock --p1 \"$ONEOS_P1\"\noneos-restock --p1 \"$ONEOS_P1\" --list")
    assert r["status"] == "PASS", r["output"]
    assert overlay.sha256(ISO) == want


def _manifest(cfg) -> dict:
    import yaml
    return yaml.safe_load((cfg.repo / "manifest.yaml").read_text())


def test_result_is_json(overlay):  # cheap guard that read_result works without a VM
    overlay.put_selftest("noop", "true")
    with overlay.p1() as p1:
        (p1 / "oneos/selftest/results/noop.json").write_text(json.dumps({"status": "PASS"}))
    assert overlay.read_result("noop")["status"] == "PASS"
