#!/usr/bin/env bash
# Assemble build/payload/: the file tree that goes onto P1 (§5.2).
# Deterministic: same inputs → same bytes (T90).
source "$(dirname "$0")/lib.sh"
need python3 mkfs.ext4 truncate sha256sum jq

lightos_iso="${LIGHTOS_ISO:-$BUILD_DIR/oneusb-lightos.iso}"
[[ -f "$lightos_iso" ]] || die "missing $lightos_iso — run 'make lightos' first (or set LIGHTOS_ISO)"

rm -rf "$PAYLOAD_DIR"
mkdir -p "$PAYLOAD_DIR"/{ISO,persistence,ventoy,oneusb/selftest/results}

# 1. ISOs. Hard links keep this instant and space-free when cache/ and build/ share a filesystem.
place() {
  mkdir -p "$(dirname "$2")"
  ln -f "$1" "$2" 2>/dev/null || cp -f --reflink=auto "$1" "$2"
}
place "$lightos_iso" "$PAYLOAD_DIR/$(manifest get lightos.file)"

present=("$(manifest get lightos.file)")
while IFS= read -r a; do
  file="$(jq -r .file <<<"$a")"
  if [[ -f "$CACHE_DIR/$file" ]]; then
    place "$CACHE_DIR/$file" "$PAYLOAD_DIR/$file"
    present+=("$file")
  else
    log "not staged (not in cache): $file"
  fi
done < <(manifest artifacts)

# 2. Persistence image: ext4 labelled "persistence" with "/ union" (Debian live).
#    Fixed UUID + hash seed + SOURCE_DATE_EPOCH make it byte-reproducible.
pers_mb="$(manifest get lightos.persistence_mb)"
pers_seed="$(mktemp -d)"
trap 'rm -rf "$pers_seed"' EXIT
echo "/ union" >"$pers_seed/persistence.conf"
touch -d "@$SOURCE_DATE_EPOCH" "$pers_seed/persistence.conf" "$pers_seed"
dat="$PAYLOAD_DIR/persistence/lightos.dat"
truncate -s "${pers_mb}M" "$dat"
mkfs.ext4 -q -F -L persistence \
  -U 6f6e6575-7362-4000-8000-706572736973 \
  -E hash_seed=6f6e6575-7362-4000-8000-686173680000,root_owner=0:0 \
  -d "$pers_seed" "$dat"

# 3. ventoy.json from the template, listing only entries that are actually on the stick.
PRESENT="${present[*]}" manifest render-ventoy "$ONEUSB_ROOT/config/ventoy.json.j2" \
  "$PAYLOAD_DIR/ventoy/ventoy.json"
if [[ -d "$ONEUSB_ROOT/config/theme" ]] && compgen -G "$ONEUSB_ROOT/config/theme/*.txt" >/dev/null; then
  cp -r "$ONEUSB_ROOT/config/theme" "$PAYLOAD_DIR/ventoy/theme"
fi

# 4. Manifest copy so oneusb-restock knows what belongs here.
cp "$ONEUSB_ROOT/manifest.yaml" "$PAYLOAD_DIR/oneusb/manifest.yaml"
cat >"$PAYLOAD_DIR/oneusb/selftest/README.txt" <<'EOF'
Self-test hook (ADR-0003). If run.sh exists here, the home base runs it at boot,
writes results/<name>.json, prints ONEUSB-SELFTEST <name> PASS|FAIL on ttyS0 and
powers off. Normal boots leave this directory alone.
EOF

# 5. Checksums of the whole payload (T00, T90, release SHA256SUMS).
find "$PAYLOAD_DIR" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
(cd "$PAYLOAD_DIR" && find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z |
  xargs -0 sha256sum | sed 's#  \./#  #') >"$BUILD_DIR/payload.SHA256SUMS"
log "payload staged → $PAYLOAD_DIR ($(du -sh --apparent-size "$PAYLOAD_DIR" | cut -f1))"
