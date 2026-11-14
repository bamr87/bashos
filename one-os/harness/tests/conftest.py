"""Shared fixtures. Each test gets build/test-runs/<test>/ for its artifacts (PLAN §7.4)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from oneos_harness import VM, Config, Overlay


@pytest.fixture(scope="session")
def cfg() -> Config:
    return Config()


@pytest.fixture(scope="session")
def image(cfg: Config) -> Path:
    if not cfg.image.exists():
        pytest.skip(f"{cfg.image} missing — run 'make image'")
    return cfg.image


@pytest.fixture
def run_dir(cfg: Config, request) -> Path:
    d = cfg.runs / re.sub(r"[^\w.-]+", "_", request.node.name)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


@pytest.fixture
def overlay(image: Path, run_dir: Path, cfg: Config, request):
    ov = Overlay(image, run_dir)
    yield ov
    failed = getattr(request.node, "rep_call", None) and request.node.rep_call.failed
    if not (cfg.keep or failed):
        ov.discard()  # overlays are big; logs/pcaps/screens stay


@pytest.fixture
def make_vm(cfg: Config, run_dir: Path):
    vms: list[VM] = []

    def _make(**kw) -> VM:
        vm = VM(cfg, run_dir, **kw)
        vms.append(vm)
        return vm

    yield _make
    for vm in vms:
        if vm.alive():
            try:
                vm.screendump(vm.dir / f"{vm.name}.final.png")
            except Exception:
                pass
        vm.kill()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def selftest(make_vm, overlay: Overlay, name: str, script: str, *, profile: str = "uefi",
             timeout: float = 600, **vm_kw) -> dict:
    """Inject a self-test, boot the stick, wait for its verdict and power-off, return the result JSON."""
    overlay.put_selftest(name, script)
    overlay.set_default_image("/ISO/oneos-lightos.iso", timeout=1)
    vm = make_vm(profile=profile, usb_image=overlay.path, name=name, **vm_kw).start()
    verdict = vm.wait_serial(rf"ONEOS-SELFTEST {re.escape(name)} (PASS|FAIL)", timeout)
    vm.wait_shutdown(120)
    result = overlay.read_result(name)
    assert result["status"] in verdict
    return result
