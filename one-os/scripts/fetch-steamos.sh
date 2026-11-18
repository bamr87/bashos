#!/usr/bin/env bash
# fetch-steamos.sh — download Valve's latest SteamOS recovery image into cache/steamos/.
# Resolves Valve's stable "latest" link to the dated file, skips the download if that file
# is already cached, verifies the bzip2 stream and records its SHA-256 (Valve publishes none).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LATEST=https://steamdeck-images.steamos.cloud/recovery/steamdeck-repair-latest.img.bz2
out="$ROOT/cache/steamos"; mkdir -p "$out"
url="$(curl -fsSI "$LATEST" | awk 'tolower($1)=="location:"{print $2}' | tr -d '\r')"
[[ -n $url ]] || url="$LATEST"
f="$out/$(basename "$url")"
echo "$url" >"$out/LATEST_URL"
if [[ -f $f && -f $f.sha256 ]]; then echo "cached: $(basename "$f")"; exit 0; fi
echo "downloading $url ($(curl -fsSIL "$url" | awk 'tolower($1)=="content-length:"{v=$2} END{printf "%.2f GB", v/1e9}'))"
curl -fL --retry 3 -C - -o "$f.part" "$url"
echo "verifying the bzip2 stream…"
if command -v lbzip2 >/dev/null; then lbzip2 -t "$f.part"; else bzip2 -t "$f.part"; fi
mv "$f.part" "$f"
sha=(sha256sum); command -v sha256sum >/dev/null || sha=(shasum -a 256)   # Linux / macOS
(cd "$out" && "${sha[@]}" "$(basename "$f")" >"$(basename "$f").sha256")
echo "cached: $(basename "$f")  sha256 $(cut -d' ' -f1 "$f.sha256")"
