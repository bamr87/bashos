"""T30 — persistence round-trip across two boots."""
import secrets

import pytest
from conftest import selftest

pytestmark = pytest.mark.vm


def test_persistence_round_trip(overlay, make_vm):
    token = secrets.token_hex(16)
    r1 = selftest(make_vm, overlay, "t30-write", f"echo {token} > /root/canary\nsync\ncat /root/canary",
                  net=False)
    assert r1["status"] == "PASS", r1["output"]
    r2 = selftest(make_vm, overlay, "t30-read",
                  f'test -f /root/canary\nread -r got < /root/canary\n[ "$got" = "{token}" ]\necho "$got"',
                  net=False)
    assert r2["status"] == "PASS", r2["output"]
    assert token in r2["output"]
