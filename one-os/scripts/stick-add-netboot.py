#!/usr/bin/env python3
"""stick-add-netboot.py [/Volumes/Ventoy] — add keyboard-safe network-boot entries to a stick.

Copies, into the mounted Ventoy data partition (no reformat, nothing else changes):
  ISO/netboot.xyz-snp.efi   netboot.xyz using the firmware's network driver — the default
                            netboot.xyz.efi brings its own drivers, which take the USB
                            controller away from the firmware on some boards (keyboard dies)
  ISO/one-os-netboot.efi   plain iPXE (snponly): Ctrl-B at its banner for a shell, then
                            dhcp + chain http://<server>:8780/boot.ipxe
and adds menu names for both (UEFI only) to ventoy/ventoy.json, keeping a .bak copy.
Sources: build/sd-additions/ISO/ (prepared from the pinned netboot.xyz checksum list and
build/netboot/tftp/snponly.efi).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "sd-additions" / "ISO"
ENTRIES = {
    "netboot.xyz-snp.efi": "Network install (netboot.xyz, keyboard-safe)",
    "one-os-netboot.efi": "Network boot from a one-os server (iPXE, Ctrl-B for shell)",
}


def main() -> int:
    vol = Path(sys.argv[1] if len(sys.argv) > 1 else "/Volumes/Ventoy")
    cfg = vol / "ventoy" / "ventoy.json"
    if not cfg.is_file():
        raise SystemExit(f"{vol} isn't a mounted one-os/Ventoy data partition (no ventoy/ventoy.json)")
    missing = [n for n in ENTRIES if not (SRC / n).is_file()]
    if missing:
        raise SystemExit(f"missing in {SRC}: {missing}")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    shutil.copyfile(cfg, cfg.with_name("ventoy.json.bak"))
    for name in ENTRIES:
        shutil.copyfile(SRC / name, vol / "ISO" / name)
        print(f"copied ISO/{name}")
    aliases = [a for a in data.get("menu_alias", []) if a.get("image", "").lstrip("/") not in
               {f"ISO/{n}" for n in ENTRIES}]
    aliases += [{"image": f"/ISO/{n}", "alias": alias} for n, alias in ENTRIES.items()]
    data["menu_alias"] = aliases
    legacy = set(data.get("image_blacklist_legacy", []))
    legacy |= {f"/ISO/{n}" for n in ENTRIES}
    data["image_blacklist_legacy"] = sorted(legacy)
    cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.loads(cfg.read_text(encoding="utf-8"))  # still valid
    print(f"updated {cfg} (backup: ventoy.json.bak)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
