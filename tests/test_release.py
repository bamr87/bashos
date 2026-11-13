"""The release pipeline contract (UPS-QA-32, bashos#89).

release-please owns the version and CHANGELOG; publishing is chained off its
``release_created`` output in the same run, never off a tag push (a tag made
with GITHUB_TOKEN would not trigger another workflow).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
REUSABLE = "bamr87/.github/.github/workflows/release-please.yml@main"


def _workflow() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as boolean True.
    doc["on"] = doc.pop(True, doc.get("on"))
    return doc


def test_config_and_manifest_are_valid_and_match_the_package_version() -> None:
    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    pkg = config["packages"]["."]
    assert pkg["release-type"] == "python"
    assert pkg["changelog-path"] == "CHANGELOG.md"

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert manifest == {".": version}


def test_dunder_version_is_bumped_with_the_package() -> None:
    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    assert "src/bashos/__init__.py" in config["packages"]["."]["extra-files"]
    init = (ROOT / "src" / "bashos" / "__init__.py").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    assert re.search(
        rf'^__version__ = "{re.escape(manifest["."])}"\s+# x-release-please-version$', init, re.M
    )


def test_release_runs_on_main_through_the_fleet_reusable_workflow() -> None:
    wf = _workflow()
    assert wf["on"]["push"] == {"branches": ["main"]}
    assert "tags" not in wf["on"]["push"]
    assert "workflow_dispatch" in wf["on"]
    release = wf["jobs"]["release"]
    assert release["uses"] == REUSABLE
    assert release["secrets"] == "inherit"


def test_publishing_is_chained_off_release_created_in_the_same_run() -> None:
    jobs = _workflow()["jobs"]
    target = jobs["target"]
    assert target["needs"] == "release"
    assert "needs.release.outputs.release_created == 'true'" in target["if"]
    for name in ("build", "github-release", "pypi", "ghcr"):
        needs = jobs[name]["needs"]
        needs = [needs] if isinstance(needs, str) else needs
        assert "target" in needs, f"{name} must wait for the resolved release tag"
