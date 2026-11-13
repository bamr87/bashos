"""T90 — two clean payload builds produce identical checksums (nightly)."""
import os
import subprocess

import pytest

pytestmark = pytest.mark.nightly


def test_payload_is_reproducible(cfg, tmp_path):
    if not cfg.lightos_iso.exists():
        pytest.skip("needs build/oneos-lightos.iso")
    sums = []
    for i in (1, 2):
        b = tmp_path / f"b{i}"
        env = {**os.environ, "BUILD_DIR": str(b), "PAYLOAD_DIR": str(b / "payload"),
               "LIGHTOS_ISO": str(cfg.lightos_iso)}
        subprocess.run([str(cfg.repo / "scripts/stage-payload.sh")], env=env, check=True)
        sums.append((b / "payload.SHA256SUMS").read_text())
    assert sums[0] == sums[1]
