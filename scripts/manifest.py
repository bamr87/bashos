#!/usr/bin/env python3
"""Read manifest.yaml for the shell scripts.

  manifest.py get <dotted.path>          print a scalar (or JSON for lists/maps)
  manifest.py artifacts                  one JSON object per line: every ISO-like artifact
  manifest.py lint                       schema check + no <PIN> placeholders
  manifest.py render-ventoy <tmpl> <out> render config/ventoy.json.j2
  manifest.py packages                   lightos package list (desktop + extras)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(os.environ.get("ONEUSB_MANIFEST", ROOT / "manifest.yaml"))
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# The image is built with --apt-recommends false, so list the X server, input/video
# drivers and greeter explicitly (lightdm alone fails to start without them).
XORG = ["xserver-xorg-core", "xserver-xorg-video-all", "xserver-xorg-input-all", "xinit", "dbus-x11",
        "fonts-dejavu-core"]
DESKTOP_PACKAGES = {
    "xfce": XORG + ["xfce4", "xfce4-terminal", "lightdm", "lightdm-gtk-greeter", "network-manager-gnome",
                    "firefox-esr"],
    "lxqt": XORG + ["lxqt-core", "qterminal", "sddm", "nm-tray", "firefox-esr"],
    "none": [],
}


def load(path: Path = MANIFEST) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def artifacts(m: dict) -> list[dict]:
    """Everything that ends up as a file on P1, except the locally built lightos ISO."""
    out = []
    for kind in ("netboot", "isos"):
        for a in m.get(kind) or []:
            a = dict(a)
            a["kind"] = kind
            a.setdefault("ci", False)
            a.setdefault("optional", False)
            a.setdefault("large", False)
            a.setdefault("mode", "any")              # any | uefi | legacy
            a["source"] = a.get("source", "url")
            out.append(a)
    return out


def ventoy_artifact(m: dict) -> dict:
    v = m["ventoy"]
    return {"name": "ventoy", "url": v["url"], "sha256": v["sha256"],
            "file": os.path.basename(v["url"]), "source": "url", "kind": "ventoy"}


def lint(m: dict) -> list[str]:
    errs = []
    raw = MANIFEST.read_text(encoding="utf-8")
    if "<PIN>" in raw:
        errs.append("manifest contains <PIN> placeholders")
    if m.get("schema") != 1:
        errs.append("schema must be 1")
    v = m.get("ventoy") or {}
    for k in ("version", "url", "sha256"):
        if not v.get(k):
            errs.append(f"ventoy.{k} missing")
    if v.get("sha256") and not SHA_RE.match(v["sha256"]):
        errs.append("ventoy.sha256 is not a sha256")
    if v.get("version") and v["version"] not in v.get("url", ""):
        errs.append("ventoy.url does not contain ventoy.version")
    opts = v.get("options") or {}
    if opts.get("partition_style") not in ("gpt", "mbr"):
        errs.append("ventoy.options.partition_style must be gpt|mbr")
    lo = m.get("lightos") or {}
    if lo.get("desktop") not in DESKTOP_PACKAGES:
        errs.append(f"lightos.desktop must be one of {sorted(DESKTOP_PACKAGES)}")
    if not str(lo.get("file", "")).startswith("ISO/"):
        errs.append("lightos.file must live under ISO/")
    seen = set()
    for a in artifacts(m):
        n = a.get("name")
        if not n or not a.get("file"):
            errs.append(f"artifact {a!r} needs name and file")
            continue
        if a["file"] in seen:
            errs.append(f"duplicate file {a['file']}")
        seen.add(a["file"])
        if a["source"] == "url":
            if not a.get("url"):
                errs.append(f"{n}: url missing")
            if not SHA_RE.match(str(a.get("sha256", ""))):
                errs.append(f"{n}: sha256 missing or malformed")
        if a["mode"] not in ("any", "uefi", "legacy"):
            errs.append(f"{n}: mode must be any|uefi|legacy")
        if a.get("alias") and not a["alias"].isascii():
            errs.append(f"{n}: alias must be ASCII (Ventoy's menu font has no emoji)")
        if a["source"] == "user-supplied" and a["ci"]:
            errs.append(f"{n}: user-supplied artifacts must have ci: false")
        if a["source"] not in ("url", "user-supplied"):
            errs.append(f"{n}: unknown source {a['source']}")
    return errs


def render_ventoy(m: dict, tmpl: Path, out: Path) -> None:
    import jinja2

    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    text = env.from_string(tmpl.read_text(encoding="utf-8")).render(
        m=m, artifacts=artifacts(m), present=set(os.environ.get("PRESENT", "").split()))
    data = json.loads(text)  # fail loudly on invalid JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    m = load()
    cmd = argv[0]
    if cmd == "get":
        cur = m
        for part in argv[1].split("."):
            cur = cur[int(part)] if isinstance(cur, list) else cur[part]
        print(json.dumps(cur) if isinstance(cur, (list, dict)) else
              ("true" if cur is True else "false" if cur is False else cur))
    elif cmd == "artifacts":
        for a in artifacts(m):
            print(json.dumps(a, ensure_ascii=False))
    elif cmd == "ventoy":
        print(json.dumps(ventoy_artifact(m)))
    elif cmd == "lint":
        errs = lint(m)
        for e in errs:
            print(f"manifest: {e}", file=sys.stderr)
        return 1 if errs else 0
    elif cmd == "render-ventoy":
        render_ventoy(m, Path(argv[1]), Path(argv[2]))
    elif cmd == "packages":
        lo = m["lightos"]
        for p in DESKTOP_PACKAGES[lo["desktop"]] + list(lo.get("extra_packages") or []):
            print(p)
    else:
        print(f"unknown command {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
