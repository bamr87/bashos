"""T00 — image structure, no VM."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

VENTOY_SCHEMA = {
    "type": "object",
    "required": ["control", "persistence", "menu_alias"],
    "properties": {
        "control": {"type": "array", "items": {"type": "object", "minProperties": 1, "maxProperties": 1}},
        "persistence": {"type": "array", "items": {
            "type": "object", "required": ["image", "backend"],
            "properties": {"image": {"type": "string", "pattern": "^/"}, "backend": {"type": "string", "pattern": "^/"}}}},
        "menu_alias": {"type": "array", "items": {
            "type": "object", "required": ["image", "alias"],
            "properties": {"image": {"type": "string", "pattern": "^/"}, "alias": {"type": "string"}}}},
    },
}


@pytest.fixture(scope="module")
def table(image: Path) -> dict:
    out = subprocess.run(["sfdisk", "--json", str(image)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["partitiontable"]


def _probe(image: Path, part: dict, sector: int) -> dict:
    out = subprocess.run(["blkid", "-p", "-O", str(part["start"] * sector), "-o", "export", str(image)],
                         capture_output=True, text=True, check=False)
    return dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)


def test_partition_layout(table: dict, image: Path):
    parts = table["partitions"]
    assert len(parts) >= 2, parts
    sector = table.get("sectorsize", 512)
    p1, p2 = parts[0], parts[1]
    assert _probe(image, p1, sector).get("LABEL") == "Ventoy"
    assert _probe(image, p1, sector).get("TYPE") == "exfat"
    p2info = _probe(image, p2, sector)
    assert p2info.get("LABEL") == "VTOYEFI"
    assert p2["size"] * sector == 32 * 1024 * 1024
    assert p2["start"] > p1["start"], "VTOYEFI must follow the data partition"


def test_payload_matches_manifest(overlay, cfg):
    sums = cfg.build / "payload.SHA256SUMS"
    if not sums.exists():
        pytest.skip("build/payload.SHA256SUMS missing — run 'make payload'")
    expected = dict(reversed(line.split(maxsplit=1)) for line in sums.read_text().splitlines())
    import hashlib
    with overlay.p1(readonly=True) as p1:
        for rel, digest in expected.items():
            f = p1 / rel.strip()
            assert f.exists(), f"{rel} missing on P1"
            if f.stat().st_size > 64 << 20:
                # Big ISOs: compare size + head/tail hash instead of reading GBs.
                src = cfg.payload / rel.strip()
                if src.exists():
                    assert f.stat().st_size == src.stat().st_size, rel
                    continue
            h = hashlib.sha256()
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            assert h.hexdigest() == digest, f"checksum mismatch: {rel}"


def test_ventoy_json(overlay):
    with overlay.p1(readonly=True) as p1:
        data = json.loads((p1 / "ventoy" / "ventoy.json").read_text(encoding="utf-8"))
        jsonschema.validate(data, VENTOY_SCHEMA)
        for entry in data["persistence"]:
            assert (p1 / entry["image"].lstrip("/")).exists(), entry
            assert (p1 / entry["backend"].lstrip("/")).exists(), entry
        for entry in data["menu_alias"]:
            assert (p1 / entry["image"].lstrip("/")).exists(), f"alias for missing image {entry}"
        ctrl = {k: v for c in data["control"] for k, v in c.items()}
        assert (p1 / ctrl["VTOY_DEFAULT_IMAGE"].lstrip("/")).exists()
        # Windows 11 setup from the stick: TPM/Secure Boot/RAM checks and the online-account step
        assert ctrl.get("VTOY_WIN11_BYPASS_CHECK") in ("0", "1")
        assert ctrl.get("VTOY_WIN11_BYPASS_NRO") in ("0", "1")


def test_persistence_image(overlay):
    with overlay.p1(readonly=True) as p1:
        dat = p1 / "persistence" / "lightos.dat"
        out = subprocess.run(["blkid", "-p", "-o", "export", str(dat)], capture_output=True, text=True, check=True)
        info = dict(line.split("=", 1) for line in out.stdout.splitlines())
        assert info["TYPE"] == "ext4" and info["LABEL"] == "persistence"
        conf = subprocess.run(["debugfs", "-R", "cat /persistence.conf", str(dat)],
                              capture_output=True, text=True, check=True).stdout
        assert conf.strip() == "/ union"
