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
# The hub's own release-please workflow at its floating major tag (decision D3,
# UPS-REPO-21; never a branch, UPS-WORK-10). bamr87/.github's copy is legacy.
REUSABLE = "bamr87/bamr87/.github/workflows/release-please.yml@v2"


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
    # RELEASE_PLEASE_TOKEN is the only credential that can open the release PR
    # here (Actions may not create PRs), so a PR that cannot be opened fails the
    # run instead of warning.
    assert release["with"]["strict-pr-creation"] is True
    assert release["permissions"] == {"contents": "write", "pull-requests": "write"}


def test_publishing_is_chained_off_release_created_in_the_same_run() -> None:
    jobs = _workflow()["jobs"]
    target = jobs["target"]
    assert target["needs"] == "release"
    assert "needs.release.outputs.release_created == 'true'" in target["if"]
    assert "github.event_name == 'workflow_dispatch'" in target["if"]
    # A job without `if:` gets an implicit success(), which GitHub evaluates over
    # every ancestor job, not only its own `needs:`. On a manual dispatch the
    # `release` job is skipped, so without an explicit condition every publish
    # job would be skipped too and the recovery run would end green having
    # published nothing (likewise when the tagging pass succeeds but the PR pass
    # fails). Each publish job therefore gates on the jobs it actually needs.
    for name, upstream in (
        ("build", ["target"]),
        ("github-release", ["target", "build"]),
        ("pypi", ["target", "build"]),
        ("ghcr", ["target"]),
    ):
        job = jobs[name]
        needs = job["needs"]
        needs = [needs] if isinstance(needs, str) else needs
        assert "target" in needs, f"{name} must wait for the resolved release tag"
        condition = job.get("if", "")
        assert "!cancelled()" in condition, f"{name} must not inherit the skipped release job"
        for dep in upstream:
            assert f"needs.{dep}.result == 'success'" in condition, f"{name} must require {dep} to succeed"
