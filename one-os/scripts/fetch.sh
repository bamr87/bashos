#!/usr/bin/env bash
# Download and verify every external artifact in manifest.yaml into cache/.
#   FETCH_LARGE=1   also fetch artifacts marked `large: true`
#   CI=true         only fetch artifacts marked `ci: true`
source "$(dirname "$0")/lib.sh"
need curl sha256sum python3 tar

mkdir -p "$CACHE_DIR"

# Ventoy release tarball, then unpack it once into build/ventoy/.
ventoy_json="$(manifest ventoy)"
v_url="$(jq -r .url <<<"$ventoy_json")"
v_sum="$(jq -r .sha256 <<<"$ventoy_json")"
v_ver="$(manifest get ventoy.version)"
download "$v_url" "$CACHE_DIR/$(basename "$v_url")" "$v_sum"
if [[ ! -x "$BUILD_DIR/ventoy/ventoy-$v_ver/Ventoy2Disk.sh" ]]; then
  mkdir -p "$BUILD_DIR/ventoy"
  tar -C "$BUILD_DIR/ventoy" -xzf "$CACHE_DIR/$(basename "$v_url")"
  log "unpacked Ventoy $v_ver"
fi

missing=0
while IFS= read -r a; do
  name="$(jq -r .name <<<"$a")"
  file="$(jq -r .file <<<"$a")"
  src="$(jq -r .source <<<"$a")"
  ci="$(jq -r .ci <<<"$a")"
  optional="$(jq -r .optional <<<"$a")"
  large="$(jq -r .large <<<"$a")"
  dest="$CACHE_DIR/$file"

  if [[ "${CI:-}" == true && "$ci" != true ]]; then log "skip (ci: false): $name"; continue; fi
  if [[ "$large" == true && "${FETCH_LARGE:-0}" != 1 ]]; then
    log "skip (large; set FETCH_LARGE=1): $name"; continue
  fi

  case "$src" in
    url)
      download "$(jq -r .url <<<"$a")" "$dest" "$(jq -r .sha256 <<<"$a")"
      ;;
    user-supplied)
      local_file="$ONEOS_ROOT/local-isos/$(basename "$file")"
      if [[ -f "$local_file" ]]; then
        mkdir -p "$(dirname "$dest")"
        ln -f "$local_file" "$dest" 2>/dev/null || cp -f "$local_file" "$dest"
        log "user-supplied: $name"
      elif [[ "$optional" == true ]]; then
        log "skip (optional, not in local-isos/): $name"
      else
        warn "missing required user-supplied ISO: local-isos/$(basename "$file")"; missing=1
      fi
      ;;
  esac
done < <(manifest artifacts)

# Record what we have, for stage-payload and humans.
(cd "$CACHE_DIR" && find . -type f ! -name '*.part' ! -name SHA256SUMS -print0 | sort -z |
  xargs -0 sha256sum | sed 's#  \./#  #') >"$CACHE_DIR/SHA256SUMS"
log "fetch complete → $CACHE_DIR"
exit "$missing"
